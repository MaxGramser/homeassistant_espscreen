# M5Stack Tab5, ST7121 variant

This profile supports only the M5Stack Tab5 variant whose factory firmware reports:

```text
Detected ST7121 touch controller (FW version: 1), using ST7121 display
```

The reported unit has an ESP32-P4 eco2 at chip revision v1.3, 16 MB SPI flash and 32 MB PSRAM. The screen is 720 × 1280
pixels, used as a 1280 × 720 landscape layout. The profile selects ESPHome's `M5STACK-TAB5-ST7121` MIPI-DSI model.
Other Tab5 display and touch variants are not covered. A profile for the wrong display variant can leave the screen
blank, so check the factory log before choosing it.

## Install and test

The Tab5 is listed as a new board after successful hardware testing. In **New screen**, choose **M5Stack Tab5**, model
**Tab5 ST7121**. Other Tab5 display and touch variants are not covered by this hardware confirmation.

The display uses the explicit ST7121 model. ESPHome's available touch platform is named `st7123`; it is configured
here for the ST7121 controller using the community reference. This profile has been tested with the ST7121 variant;
other Tab5 display and touch variants still need to be checked on glass.

In Tessera, the screen's board label comes from its **Screen board** diagnostic and should identify the Tab5 (`tab5`).
If it identifies another board, such as the CYD, reinstall the screen using the **Tab5 ST7121** profile so its firmware
reports the correct board.

The landscape grid defaults to three rows of tiles. In **New screen**, choose four rows to fit more, smaller tiles on a
page. Both grid choices support up to 64 tiles across eight pages; the last page may be partly filled. The portrait
grid remains one column by five rows.

Camera tiles, live camera pictures, full-screen camera views, camera alerts and media artwork are enabled. Add a camera
entity to a screen tile to use these features.

The INA226 battery monitor exposes **Battery Voltage** as a diagnostic sensor and **Battery Level** as a percentage
sensor in Home Assistant. The percentage is an estimate from the 2-cell lithium-ion pack voltage, using a piecewise
voltage curve from 6.0 V (empty) to 8.4 V (full); voltage changes under load or while charging can affect the estimate.

After flashing, confirm that the screen boots, has a stable picture with correct colors, responds at the four corners
and across the surface, changes pages, pairs with Home Assistant, and remains working after a restart and a cold start.
Check the USB log and report the firmware and board variant with the results.

## Hardware references

- [M5Stack Tab5 product page](https://shop.m5stack.com/products/m5stack-tab5-iot-development-kit-esp32-p4)
- [ESPHome MIPI-DSI display](https://esphome.io/components/display/mipi_dsi/)
- [ESPHome ST7123 touchscreen](https://esphome.io/components/touchscreen/st7123/)
- [Community ESPHome configuration](https://github.com/Axellum/M5-Tab5-ESPHome-LVGL)
