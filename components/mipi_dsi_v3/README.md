# MIPI DSI for the ESP32-P4 boards on rev3 silicon

ESPHome 2026.9.0's `esphome/components/mipi_dsi` (license alongside), for every ESP32-P4 board on rev3 silicon. A board's
display says `platform: ${DSI_PLATFORM}`, and `packages/hardware/esp32p4-core.yaml` picks this one for a chip revision of
300 or higher and ESPHome's own `mipi_dsi` below it (`CHIP_REVISION`, docs/CHIP_REVISIONS.md). Pre-v3 boards keep the
driver they have always run.

It differs from upstream in two lines. `mipi_dsi.cpp` leaves the DSI bus's `phy_clk_src` at zero, so ESP-IDF picks the
clock that suits the chip, and `display.py` names the platform `mipi_dsi_v3`. Upstream sets
`MIPI_DSI_PHY_CLK_SRC_DEFAULT`, which on the rev3 ESP32-P4 of the V3 board ends in an `abort()` while the display
starts, straight after the I2C bus recovery in the log, so the screen restarts until safe mode (GitHub #52,
esphome/esphome#19237).

ESPHome's own fix is esphome/esphome#18984, merged for 2026.9.1. Once the app builds with that version and every P4
board's `min_version` asks for it, `DSI_PLATFORM` goes and every board takes `platform: mipi_dsi` again, and this folder
goes away. The C++ keeps
upstream's `mipi_dsi` namespace, so a comparison with a newer ESPHome is a plain diff.
