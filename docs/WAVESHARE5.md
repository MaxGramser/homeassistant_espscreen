# Waveshare ESP32-S3-Touch-LCD-5, 800 × 480

This is the **ESP32-S3-Touch-LCD-5** with 800 x 480 glass: the board of the
Waveshare 4.3-inch with a 5-inch IPS panel. Not the **5B**, which has 1024 x 600 glass and is not
supported.

Waveshare's own library (ESP32_Display_Panel) gives the 4.3-inch and the 5-inch the same RGB pins, the same panel
timings, the same GT911 touch on the same I2C bus and the same CH422G expander lines for the panel's reset, the touch
reset and the backlight. Both carry an ESP32-S3 with 16 MB flash and 8 MB of octal PSRAM. A 5-inch screen built from
the 4.3-inch package ran with picture, touch and the connection to Home Assistant working, which is why this board
starts as **new** and not experimental.

## Install

Update Tessera Screen Manager and choose **Waveshare · 5 inch** (ESP32-S3-Touch-LCD-5) in **New screen**. Follow
[Easy setup](EASY_SETUP.md) for the rest: the screen gets its own name, Wi-Fi references and unique API/OTA keys.

The remote package is `packages/waveshare5.yaml`; the checkout entry is `checkout/waveshare5.yaml`. Both combine
`packages/core.yaml` with `packages/boards/waveshare-esp32s3-5.yaml`, which takes its hardware from
`packages/hardware/waveshare-esp32s3-43.yaml`.

A 5-inch screen that already runs the 4.3-inch package keeps working. To have tiles and text at their intended size
on the larger glass, change `packages/waveshare43.yaml` to `packages/waveshare5.yaml` in the screen's own YAML and
install it again. The grid is three by three on both, so the layout keeps its cells.

## Layout and capabilities

- Lying down: 800 x 480, three columns of three cells, each tile about 34 x 14 mm.
- Standing up: 480 x 800, one column of five cells.
- The standard look at 186.6 dpi (933 diagonal pixels over 5 inches), so a tile, a letter and a key have the same
  size in millimetres as on every other board.
- GT911 reports pixels: no touch calibration.
- Camera pictures, snapshots on alerts and album covers, as on the 4.3-inch.
- The backlight is one line on the CH422G expander, lit or dark, and it stays lit
  (`features/backlight-always-on.yaml`): the 4.3-inch browns out when its backlight boost switches on again, and the
  5-inch lights its panel the same way. So there is no brightness, standby or night setting on this board.
