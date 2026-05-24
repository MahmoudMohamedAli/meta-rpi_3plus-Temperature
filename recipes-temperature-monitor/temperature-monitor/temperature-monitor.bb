SUMMARY = "Temperature Monitor application for Raspberry Pi"
DESCRIPTION = "Reads CPU temperature from sysfs and exposes it over HTTP on port 8080"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "git://github.com/MahmoudMohamedAli/Temperature_Monitor_UML.git;branch=main;protocol=https"
SRCREV = "b8438726c806232209c7ce7fef285024e2ad27f0"

# S points to the source directory after fetch
S = "${WORKDIR}/git"

# Inherit cmake build system
inherit cmake

# Pass build type to cmake
EXTRA_OECMAKE = "-DCMAKE_BUILD_TYPE=Release"

# Install binary into the image
do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${B}/temperature-monitor ${D}${bindir}/temperature-monitor
}
