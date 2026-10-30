# MIPI DSI for the rev3 ESP32-P4 boards and the JC1060P470 V2

ESPHome 2026.9.0's `esphome/components/mipi_dsi` (license alongside), for the boards built for rev3 ESP32-P4 silicon
that need it: the Guition JC8012P4A1 V3 (`packages/boards/guition-jc8012p4a1-v3.yaml`) and the Waveshare
ESP32-P4-WIFI6-Touch-LCD-7B (`packages/boards/wavesharep47b.yaml`), and for the Guition JC1060P470 V2
(`packages/boards/guition-jc1060p470-v2.yaml`), all `platform: mipi_dsi_v3`. It is a separate name so that no other
board picks it up: the first JC8012P4A1 and the first JC1060P470 keep ESPHome's own driver.

For the rev3 boards it differs from upstream in two lines. `mipi_dsi.cpp` leaves the DSI bus's `phy_clk_src` at zero,
so ESP-IDF picks the clock that suits the chip, and `display.py` names the platform `mipi_dsi_v3`. Upstream sets
`MIPI_DSI_PHY_CLK_SRC_DEFAULT`, which on the rev3 ESP32-P4 of the V3 board ends in an `abort()` while the display
starts, straight after the I2C bus recovery in the log, so the screen restarts until safe mode (GitHub #52,
esphome/esphome#19237).

It also squeezes a wider canvas into a panel whose pixels are not square: with `logical_width`, LVGL and the touch see a
display that many columns wide, `draw_pixels_at` keeps what LVGL drew in a canvas of that width (in PSRAM, RGB565
only) and blends every panel column from its two nearest canvas columns before it reaches the panel. The maths is in
`squeeze.h`, which `tests/test_squeeze.cpp` checks on the host. The Guition
JC1060P470 V2 (`packages/boards/guition-jc1060p470-v2.yaml`) uses it, 1074 columns for its 1024, so this folder stays
when the rev3 boards go back to upstream.

ESPHome's own fix is esphome/esphome#18984, merged for 2026.9.1. Once the app builds with that version and the board's
`min_version` asks for it, the rev3 boards go back to `platform: mipi_dsi`. The C++ keeps upstream's `mipi_dsi` namespace, so a comparison with a newer ESPHome is a plain diff.
