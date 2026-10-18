# Freenove FNK0104S, 480 x 320

The **Freenove FNK0104S** is a 4-inch ESP32-S3 display with a native 320 x 480 ST7796 panel over SPI and
FT63X6 capacitive touch over I2C. Tessera runs it landscape at 480 x 320 with a 90-degree rotation. The
board has 16 MB flash and octal PSRAM.

## Install

After this board is released, update Tessera Screen Manager and choose **Freenove, 4 inch** in **New screen**.
Tessera creates a screen profile with its own name, Wi-Fi settings, and API and OTA keys. Build the firmware there
and flash it over USB, following [Easy setup](EASY_SETUP.md).

The remote package is `packages/freenovefnk0104s.yaml`; a checkout uses
`checkout/freenovefnk0104s.yaml`. Both combine `packages/core.yaml` with
`packages/boards/freenovefnk0104s.yaml`.

## Layout and hardware

- Landscape: 480 x 320, two columns by two rows. Portrait: 320 x 480, one column by four rows.
- ST7796 over SPI: CLK GPIO12, MOSI GPIO11, DC GPIO46 and CS GPIO10.
- FT63X6 capacitive touch over I2C: SDA GPIO16, SCL GPIO15, interrupt GPIO17 and reset GPIO18.
- Backlight: GPIO45 PWM at 20 kHz. It is dimmable, so brightness, standby and night mode are available.
- Standard look at 144 dpi. The 12% LVGL buffer and board PSRAM allow up to 128 tiles over 24 pages.

GPIO45 and GPIO46 are ESP32-S3 strapping pins. ESPHome warns about them, but they are the board's wired
backlight and display-control pins.

## Bench result

An offline firmware image built from this board profile booted on an FNK0104S. The touch test recorded the center
and all four physical corners in the expected 480 x 320 landscape coordinates. Physical testing also confirmed that
the ST7796 needs inverted colours for its light and dark looks to render correctly. The board remains **experimental**:
Home Assistant pairing, a real tile layout, dimming and standby, and portrait operation still need testing on glass.

## References

- [Freenove FNK0104S display documentation](https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN/Freenove_ESP32S3_Display.html)
- [ESPHome mipi_spi display component](https://esphome.io/components/display/mipi_spi/)
