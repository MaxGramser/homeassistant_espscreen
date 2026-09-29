# LilyGO T-Display-S3-Long

Experimental support for the **Long** board, not the ordinary T-Display-S3 or the
T-Display-S3 AMOLED. Select **LilyGO / T-Display-S3-Long** in New screen. Its board
key is `lilygos3long`, and its remote package is `packages/lilygos3long.yaml`.
Update Tessera Screen Manager to 0.4.19 or later to see it in the catalog.

The 3.4-inch panel has 180 x 640 native pixels, an ESP32-S3, 16 MB flash and 8 MB
of octal PSRAM. Landscape uses a 640 x 180 canvas with four cells across;
portrait has four cells down. Both use the compact look, capacitive touch,
PWM backlight and the shared settings and page system. Camera images are not
enabled on this profile while their layout on narrow glass remains unverified.
The narrow glass is best suited to short tile names and simple controls.

## Hardware

| Function | GPIO |
|---|---|
| QSPI clock | 17 |
| QSPI data 0 / 1 / 2 / 3 | 13 / 18 / 21 / 14 |
| Display chip select | 12 |
| Shared display/touch reset | 16, owned by the display driver |
| Backlight PWM | 1 |
| Touch I2C SDA / SCL | 15 / 10 |

The display uses ESPHome's `mipi_spi` model `AXS15231` at 10 MHz and the
`axs15231` touch driver. Touch is polled; GPIO11 is not needed for polling.
The raw touch calibration and mirrors follow the manufacturer's ESPHome example.
Rotation belongs to LVGL, because the panel cannot swap axes in hardware.

The board sets `full_refresh: true`, a 100% LVGL buffer, and `draw_rounding: 4`
on **both** the display and LVGL. ESPHome 2026.9 takes the maximum of the two
rounding values, and the AXS15231 model defaults to 8, which does not divide 180.
Do not lower the buffer while full refresh is enabled. These settings avoid the
partial-window and edge corruption described by LilyGO's example.

USB-powered operation is the initial target. Battery charging, PMU controls and
OTG power output are not configured by this profile.

## Before calling the board hardware-tested

- Boot over USB, confirm Wi-Fi and the Home Assistant API connect, and receive a layout.
- Check solid colours and all four edges for corruption; switch pages repeatedly.
- In landscape and portrait, use the touch test to check all corners, centre and drags.
  Confirm that tapping each of the four tiles selects only that tile.
- Check brightness at 100%, 50%, 10% and off, then wake from standby.
- Open settings, a light control, a weather card. Check text clipping
  on this unusually narrow canvas, in both orientations.
- Verify a restart and OTA update preserve pairing, rotation and the stored layout.

A successful configuration check or build does not establish physical acceptance.

## Sources

The pin map, panel settings and touch transform follow the
[LilyGO manufacturer repository](https://github.com/Xinyuan-LilyGO/T-Display-S3-Long)
at commit `3deece89098f25e7d155e41e4e0f5dd8b368ab02`, particularly
[the ESPHome example](https://github.com/Xinyuan-LilyGO/T-Display-S3-Long/blob/3deece89098f25e7d155e41e4e0f5dd8b368ab02/examples/ESPHome_LVGL_HelloWorld/esphome-lvgl-hello-world.yaml)
and `examples/GFX_AXS15231B_Image/pins_config.h`.
