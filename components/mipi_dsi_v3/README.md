# MIPI DSI for the JC8012P4A1 V3

ESPHome 2026.9.0's `esphome/components/mipi_dsi` (license alongside), for the Guition JC8012P4A1 V3 alone
(`packages/boards/guition-jc8012p4a1-v3.yaml`, `platform: mipi_dsi_v3`). It is a separate name so that no other board
picks it up: the first JC8012P4A1 and the JC1060P470 keep ESPHome's own driver.

It differs from upstream in two lines. `mipi_dsi.cpp` leaves the DSI bus's `phy_clk_src` at zero, so ESP-IDF picks the
clock that suits the chip, and `display.py` names the platform `mipi_dsi_v3`. Upstream sets
`MIPI_DSI_PHY_CLK_SRC_DEFAULT`, which on the rev3 ESP32-P4 of the V3 board ends in an `abort()` while the display
starts, straight after the I2C bus recovery in the log, so the screen restarts until safe mode (GitHub #52,
esphome/esphome#19237).

ESPHome's own fix is esphome/esphome#18984, merged for 2026.9.1. Once the app builds with that version and the board's
`min_version` asks for it, the board goes back to `platform: mipi_dsi` and this folder goes away. The C++ keeps
upstream's `mipi_dsi` namespace, so a comparison with a newer ESPHome is a plain diff.
