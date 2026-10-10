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

The landscape grid starts with three rows of tiles; the Grid button beside the pages in the editor gives it more, up to
five by five, without a new build (firmware 0.53.0+). Every grid takes up to 64 tiles across eight pages; the last page
may be partly filled. Standing up it starts on one column of five rows.

Camera tiles, live camera pictures, full-screen camera views, camera alerts and media artwork are enabled. Add a camera
entity to a screen tile to use these features.

The INA226 battery monitor exposes **Battery Voltage** as a diagnostic sensor and **Battery Level** as a percentage
sensor in Home Assistant. The percentage is an estimate from the 2-cell lithium-ion pack voltage, using a piecewise
voltage curve from 6.0 V (empty) to 8.4 V (full); voltage changes under load or while charging can affect the estimate.

The battery shows in the top bar from firmware 0.41.0, with Home Assistant's icon for its level and while it charges
(**Add → Battery** in the editor). **Battery Charging** is on while more than 50 mA flows into the pack, from the same
INA226, and **Battery Current** shows that current. docs/BATTERY.md has the details.

The ESP32-C6 that does the Wi-Fi and the battery charger get their power from the second I/O expander (address 0x44),
which starts with every output off. The firmware switches on its Wi-Fi power (P0), quick charge (P5) and charge enable
(P7) at boot, as M5Stack's own firmware does. Without the Wi-Fi power output, the screen only finds its network while
an earlier firmware left the C6 powered, and after a cold start it stops at `esp_wifi_init failed: ESP_FAIL`.

After flashing, confirm that the screen boots, has a stable picture with correct colors, responds at the four corners
and across the surface, changes pages, pairs with Home Assistant, and remains working after a restart and a cold start.
Check the USB log and report the firmware and board variant with the results.

## Speaker and microphones

The speaker (an ES8388) and the two microphones (an ES7210) are the screen's audio through `features/audio.yaml`: a
media player in Home Assistant for announcements, text to speech and music, a **Volume** and a **Microphone** setting
under Extras (on the screen and in Screen settings), and the speaker and microphone that plugins use, such as the voice
assistant and Tap sound. As ESPHome's own Tab5 configuration does, both codecs share one I2S bus, which ESPHome lets
them take in turns, so the board sets `AUDIO_HALF_DUPLEX`: the speaker lets go of the bus after a sound, the amplifier
(SPK_EN on the first I/O expander) is on only while sound plays, and the microphone pauses while the media player plays.
The volume runs evenly in decibels from -45 dB to the ES8388's full scale.

## Camera

The 2 MP camera on the MIPI-CSI port answers on the system I2C bus and takes its 24 MHz clock from GPIO36, as M5Stack's
own firmware drives it. The board states both (`CAMERA_I2C`, `CAMERA_XCLK_PIN`, the feature `camera_sensor`), and the
Screen camera plugin makes it a camera of the screen's device in Home Assistant.

## Built, not yet heard or seen

The audio and the camera are built for this board on the `dev` branch but have not run on a Tab5 yet. To try them,
install the app from the `#dev` repository URL (docs/RELEASING.md, "Testing dev"), update the screen, and add the
plugins. Then report:

1. an announcement or text to speech from Home Assistant on the screen's media player, at a few volumes;
2. the Volume and Microphone rows under Extras, on the screen and in Screen settings;
3. with the Voice assistant plugin: the wake word, a question and its spoken answer;
4. with the Screen camera plugin: a picture and the live view in Home Assistant, and the camera in the top bar;
5. the USB log of the first start, which says whether the camera's sensor was found.

## Hardware references

- [M5Stack Tab5 product page](https://shop.m5stack.com/products/m5stack-tab5-iot-development-kit-esp32-p4)
- [ESPHome MIPI-DSI display](https://esphome.io/components/display/mipi_dsi/)
- [ESPHome ST7123 touchscreen](https://esphome.io/components/touchscreen/st7123/)
- [Community ESPHome configuration](https://github.com/Axellum/M5-Tab5-ESPHome-LVGL)
- [ESPHome's Tab5 configuration](https://devices.esphome.io/devices/m5stack-tab5) (the audio pins and codecs)
- [M5Stack's Tab5 BSP](https://github.com/m5stack/M5Tab5-UserDemo) (`m5stack_tab5.h`, `m5stack_tab5.c`: the I2S pins and
  the camera's clock)
