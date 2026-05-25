SUMMARY = "Python system monitor for Raspberry Pi"
DESCRIPTION = "Reads CPU temp, memory, CPU usage, disk and serves them as JSON over HTTP on port 8888"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://system_monitor.py"

S = "${WORKDIR}"

# No build step needed for Python
do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/system_monitor.py ${D}${bindir}/system-monitor
}

# Only needs Python3 — no extra packages (uses stdlib only)
RDEPENDS:${PN} = "python3"