# Freenove FNK0104B, 2.8 inch, experimental

The **Freenove FNK0104B** is a 2.8-inch ESP32-S3 display with a 240 x 320 ILI9341 panel and capacitive touch. Freenove
lists 16 MB flash and 8 MB PSRAM for this display series. The profile is **experimental** because it has not yet been
built and accepted on a physical FNK0104B.

## Install

Update Tessera Screen Manager and choose **Freenove · 2.8 inch, FNK0104B** (marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create the screen profile and flash it over USB.

The remote package is `packages/freenovefnk0104b.yaml` and the checkout entry is `checkout/freenovefnk0104b.yaml`.
Both combine `packages/core.yaml` with `packages/boards/freenovefnk0104b.yaml`.

## Layout and capabilities

- The panel is 240 x 320. Tessera lays it down at 320 x 240 with a 90-degree LVGL rotation, using a 2 x 3 grid. Standing
  up, the grid is 1 x 4. The compact look is scaled to about 143 dpi.
- The profile uses ESPHome's ILI9341 SPI driver, the series' GPIO12 clock, GPIO11 data, GPIO10 chip select and GPIO46
  data/command line. It sets a 40 MHz SPI rate, BGR colour order and colour inversion. Confirm the rate, colours and
  inversion on the glass before treating them as accepted hardware values.
- Capacitive FT6336 touch uses GPIO16 SDA, GPIO15 SCL, GPIO17 interrupt and GPIO18 reset. It reports pixels and needs no
  calibration.
- GPIO45 drives the dimmable backlight at 20 kHz. Brightness, standby, night mode, Wake and Sleep are enabled.
- The 8 MB PSRAM enables camera and snapshot pictures from Home Assistant. The board profile does not enable an
  on-board camera sensor.
- The ES8311 codec provides the speaker and microphone. The codec shares the touch controller's I2C bus. The profile
  uses I2S MCLK GPIO4, BCLK GPIO5, microphone data GPIO6, speaker data GPIO8 and LRCLK GPIO7. Its speaker amplifier
  enable is GPIO1 and is configured active low. The mic bus supplies clocks to the secondary speaker bus so both audio
  directions can run together. The media player volume and microphone switch appear under Screen settings and in the
  add-on's screen settings.
- The optional battery connector is measured on GPIO9 through a 2:1 voltage divider. The generic battery level curve
  has not been calibrated against an FNK0104B battery. No charging-state signal is configured.
- One addressable WS2812 on GPIO42 is exposed to Home Assistant as **Status LED**, in GRB channel order.

These pins and component choices follow Freenove's FNK0104 examples and the shared FNK0104 series wiring. The ILI9341
colour settings, audio and battery reporting, touch mapping, backlight dimming, and both screen orientations still need
physical acceptance.

## Hardware references

- [Freenove FNK0104 model and display details](https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN/Freenove_ESP32S3_Display.html)
- [Freenove touch example](https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN/12_TFT_Touch_Drawing.html)
- [Freenove audio example and I2S pins](https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN/7_Music.html)
- [Freenove battery voltage example](https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN_NonTouch/5_Battery_Voltage.html)
- [Freenove RGB LED example](https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN_NonTouch/3_Button.html)
- [Freenove product page](https://store.freenove.com/products/fnk0104)
- [ESPHome mipi_spi display](https://esphome.io/components/display/mipi_spi/)

## What to report while testing

1. Boot, Wi-Fi and Home Assistant pairing, with a layout across a few pages.
2. Correct colours and rotation lying down and standing up.
3. Touch near each corner, slider drags and edge gestures in both orientations.
4. Backlight levels, standby, wake by touch and night mode.
5. Camera and snapshot pictures, the Status LED, speaker playback, microphone input and the battery reading.
6. Heap and PSRAM use with a full layout, any restart or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
