# Waveshare ESP32-S3-Touch-LCD-7, experimental

Added in app 0.2.110, firmware 0.2.94, for [issue #22](https://github.com/MaxGramser/homeassistant_espscreen/issues/22).
This is the **800 x 480 ESP32-S3-Touch-LCD-7**, with GT911 capacitive touch, 8 MB octal PSRAM and 8 or 16 MB flash.
It is not the 7B ([its own page](WAVESHARE7B.md)), the 7C or the version without touch. Physical acceptance has not been performed.

## Install

Update Tessera Screen Manager and choose **Waveshare · 7 inch** (ESP32-S3-Touch-LCD-7, marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys.
Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.
Keep an existing working profile if the board is already installed. Tessera adds it to Home Assistant by itself once it is on your Wi-Fi; then add its tiles.

The remote package is `packages/waveshare7.yaml`; the checkout entry is `checkout/waveshare7.yaml`.
Both combine `packages/core.yaml` with `packages/boards/waveshare-esp32s3-7.yaml`.
The 8 MB flash layout also fits a 16 MB board and leaves its additional flash unused.
Use the native USB connector for USB Serial/JTAG logs; the separate USB-to-UART connector is a different logging route.

## Layout and capabilities

- Landscape: 800 x 480, four columns of four cells. Portrait: 480 x 800, two columns of seven cells.
- Standard look at 133 dpi, following the existing physical size rules. The panel's non-square pixels are not compensated.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM implementation.
  Their operation on this board still needs physical verification. They are periodically refreshed images, not video playback.
- The unmodified backlight only switches on or off. The experimental profile keeps it on: no dimming, standby, night mode or alert flashes.
  The 4.3-inch board had brownouts on wake; that does not establish the same fault on this model. Standby remains disabled until tested.
  A board whose backlight has been rewired does dim: see [Dimming with the backlight mod](#dimming-with-the-backlight-mod).
- GT911 reports pixel coordinates, with no resistive calibration. The existing touch filter and action guard remain in use.
- LVGL uses a 12% draw buffer to leave internal RAM for networking and tile widgets.

## Dimming with the backlight mod

The stock backlight is one line on the CH422G expander (EXIO2): lit or dark, with no levels.
A hardware modification described by the Home Assistant community solders a wire from the backlight control pad to a free GPIO,
which can then drive the backlight with PWM. Both pins in use are reachable without opening the board:
GPIO6 on the sensor connector, or GPIO16 on the RS485 connector.
See the [community thread](https://community.home-assistant.io/t/esp32-s3-7inch-capacitive-touch-display-adjust-brightness/771030/10) for the pad and the wiring.

The firmware needs no new release for this. Every screen installed by Tessera keeps a small YAML file of its own that is
loaded after the shared package and survives app updates. Open the screen, press `···`, choose **Override YAML** (advanced)
and enter this, with `GPIO16` replaced by the pin the wire is soldered to:

```yaml
substitutions:
  BACKLIGHT_DIMMABLE: "true"

output:
  - id: !remove gpio_backlight_pwm
  - platform: ledc
    id: gpio_backlight_pwm
    pin: GPIO16
    frequency: 1000Hz
    min_power: 40%
    zero_means_zero: true

switch:
  - platform: output
    id: backlight_enable
    output: backlight_line
    restore_mode: ALWAYS_ON
    internal: true
```

Then press **Save & check**, which validates the complete profile, and **Update firmware** to rebuild and install.

- The PWM output takes over the id the shared backlight already uses, so the light, the brightness setting and every
  script stay as they are and reach a dimmer instead of a switch.
- The switch keeps EXIO2 high, which the panel needs to light at all. It stays out of Home Assistant.
- `min_power` maps the whole brightness setting onto the duty range the LED driver actually lights at. One board went dark
  below roughly 40 %; raise or lower the figure until the lowest setting is as dim as the board can go.
  `zero_means_zero` keeps a level of zero completely dark.
- From firmware 0.2.99 a screen reports what it can do (the **Screen features** sensor), so Tessera shows the
  brightness row for a modified board instead of reading it from its own table per board.
- Standby and night mode stay switched off on this board (`CAN_STANDBY`). With the mod the boost converter behind the LEDs
  stays powered and only the duty falls to zero, so the 4.3-inch brownout cannot occur in the same way, but that has not
  been measured. Adding `CAN_STANDBY: "true"` to the `substitutions:` of the same override turns standby and night
  back on. From app 0.2.131 that also brings the **Wake** and **Sleep** buttons and the standby and night settings back
  in Home Assistant; press **Update firmware** once after adding it.

Reported working on a board revision 1.1 with 8 MB flash by [@Cjdavidson](https://github.com/MaxGramser/homeassistant_espscreen/issues/22), who measured the mod and the dimming range.

## Hardware references

- [Waveshare specifications and pinout](https://docs.waveshare.com/ESP32-S3-Touch-LCD-7).
- [ESPHome MIPI RGB models](https://esphome.io/components/display/mipi_rgb/), model `ESP32-S3-TOUCH-LCD-7-800X480`.
- I2C: SDA GPIO8, SCL GPIO9. GT911 reset: CH422G EXIO1. LCD reset: EXIO3.
- EXIO2 supplies the backlight enable; EXIO6 enables the panel supply. The display owns EXIO6 and the backlight output owns EXIO2.
  The 7-inch model's own timings are used without the 4.3-inch overrides.

## What to report while testing

1. Board revision and flash size, successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts.
3. Physical taps near each corner, slider drags and edge swipes, in the selected orientation.
4. A full page of tiles, opening and closing the settings and detail cards, and the half-turn setting.
5. Camera tile pictures, full-screen camera images and camera alerts, including repeated opens and closes.
6. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.

Repeat the relevant checks after building the other orientation. Do not publish Wi-Fi passwords or API/OTA keys with logs.
The experimental release does not exercise standby or send commands to real Home Assistant devices as part of automated validation.
