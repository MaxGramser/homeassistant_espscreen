# Waveshare ESP32-S3-Touch-LCD-4B, experimental

Added in app 0.2.126, firmware 0.2.102.
This is the **ESP32-S3-Touch-LCD-4B**: a 4-inch 480 x 480 IPS panel with an ST7701S driver over RGB, GT911 capacitive
touch, 8 MB octal PSRAM and 16 MB flash. It is not the older ESP32-S3-Touch-LCD-4 without the "B", which has other pins
(its revision 4.0 has a board file of its own: [WAVESHARE4V4.md](WAVESHARE4V4.md)).
Physical acceptance has not been performed.

Up to firmware 0.3.9 this board started without its tiles: a light page with only the page buttons, and every save
answered with "Use the Easy Setup profile". Its board file had a boot step of its own that replaced the shared boot
steps (docs/PROFILES.md, "Which value wins"). Firmware 0.3.10 removed that step, and from then until 0.6.1 the panel
only drew after a restart that kept the board powered: after a cold start the backlight lit a black screen while touch
worked. ESPHome's software SPI claims the panel's setup lines before the expander starts, and the expander starts with
every line an input, so the setup never reached the panel (ESPHome issue #11748). Firmware 0.6.1 parks those lines
with three outputs that start after the expander and before the display, and keeps the shared boot steps. Update such
a screen to 0.6.1 or later.

## Install

Update Tessera Screen Manager and choose **Waveshare · 4 inch** (ESP32-S3-Touch-LCD-4B, marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys.
Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.
Keep an existing working profile if the board is already installed. Tessera adds it to Home Assistant by itself once it is on your Wi-Fi; then add its tiles.

The remote package is `packages/waveshare4b.yaml`; the checkout entry is `checkout/waveshare4b.yaml`.
Both combine `packages/core.yaml` with `packages/boards/waveshare-esp32s3-4b.yaml`.
The board has two USB-C ports. Logs go out over the one with the USB-to-UART chip, as on the 4-inch Guition.
The audio-enabled profile requires ESPHome **2026.9.0 or newer**.

## Layout and capabilities

- The glass has the size and resolution of the 4-inch Guition, so the screen looks the same: two columns of three cells,
  the same tiles in millimetres, the standard look at 170 dpi. The glass is square, so it turns a quarter as well as a half.
- The backlight hangs on a PWM pin of the chip (GPIO4), not on an I2C expander as on the 4.3-inch and 7-inch Waveshares.
  Brightness is a percentage, and standby, night mode, Sleep, Wake and the alert's flashes are enabled, as on the Guition.
  GPIO4 is the analog dim input of the LED driver (an AP3032), not a switch for the LEDs: it reaches the driver's feedback
  pin through a 160 Hz filter, and the driver stops altogether once that level passes about 1.78 V. So the pin runs at
  300 kHz, the dimmest step stays just inside the steady range, 0 stays dark, and the light skips ESPHome's gamma
  (firmware 0.39.0; before, everything under 74 % brightness was dark).
  The 4.3-inch browned out when it switched its backlight on from dark; on this board only the PWM duty falls, but the
  wake from a dark standby has not been seen on this hardware yet.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM implementation.
- GT911 reports pixel coordinates, with no resistive calibration. The existing touch filter and action guard remain in use.
- The ES7210 microphone input and ES8311 speaker output use the shared audio graph, with Volume and Microphone in
  Extras. The speech path is mono, 16 kHz, with simultaneous capture and playback.
- The battery charger (AXP2101), the motion sensor and the clock chip stay unused. The screen runs from USB;
  a battery on the connector is neither read nor managed.

## Audio and Assist

Connect a suitable **8 ohm, 2 W speaker** to the speaker connector. Home Assistant exposes the screen's Media Player
for announcements and TTS. Volume is shared by Home Assistant, **Screen settings → Extras** in Tessera and
**Settings → Extras** on the screen. Hold the top bar to open the screen's settings.

**Microphone starts OFF when no choice has been saved.** Enable it in Extras on the screen, through its Microphone
entity in Home Assistant or through Tessera's Screen settings. The local control works without Home Assistant.
The screen restores a saved ON or OFF choice after restarting. Preferences normally reach flash within 60 seconds;
a sudden loss of power before that write can restore the previous choice.

Microphone OFF is a **software mute**, not a physical power disconnect. New audio callback buffers are zeroed;
already forwarded data and an answer that has started playing are not canceled. Without a microphone consumer,
the profile does not start continuous capture.

The separate **Voice assistant** plugin requires microphone, speaker and media player capabilities, which this
profile provides without another hardware plugin. Assist and wake words are not built into the default firmware.
Use an existing Home Assistant Assist pipeline with speech recognition, a conversation agent and speech synthesis.
There is no echo cancellation, stereo capture or two-microphone beamforming. Simultaneous capture preserves speech
during the wake sound; it does not remove that sound or a spoken reply from the microphone signal.

The speaker uses one native I2S controller as the clock source and keeps its clocks running in silence. The microphone
uses the other controller in secondary mode, following the same BCLK and LRCLK pins; only the speaker drives MCLK.
The amplifier follows buffered audio and switches off during silence without stopping capture.

Audio and end-to-end Assist still require physical acceptance. The target is ordinary speech about one metre from
the panel in a quiet room, not far-field use or speech over a television. The AXP2101's ALDO1 rail supplies the analog
audio circuitry; its availability after a true cold USB start must be checked. The profile does not write guessed
PMIC settings. A warm restart does not establish that cold-start audio works.

## Hardware references

- [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-4B) and its schematic.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/), with the generic `ST7701S` model and this board's pins.
  ESPHome's `WAVESHARE-4-480X480` model belongs to the board without the "B" and does not fit this one.
- The pins and timings follow a community configuration that runs this board with ESPHome
  ([alaltitov/Waveshare-ESP32-S3-Touch-LCD-4B](https://github.com/alaltitov/Waveshare-ESP32-S3-Touch-LCD-4B)).
- I2C: SDA GPIO47, SCL GPIO48, shared by the GT911, the TCA9554 expander (0x20) and the other chips.
- The ST7701S takes its setup over three-wire SPI on the expander: CS on EXIO0, data on EXIO1, clock on EXIO2.
  EXIO3 enables the speaker amplifier, initially off and then following buffered audio.
- RGB: DE GPIO17, PCLK GPIO9, HSYNC GPIO46, VSYNC GPIO3, 16 MHz pixel clock, 18-bit pixel mode, inverted colours.
- Backlight: GPIO4, PWM at 300 kHz, inverted, `min_power: 0.52` (duty 48 % at the dimmest), `zero_means_zero`, gamma 1.0.
- Audio I2S: MCLK GPIO5, BCLK GPIO16, LRCLK GPIO7, speaker data GPIO6 and microphone data GPIO15.
  The speaker controller is primary; the microphone controller is secondary and shares only the clock inputs.
  ES7210 is at I2C 0x40 with initial gain 24 dB; ES8311 is at 0x18. Mono capture uses the left channel.

## What to report while testing

1. Board revision, successful boot and appearance in Tessera.
2. Correct colours and a stable picture across several page changes and cold starts. Shifted, mirrored or inverted
   colours point at the display block.
3. Physical taps near each corner, slider drags and edge swipes, and the quarter-turn setting. Touch that lands mirrored
   or swapped points at the touch transform.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode. Report any restart, a dark screen that does not wake, or lost touch after a wake.
5. A full page of tiles, opening and closing the settings and detail cards.
6. Camera tile pictures, full-screen camera images and camera alerts, including repeated opens and closes.
7. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.
8. Audio after five full power-off USB starts, including successful codec initialization and an audible TTS answer.
9. Volume at 0, 25 and 50 percent through all three interfaces, repeated playback and Stop, and silence when idle.
10. Microphone OFF before its first saved choice, restored ON/OFF after power cycles, and muted input after playback.
    Wait more than 60 seconds after each choice before cutting power; do not erase existing preferences to test defaults.
11. With the optional Voice assistant plugin temporarily installed, twenty wake/question/spoken-answer cycles at one
    metre, repeated manual requests with wake word off, and recovery after reconnecting the screen's HA integration.
    Keep the plugin's normal sounds enabled for acceptance, and report clipped words or a capture that does not resume.
    Remove the temporary plugin and test page afterward and restore the previous layout, plugins and microphone choice.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
