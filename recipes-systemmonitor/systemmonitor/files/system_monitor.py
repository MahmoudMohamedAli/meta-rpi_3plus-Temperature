#!/usr/bin/env python3

import os
import time
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ── Sensor readers ────────────────────────────────────────────────────────────

def read_cpu_temp():
    """Read CPU temperature from sysfs in degrees Celsius."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 2)
    except Exception:
        return None


def read_memory():
    """Parse /proc/meminfo and return used/total in MB."""
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:"):
                    mem[parts[0]] = int(parts[1])  # kB
        total = mem.get("MemTotal:", 0)
        available = mem.get("MemAvailable:", 0)
        used = total - available
        return {
            "total_mb": round(total / 1024, 1),
            "used_mb":  round(used  / 1024, 1),
            "free_mb":  round(available / 1024, 1),
            "percent":  round((used / total) * 100, 1) if total else 0,
        }
    except Exception:
        return None


def read_cpu_usage():
    """
    Calculate CPU usage % by sampling /proc/stat twice with a short delay.
    Returns a float in [0, 100].
    """
    def get_times():
        with open("/proc/stat") as f:
            line = f.readline().split()
        # user nice system idle iowait irq softirq ...
        values = list(map(int, line[1:]))
        idle  = values[3]
        total = sum(values)
        return idle, total

    idle1, total1 = get_times()
    time.sleep(0.1)
    idle2, total2 = get_times()

    diff_idle  = idle2  - idle1
    diff_total = total2 - total1

    if diff_total == 0:
        return 0.0
    return round((1 - diff_idle / diff_total) * 100, 1)


def read_uptime():
    """Return uptime as a human-readable string."""
    try:
        with open("/proc/uptime") as f:
            seconds = float(f.read().split()[0])
        days    = int(seconds // 86400)
        hours   = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs    = int(seconds % 60)
        return f"{days}d {hours}h {minutes}m {secs}s"
    except Exception:
        return None


def read_disk():
    """Return disk usage for / in MB."""
    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        free  = stat.f_bfree  * stat.f_frsize
        used  = total - free
        return {
            "total_mb": round(total / (1024 * 1024), 1),
            "used_mb":  round(used  / (1024 * 1024), 1),
            "free_mb":  round(free  / (1024 * 1024), 1),
            "percent":  round((used / total) * 100, 1) if total else 0,
        }
    except Exception:
        return None


# ── Stats collector ───────────────────────────────────────────────────────────

class SystemStats:
    """Thread-safe stats cache refreshed every 2 seconds."""

    def __init__(self, interval=2):
        self._interval = interval
        self._lock = threading.Lock()
        self._stats = {}
        self._refresh()                       # initial read
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _refresh(self):
        stats = {
            "cpu_temp_c":  read_cpu_temp(),
            "cpu_usage_%": read_cpu_usage(),
            "memory":      read_memory(),
            "disk":        read_disk(),
            "uptime":      read_uptime(),
            "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with self._lock:
            self._stats = stats

    def _loop(self):
        while True:
            time.sleep(self._interval)
            self._refresh()

    def get(self):
        with self._lock:
            return dict(self._stats)


# ── HTTP handler ──────────────────────────────────────────────────────────────

collector = SystemStats(interval=2)


class MonitorHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def do_GET(self):
        if self.path == "/":
            self._serve_json(collector.get())
        elif self.path == "/health":
            self._serve_json({"status": "ok"})
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def _serve_json(self, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Entry point ───────────────────────────────────────────────────────────────

HOST = "0.0.0.0"
PORT = 8888

if __name__ == "__main__":
    print(f"System Monitor starting on {HOST}:{PORT}")
    print("Endpoints:")
    print(f"  GET /        → full stats JSON")
    print(f"  GET /health  → health check")

    server = HTTPServer((HOST, PORT), MonitorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
