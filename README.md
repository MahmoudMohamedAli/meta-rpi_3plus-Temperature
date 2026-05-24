# meta-mylayer

A Yocto BSP layer for Raspberry Pi 3B that provides TFTP/NFS network boot configuration and builds the Temperature Monitor application into the image.

## Overview

This layer extends the standard `meta-raspberrypi` layer with:
- U-Boot configured to fetch kernel and DTB over TFTP
- NFS rootfs support for fast development iterations
- Temperature Monitor application recipe

## Dependencies

| Layer | Branch |
|---|---|
| `poky` | kirkstone |
| `meta-raspberrypi` | kirkstone |
| `meta-openembedded/meta-oe` | kirkstone |

## Layer Structure

```
Local.conf

meta-mylayer/
├── conf/
│   └── layer.conf
├── recipes-bsp/
│       └── rpi-u-boot-scr/
│           ├── rpi-u-boot-scr.bbappend
│           └── files/
│               └── boot.cmd.in          ← U-Boot TFTP boot script
├── recipes-temperature-monitor/
│   └── temperature-monitor/
│       └── temperature-monitor.bb       ← App recipe
└── README.md
```

## Quick Setup

### 1. Clone all layers

```bash
git clone https://github.com/MahmoudMohamedAli/meta-rpi_3plus-Temperature.git
```

### 2. Initialize build environment

```bash
cd poky
source oe-init-build-env build
```

### 3. Add layers

```bash
bitbake-layers add-layer ../../meta-rpi_3plus-Temperature
```

### 4. Replace your build/conf/local.conf with the one in the repo

```bitbake
# Target machine
MACHINE = "raspberrypi3-64"

# Include temperature monitor and required libraries
IMAGE_INSTALL:append = " temperature-monitor libstdc++ libgcc nfs-utils"

# Enable UART for serial console
ENABLE_UART = "1"

# Enable U-Boot
RPI_USE_U_BOOT = "1"

# Optional: systemd
#DISTRO_FEATURES:append = " systemd"
```

### 5. Build

```bash
bitbake core-image-minimal
```

### 6. Flash SD card

- use the Bash script to flash image [flasher](flash_script/flash.sh)
- Note: make sure to Read the Bash script to change the paths and device name "default: /dev/sdb" which mapped to SD card

---

## Network Boot Setup (TFTP + NFS)

This layer configures U-Boot to fetch the kernel and DTB from a TFTP server on your PC, with the rootfs served over NFS — no reflashing needed during development.

### Network topology

```
PC (10.42.0.1)                  Raspberry Pi (10.42.0.3)
├── TFTP server (:69)    <───   U-Boot fetches Image + DTB
├── NFS server (:2049)   <───   Kernel mounts rootfs
└── /srv/nfs/rpi/               Rootfs lives here
```

### PC Setup

#### Install servers

```bash
sudo apt install tftpd-hpa nfs-kernel-server
```

#### Configure TFTP

```bash
# /etc/default/tftpd-hpa
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="/tftpboot"
TFTP_ADDRESS="0.0.0.0:69"
TFTP_OPTIONS="--secure"

sudo mkdir -p /tftpboot
sudo chmod 777 /tftpboot
sudo systemctl restart tftpd-hpa
```

#### Copy kernel and DTB to TFTP folder

```bash
sudo cp tmp/deploy/images/raspberrypi3-64/Image /tftpboot/
sudo cp tmp/deploy/images/raspberrypi3-64/bcm2710-rpi-3-b.dtb /tftpboot/
sudo chmod 644 /tftpboot/*
```

#### Configure NFS

```bash
# /etc/exports
/srv/nfs/rpi  10.42.0.3(rw,sync,no_subtree_check,no_root_squash)
```

```bash
sudo mkdir -p /srv/nfs/rpi
sudo tar -xjf tmp/deploy/images/raspberrypi3-64/core-image-minimal-raspberrypi3-64.tar.bz2 \
  -C /srv/nfs/rpi
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
```

#### Set static IP on ethernet interface

```bash
sudo ip addr add 10.42.0.1/24 dev enp5s0
```

### Boot sequence

```
SD card → Firmware → U-Boot
                        ↓
              TFTP fetch: Image
              TFTP fetch: bcm2710-rpi-3-b.dtb
                        ↓
              Kernel boots
                        ↓
              NFS mount: 10.42.0.1:/srv/nfs/rpi
                        ↓
              Login prompt
```

### Development workflow with NFS

Since the rootfs is on your PC you can update it instantly without reflashing:

```bash
# Rebuild app
bitbake temperature-monitor

# Copy new binary directly to NFS rootfs
sudo cp ttmp/work/raspberrypi3_64-poky-linux/core-image-minimal/1.0-r0/rootfs/usr/bin/temperature-monitor  \
  /srv/nfs/rpi/usr/bin/

# On RPi — run immediately, no reboot needed
temperature-monitor
```

---

## U-Boot Boot Script

The `boot.cmd.in` file configures U-Boot to:

1. Set server and board IPs
2. Fetch kernel via TFTP
3. Fetch DTB via TFTP
4. Set kernel boot arguments
5. Boot the kernel

```bash
setenv serverip 10.42.0.1
setenv ipaddr   10.42.0.3

tftpboot ${kernel_addr_r} @@KERNEL_IMAGETYPE@@
tftpboot ${fdt_addr_r}    bcm2710-rpi-3-b.dtb

setenv bootargs "8250.nr_uarts=1 console=ttyS0,115200 console=ttyAMA0,115200 \
  console=tty1 root=/dev/nfs nfsroot=10.42.0.1:/srv/nfs/rpi,v3,tcp \
  rw ip=10.42.0.3:10.42.0.1:10.42.0.1:255.255.255.0::eth0:off loglevel=8"

@@KERNEL_BOOTCMD@@ ${kernel_addr_r} - ${fdt_addr_r}
```

---

## Temperature Monitor App

The layer includes a recipe for the Temperature Monitor application:

- **Source**: https://github.com/MahmoudMohamedAli/Temperature_Monitor_UML
- **Install path**: `/usr/bin/temperature-monitor`
- **Port**: `8080`

```bash
# Run on RPi
temperature-monitor

# Query from PC
curl http://10.42.0.3:8080
# temperature=45.234C
```

---

## Maintainer

Mahmoud Elkot

## License

MIT
