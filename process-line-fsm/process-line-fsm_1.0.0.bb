# recipes-supernovia/process-line-fsm/process-line-fsm_1.0.bb

SUMMARY = "Process Line Controller — Raspberry Pi FSM"
DESCRIPTION = "Asyncio-based conveyor belt FSM controller with GPIO support"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://process_line_fsm.py \
           file://fsm_diagram.html "

S = "${WORKDIR}"

# Runtime dependency 
RDEPENDS:${PN} = "python3 "

do_install() { 
    # Install the Python script
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/process_line_fsm.py ${D}${bindir}/process-line-fsm
    
    # Install the HTML diagram
    install -d ${D}${datadir}/process-line-fsm
    install -m 0644 ${WORKDIR}/fsm_diagram.html ${D}${datadir}/process-line-fsm/
}

FILES:${PN} += "${datadir}/process-line-fsm "