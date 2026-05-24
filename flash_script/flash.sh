#!/bin/bash

# --- 1. CONFIGURATION ---
POKY_DIR="/home/mahmoud/Desktop/yocto/poky"
BUILD_DIR="$POKY_DIR/build"
IMAGE_NAME="core-image-minimal"
MACHINE="raspberrypi3-64"

# Flash Locations
IMAGE_PATH="$BUILD_DIR/tmp/deploy/images/$MACHINE/$IMAGE_NAME-$MACHINE.wic.bz2"
BMAP_PATH="$BUILD_DIR/tmp/deploy/images/$MACHINE/$IMAGE_NAME-$MACHINE.wic.bmap"
TARGET_DRIVE="/dev/sdb"

# --- 2. PRE-CHECKS ---
if [ "$EUID" -ne 0 ]; then 
  echo "Error: Please run as root (sudo)"
  exit 1
fi

# --- 3. BITBAKE SECTION ---
echo "Starting Yocto Build for $IMAGE_NAME..."

# We must run bitbake as a normal user, but the script is running as root.
# We use 'su' to drop privileges for the build, as bitbake will fail if run as root.
sudo -u mahmoud bash <<EOF
    cd $POKY_DIR
    source oe-init-build-env $BUILD_DIR
    bitbake $IMAGE_NAME
EOF

# Check if build succeeded
if [ $? -ne 0 ]; then
    echo "Build failed! Aborting flash."
    exit 1
fi

# --- 4. FLASH SECTION ---
echo "Build Successful. Preparing to flash..."

# Verify files exist
if [ ! -f "$IMAGE_PATH" ]; then
    echo "Error: Image file not found at $IMAGE_PATH"
    exit 1
fi

# Install bmaptool if missing
if ! command -v bmaptool &> /dev/null; then
    apt-get update && apt-get install -y bmap-tools
fi

echo "Unmounting $TARGET_DRIVE..."
umount ${TARGET_DRIVE}* 2>/dev/null

echo "Flashing $IMAGE_NAME to $TARGET_DRIVE (using bmaptool)..."
bmaptool copy "$IMAGE_PATH" "$TARGET_DRIVE" --bmap "$BMAP_PATH"

echo "------------------------------------------------"
echo "Flash complete! You can now boot your Pi."