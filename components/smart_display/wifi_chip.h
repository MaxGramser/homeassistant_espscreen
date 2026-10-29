// The Wi-Fi co-processor of an ESP32-P4 screen: an ESP32-C6 on SDIO through esp_hosted (hardware/esp32p4-c6.yaml,
// hardware/m5stack-tab5.yaml).
//
// A restart is a whole-system reset. On the P4, ESP-IDF's esp_restart() resets only the two CPUs, the DMAs, the flash
// bus and the crypto blocks (esp_restart_noos in esp_system/port/soc/esp32p4/system_internal.c), not the SDIO host the
// C6 hangs on. Now and then that link came out of a restart stuck: "ESP-Hosted link not yet up",
// "sdmmc_host_wait_for_event returned 0x107", "sdio_read_task: Failed to read data - -1 838860 838860" (a packet
// length read as 0xCCCCC, espressif/esp-hosted-mcu #240), esp_hosted restarted the P4 after 13 s with the same CPU
// reset, and so on until the power went off; the bootloader's rollback to the previous firmware looped the same way,
// safe mode included. On the bench Guition V3 about one restart in five did that (2026-10-26); holding the C6 itself in
// reset for ten seconds at every start did not help once it was stuck, and a hardware reset of the P4 always did. An
// M5Stack Tab5 elsewhere showed the same, and every restart through esp_rom_software_reset_system() cured it
// (SimmoDev/homedeck #8, some 2000 restarts).
// So a shutdown handler, registered before anything else and so run after every other one, ends every esp_restart()
// (an update, ESPHome's restart, esp_hosted's own after a failed link) in that reset of the whole digital system. A
// crash still restarts the CPUs only (ESP-IDF's panic path calls no handler); a link it leaves stuck costs one more
// start, which esp_hosted's restart then ends in the whole reset.
//
// Its firmware. The C6 keeps its own, which flashing the P4 never changes. firmware() asks it once, with Wi-Fi up, logs
// it and gives it to the "Wi-Fi co-processor" sensor (hardware/esp32p4-core.yaml), which the troubleshooting report
// reads, so the reports tell which C6 firmwares the screens out there run.
#pragma once

#include <string>

namespace wifi_chip {

// What the co-processor runs, "ESP-Hosted 2.3.2 (host 2.12.12)"; "unknown" while Wi-Fi is not up yet, and on a screen
// without one. The first call with Wi-Fi connected asks the C6 (one RPC over the link); every later one gives that.
std::string firmware();

}  // namespace wifi_chip
