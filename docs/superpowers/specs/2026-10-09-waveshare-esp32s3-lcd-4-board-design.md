# Waveshare ESP32-S3-Touch-LCD-4 Board Template Design

## Goal

Create a Tessera-native lab board template for the non-B Waveshare ESP32-S3-Touch-LCD-4 in
`packages/boards/waveshare-esp32s3-lcd-4.yaml`.

This task does not add the board to `boards.yaml`, generate entry files, or publish permanent catalogue support.
Those steps wait until Tessera has been built, flashed, and accepted on the physical board.

## Source of Truth

The hardware values come from the verified standalone draft in
`packages/boards/waveshare-esp32s3-lcd-4-experiment.yaml` and the project handoff. The existing 4B profile supplies
Tessera structure and naming conventions only. Its TCA9554, ST7701S, pins, timings, and backlight wiring do not apply
to the non-B board.

## Template Structure

The board template will:

- include `hardware/esp32s3-rgb.yaml`;
- include the six-cell grid, standard look, capacitive-touch, backlight, camera, self-test, and snapshot features;
- report `BOARD_ID` as `wavesharelcd4`;
- use a 480 by 480 panel, 170 DPI, and a 2 by 3 grid;
- allow 128 tiles, 24 pages, 12 top-bar items, and a 25 percent LVGL buffer;
- require ESPHome 2026.7.0 or later for `waveshare_io_ch32v003`;
- retain 16 MB flash, octal PSRAM from the shared hardware package, and UART0 logging;
- retain the verified GPIO15/GPIO7 I2C bus and GPIO2/GPIO1 LCD setup SPI bus;
- retain the CH32V003 at address `0x24`;
- retain LCD power on expander pin 5, LCD reset on pin 3, touch reset on pin 1, touch interrupt on pin 2, and buzzer
  suppression on pin 6;
- retain the verified CH32V003 PWM limits, inversion, and LCD power dependency;
- retain the `WAVESHARE-4-480X480` ESPHome display model and its verified setup priority;
- retain GT911 polling at 20 ms and the verified 0 through 479 calibration.

Tessera-facing component IDs will follow repository contracts:

- display: `my_display`;
- touchscreen: `ts_touch`;
- backlight output: `gpio_backlight_pwm`;
- I2C bus: `touch_bus`;
- LCD setup SPI bus: `lcd`.

The shared backlight feature will own the light component. The template will not duplicate the draft's diagnostic
light, touch logging, display lambda, or test font.

## Boot and Safety Behavior

The template will not define `esphome.on_boot`, because that would replace Tessera core boot behavior. Board hardware
configuration will keep the buzzer control low without broad initialization of expander pins. In particular, it will
not recreate the earlier multi-pin startup sequence that caused a black screen, disabled backlight, and continuous
tone.

LCD power remains explicit and is enabled as a dependency of the backlight output, matching the verified draft.

## Validation

Validation is limited to repository checks that cover a standalone board template and its ESPHome package structure.
No result will be described as a physical Tessera test, flash, or hardware acceptance.

Permanent catalogue support, generated files, documentation for end users, and release notes remain out of scope.
