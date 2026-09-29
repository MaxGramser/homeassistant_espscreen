# LilyGO T-Display-S3-Long

Experimental support for the **Long** board, not the ordinary T-Display-S3 or the
T-Display-S3 AMOLED. Select **LilyGO / T-Display-S3-Long** in New screen. Its board
key is `lilygos3long`, and its remote package is `packages/lilygos3long.yaml`.
Update Tessera Screen Manager to 0.4.19 or later to see it in the catalog.
Version 0.4.21 includes the touch calibration reported working on this board.
Its header sits higher and the button grid starts at y=42 instead of roughly
y=55, leaving about 13 more pixels of height for the four buttons.
Version 0.4.22 fixes the effective touch transform and the native-axis
calibration required by this firmware's separate LVGL rotation.
Version 0.4.23 / firmware 0.12.0 places a lamp's colour, temperature and
brightness controls beside each other on this short landscape screen and
keeps a media player's volume row clear of its playback buttons.
Version 0.4.24 / firmware 0.13.0 expands temperature and brightness when the
lamp has no colour slider, and puts media volume beside finger-sized controls.

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
| Display reset | 16, owned by the display driver |
| Backlight PWM | 1 |
| Touch I2C SDA / SCL | 15 / 10 |
| CST3530 touch reset / interrupt | 2 / 11 |
| SY6970 PMU | I2C 0x6A on SDA 15 / SCL 10 |

The display uses ESPHome's `mipi_spi` model `AXS15231` at 10 MHz. The touch
controller is a **CST3530**. LilyGO's ESPHome example and the independent
EspControl board configuration both read it using ESPHome's `axs15231` I2C
touchscreen platform. That platform name does not identify the touch chip.
Touch is polled, so the separate GPIO2 reset and GPIO11 interrupt are not
configured in this profile.
The raw touch bounds (X 10..627, Y 6..176) come from a working board
configuration. In this firmware touch is mapped to the panel's native
180 x 640 space before LVGL rotates it 90 degrees. The board therefore swaps
the axes, uses calibration x 6..176 and y 10..627, and mirrors the native Y
axis. These transform values must be set as board substitutions because the
shared core extends the touchscreen with its own transform fields.
Rotation belongs to LVGL, because the panel cannot swap axes in hardware.

The board sets `full_refresh: true`, a 100% LVGL buffer, and `draw_rounding: 4`
on **both** the display and LVGL. ESPHome 2026.9 takes the maximum of the two
rounding values, and the AXS15231 model defaults to 8, which does not divide 180.
Do not lower the buffer while full refresh is enabled. These settings avoid the
partial-window and edge corruption described by LilyGO's example.

The **SY6970** battery charger/PMU shares the I2C bus at address `0x6A`.
USB-powered operation is the initial target. The PMU component is deliberately
not enabled yet: ESPHome's built-in `sy6970` writes charge voltage, current and
enable settings during setup, and EspControl uses a patched version to service
the chip's I2C watchdog. Copying its charge settings without checking the
battery and the board would alter charging. Battery status, charging control
and OTG power output therefore require a separate hardware-validated change.

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
The [EspControl Long board definition](https://github.com/willumpie82/espcontrol/blob/add-lilygo-t-display-s3-long/devices/lilygo-t-display-s3-long/device/device.yaml)
also identifies the CST3530 and SY6970 and documents its PMU watchdog workaround.
