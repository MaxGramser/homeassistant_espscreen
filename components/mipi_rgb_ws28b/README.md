# MIPI RGB for the Waveshare ESP32-S3-Touch-LCD-2.8B

ESPHome 2026.9.0's `esphome/components/mipi_rgb` (license alongside), for the Waveshare ESP32-S3-Touch-LCD-2.8B alone
(`packages/boards/waveshare28b.yaml`, `platform: mipi_rgb_ws28b`). It is a separate name so that no other board picks it
up: every other RGB board keeps ESPHome's own driver.

It differs from upstream in one option. `display.py` takes `send_colmod` (true by default, as upstream), and with
`send_colmod: false` it leaves COLMOD (0x3A) out of the init sequence it builds; `__init__.py` names the platform
`mipi_rgb_ws28b`. Upstream always appends COLMOD after the board's own init sequence, 0x55 for `pixel_mode: 16bit` and
0x66 for `18bit`. With either, this panel reads the sixteen RGB lines shifted: a test page of single bits showed the top
bits of every channel dark, gradients repeating and greys turning green or purple, whatever order the data pins were
given in, with or without COLCTRL (0xCD 0x08). Waveshare's own example for the board (Arduino `Display_ST7701.cpp`)
sends no COLMOD, and the panel keeps its power-on format; without 0x3A the same test page shows smooth gradients and
neutral greys, with Waveshare's pin order.

If ESPHome gets a way to leave COLMOD out (or to send the panel's own value), the board goes back to
`platform: mipi_rgb` and this folder goes away. The C++ is upstream's, unchanged, in upstream's `mipi_rgb` namespace,
so a comparison with a newer ESPHome is a plain diff.
