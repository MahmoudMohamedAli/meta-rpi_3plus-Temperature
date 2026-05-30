#!/usr/bin/env python3
"""
Process Line Controller — Raspberry Pi FSM
==========================================
Simulates an industrial conveyor / item-processing station.

Hardware wiring (BCM pin numbers):
  GPIO 17 — IR sensor     input   (item present = LOW, pulled up)
  GPIO 27 — Start button  input   (pressed = LOW, pulled up)
  GPIO 22 — E-stop button input   (pressed = LOW, pulled up)
  GPIO 23 — Green LED     output  (running indicator)
  GPIO 24 — Red LED       output  (fault / e-stop indicator)
  GPIO 25 — Relay         output  (conveyor motor)

Usage:
  python process_line_fsm.py           # auto-detects hardware
  python process_line_fsm.py --sim     # force simulation mode
"""

import asyncio
import argparse
import logging
import sys

# ─────────────────────────────────────────────
# Logging — stdout + file
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("process_line.log"),
    ],
)
log = logging.getLogger("fsm")

# ─────────────────────────────────────────────
# GPIO abstraction — real or simulated
# ─────────────────────────────────────────────
class _SimGPIO:
    """Drop-in GPIO simulator so the programme runs on any machine."""
    BCM   = "BCM"
    IN    = "IN"
    OUT   = "OUT"
    PUD_UP = "PUD_UP"

    def __init__(self):
        self._pins: dict[int, bool] = {}

    def setmode(self, _): pass

    def setup(self, pin, mode, pull_up_down=None):
        self._pins[pin] = True       # inputs default HIGH (not pressed/not blocked)

    def output(self, pin, val: bool):
        self._pins[pin] = val
        _PIN_NAMES = {23: "GREEN_LED", 24: "RED_LED  ", 25: "RELAY    "}
        name = _PIN_NAMES.get(pin, f"GPIO{pin:2d} ")
        log.info(f"    [hw]  {name} → {'ON ' if val else 'OFF'}")

    def input(self, pin) -> bool:
        return self._pins.get(pin, True)

    def cleanup(self):
        log.info("    [hw]  GPIO cleaned up (sim)")


try:
    import RPi.GPIO as _GPIO      # type: ignore
    GPIO = _GPIO
    _SIM = False
    log.info("RPi.GPIO found — running in HARDWARE mode")
except ImportError:
    GPIO = _SimGPIO()
    _SIM = True
    log.info("RPi.GPIO not found — running in SIMULATION mode")

# ─────────────────────────────────────────────
# Pin definitions (BCM)
# ─────────────────────────────────────────────
PIN_IR_SENSOR  = 17
PIN_BTN_START  = 27
PIN_BTN_ESTOP  = 22
PIN_LED_GREEN  = 23
PIN_LED_RED    = 24
PIN_RELAY      = 25

# ─────────────────────────────────────────────
# Hardware layer — thin wrapper over GPIO
# ─────────────────────────────────────────────
class Hardware:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN_IR_SENSOR, GPIO.IN,  pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN_BTN_START, GPIO.IN,  pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN_BTN_ESTOP, GPIO.IN,  pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PIN_LED_GREEN, GPIO.OUT)
        GPIO.setup(PIN_LED_RED,   GPIO.OUT)
        GPIO.setup(PIN_RELAY,     GPIO.OUT)
        self.all_off()

    # outputs
    def set_green_led(self, on: bool): GPIO.output(PIN_LED_GREEN, on)
    def set_red_led  (self, on: bool): GPIO.output(PIN_LED_RED,   on)
    def set_relay    (self, on: bool): GPIO.output(PIN_RELAY,     on)

    def all_off(self):
        self.set_green_led(False)
        self.set_red_led(False)
        self.set_relay(False)

    # inputs — active LOW (button pressed / sensor blocked = False from GPIO)
    def start_pressed(self) -> bool: return not GPIO.input(PIN_BTN_START)
    def estop_pressed(self) -> bool: return not GPIO.input(PIN_BTN_ESTOP)
    def item_present (self) -> bool: return not GPIO.input(PIN_IR_SENSOR)

    def cleanup(self):
        self.all_off()
        GPIO.cleanup()

# ─────────────────────────────────────────────
# FSM transition table
# ─────────────────────────────────────────────
TRANSITIONS: dict[str, dict[str, str]] = {
    "IDLE": {
        "start":            "STARTING",
        "e_stop":           "EMERGENCY_STOP",
    },
    "STARTING": {
        "startup_done":     "RUNNING",
        "e_stop":           "EMERGENCY_STOP",
    },
    "RUNNING": {
        "item_detected":    "ITEM_DETECTED",
        "sensor_fail":      "FAULT",
        "stop":             "IDLE",
        "e_stop":           "EMERGENCY_STOP",
    },
    "ITEM_DETECTED": {
        "begin_process":    "PROCESSING",
        "e_stop":           "EMERGENCY_STOP",
    },
    "PROCESSING": {
        "process_done":     "RUNNING",
        "process_fail":     "FAULT",
        "e_stop":           "EMERGENCY_STOP",
    },
    "FAULT": {
        "reset":            "IDLE",
        "critical":         "SHUTDOWN",
    },
    "EMERGENCY_STOP": {
        "e_reset":          "IDLE",
        "confirm_stop":     "SHUTDOWN",
    },
    "SHUTDOWN": {},    # terminal — no outgoing transitions
}

# ─────────────────────────────────────────────
# FSM class
# ─────────────────────────────────────────────
class ProcessLineFSM:
    def __init__(self, hw: Hardware):
        self.state   = "IDLE"
        self.hw      = hw
        self.history: list[tuple[str, str, str]] = []
        self._on_enter()

    def send(self, event: str) -> bool:
        """Fire an event. Returns True if a transition occurred."""
        next_state = TRANSITIONS[self.state].get(event)
        if next_state is None:
            log.warning(f"Event '{event}' ignored in state '{self.state}'")
            return False

        log.info(f"  {self.state}  --[{event}]-->  {next_state}")
        self._on_exit()
        self.history.append((self.state, event, next_state))
        self.state = next_state
        self._on_enter()
        return True

    def is_terminal(self) -> bool:
        return self.state == "SHUTDOWN"

    # ── entry actions ────────────────────────
    def _on_enter(self):
        s = self.state
        log.info(f"[{s}]")

        if s == "IDLE":
            self.hw.all_off()

        elif s == "STARTING":
            self.hw.set_green_led(True)
            log.info("  Motor spinup — waiting 1.5 s...")

        elif s == "RUNNING":
            self.hw.set_relay(True)
            self.hw.set_green_led(True)
            log.info("  Conveyor active — monitoring IR sensor")

        elif s == "ITEM_DETECTED":
            self.hw.set_relay(False)       # stop belt
            log.info("  Item at station — conveyor paused")

        elif s == "PROCESSING":
            log.info("  Actuator working on item (2 s)...")

        elif s == "FAULT":
            self.hw.set_relay(False)
            self.hw.set_green_led(False)
            log.warning("  Sensor/motor error — operator intervention required")

        elif s == "EMERGENCY_STOP":
            self.hw.set_relay(False)
            self.hw.set_green_led(False)
            log.critical("  !!! ALL MOTION HALTED — press e_reset or confirm_stop !!!")

        elif s == "SHUTDOWN":
            self.hw.all_off()
            log.info("  Saving logs, releasing GPIO...")

    # ── exit actions ─────────────────────────
    def _on_exit(self):
        pass    # extend here if you need teardown logic per state

    def print_history(self):
        log.info("─── Transition history ───")
        for i, (frm, evt, to) in enumerate(self.history, 1):
            log.info(f"  {i:2}.  {frm}  →[{evt}]→  {to}")

# ─────────────────────────────────────────────
# Background tasks
# ─────────────────────────────────────────────

async def gpio_poller(hw: Hardware, queue: asyncio.Queue):
    """
    Real hardware: poll GPIO at 20 Hz and push events.
    Debounced — only fires on the rising edge of each signal.
    """
    prev_start = prev_estop = prev_item = False
    while True:
        start = hw.start_pressed()
        estop = hw.estop_pressed()
        item  = hw.item_present()

        if start and not prev_start: await queue.put("start")
        if estop and not prev_estop: await queue.put("e_stop")
        if item  and not prev_item:  await queue.put("item_detected")

        prev_start, prev_estop, prev_item = start, estop, item
        await asyncio.sleep(0.05)


async def sim_event_sequence(queue: asyncio.Queue):
    """
    Simulation: scripted event sequence that exercises every state path.
    Replace or extend this to test specific scenarios.
    """
    log.info("[SIM] Starting scripted event sequence")

    async def send(evt, delay):
        await asyncio.sleep(delay)
        log.info(f"[SIM] → {evt}")
        await queue.put(evt)

    # Normal run: two items processed, then operator stops line
    await send("start",        1.0)
    await send("startup_done", 1.5)
    await send("item_detected",1.0)
    await send("begin_process",0.3)
    await send("process_done", 2.0)
    await send("item_detected",0.8)
    await send("begin_process",0.3)
    await send("process_done", 2.0)
    await send("stop",         0.8)   # operator stops line

    # Fault and recovery
    await send("start",        1.0)
    await send("startup_done", 1.5)
    await send("sensor_fail",  1.0)   # injected fault
    await send("reset",        2.0)   # operator resets

    # Emergency stop → shutdown
    await send("start",        1.0)
    await send("startup_done", 1.5)
    await send("e_stop",       1.0)   # e-stop during run
    await send("confirm_stop", 2.0)   # operator confirms shutdown


async def startup_timer(queue: asyncio.Queue, fsm: ProcessLineFSM):
    """Auto-fire startup_done after 1.5 s in STARTING state (hardware mode)."""
    while True:
        if fsm.state == "STARTING":
            await asyncio.sleep(1.5)
            if fsm.state == "STARTING":
                await queue.put("startup_done")
        await asyncio.sleep(0.1)


async def process_timer(queue: asyncio.Queue, fsm: ProcessLineFSM):
    """
    Hardware mode:
      - auto begin_process 300 ms after ITEM_DETECTED
      - auto process_done  2 s after PROCESSING starts
    """
    while True:
        if fsm.state == "ITEM_DETECTED":
            await asyncio.sleep(0.3)
            if fsm.state == "ITEM_DETECTED":
                await queue.put("begin_process")

        if fsm.state == "PROCESSING":
            await asyncio.sleep(2.0)
            if fsm.state == "PROCESSING":
                await queue.put("process_done")

        await asyncio.sleep(0.05)


async def fault_led_blinker(hw: Hardware, fsm: ProcessLineFSM):
    """Blink red LED at 2 Hz when in FAULT or EMERGENCY_STOP."""
    blink = False
    while True:
        if fsm.state in ("FAULT", "EMERGENCY_STOP"):
            blink = not blink
            hw.set_red_led(blink)
            await asyncio.sleep(0.25)
        else:
            hw.set_red_led(False)
            await asyncio.sleep(0.05)


async def fsm_loop(fsm: ProcessLineFSM, queue: asyncio.Queue):
    """Main FSM loop — drains the event queue until terminal state."""
    while not fsm.is_terminal():
        event = await queue.get()
        fsm.send(event)
        queue.task_done()
    log.info("FSM reached SHUTDOWN — stopping all tasks")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
async def main(sim: bool):
    log.info("=" * 52)
    log.info("  Process Line Controller")
    log.info(f"  Mode: {'SIMULATION' if sim else 'HARDWARE'}")
    log.info("=" * 52)

    hw    = Hardware()
    queue: asyncio.Queue = asyncio.Queue()
    fsm   = ProcessLineFSM(hw)

    # Build task list based on mode
    background_tasks = [
        asyncio.create_task(fault_led_blinker(hw, fsm)),
    ]

    if sim:
        background_tasks.append(asyncio.create_task(sim_event_sequence(queue)))
    else:
        background_tasks.append(asyncio.create_task(gpio_poller(hw, queue)))
        background_tasks.append(asyncio.create_task(startup_timer(queue, fsm)))
        background_tasks.append(asyncio.create_task(process_timer(queue, fsm)))

    try:
        await fsm_loop(fsm, queue)   # blocks until SHUTDOWN
    finally:
        # Cancel all background tasks cleanly
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)

        hw.cleanup()
        fsm.print_history()
        log.info(f"Total transitions: {len(fsm.history)}")
        log.info("Goodbye.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process Line FSM Controller")
    parser.add_argument(
        "--sim", action="store_true",
        help="Force simulation mode (scripted events, no GPIO needed)"
    )
    args = parser.parse_args()

    force_sim = args.sim or _SIM     # auto-sim if RPi.GPIO not available

    try:
        asyncio.run(main(force_sim))
    except KeyboardInterrupt:
        log.info("Interrupted by user")