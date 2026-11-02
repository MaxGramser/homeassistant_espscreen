# Espressif ESP32-S3-BOX-3, 2.4 inch (new)

The **ESP32-S3-BOX-3** from Espressif is a 2.4-inch 320 x 240 board: an ILI9342C panel over SPI, GT911 capacitive touch
over I2C, and an ESP32-S3 with 16 MB flash and 16 MB octal PSRAM. It has the CYD's resolution on smaller glass, with
PSRAM and a backlight that dims.

The board file's pins come from ESPHome's own BOX-3 package and Espressif's board support package. A contributor ran it
on a BOX-3 of their own with no changes to the board file (below), so the board is **new**: tried on a real unit, with
few screens out there yet.

Its speaker (ES8311 and an amplifier) and its two microphones (ES7210) work, which makes the screen a media player in
Home Assistant and lets plugins play and listen (the voice assistant among them); the audio is **experimental** (below).
The mute button and the sensors of its dock are not used yet. A BOX-3 that runs ESPHome's own voice assistant firmware
today stops being one when it is flashed with this firmware, until the voice assistant plugin is added. Keep that
firmware to flash it back.

## Which BOX-3

Early BOX-3 units have a TT21100 touch controller and an ST7789 panel instead of the GT911 and the ILI9342C. Espressif's
board support package tells the two apart by which chip answers on the I2C bus. This board file is for the GT911 units.
The boot log tells you which one you have: the GT911 answers at 0x5D or 0x14, the TT21100 at 0x24.

## Install

Update Tessera Screen Manager and choose **Espressif · 2.4 inch, ESP32-S3-BOX-3** in **New
screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA
keys, then flash it over USB-C or download the firmware for ESPHome Web. There is no touch calibration: the touch panel
reports pixels.

The remote package is `packages/esp32s3box3.yaml` and the checkout entry `checkout/esp32s3box3.yaml`. Both combine
`packages/core.yaml` with the board file `packages/boards/espressif-esp32-s3-box-3.yaml`.

## Layout and capabilities

- Lying down 320 x 240, two columns of two cells; standing up 240 x 320, one column of four. The compact look at
  167 dpi. The CYD's two by three would leave rows of about 7 mm on this smaller glass, under the 12 mm a tile keeps;
  a screen can still be given that grid in the editor.
- The backlight is a PWM pin (GPIO47) at 1 kHz: brightness is a percentage, and standby, night mode, Sleep, Wake and the
  alert's flashes are enabled.
- The GT911 reports pixels lying down and is read through its interrupt line.
- The GT911 shares its reset with the display, and picks its I2C address again each time it is reset. So it starts
  after the display (`setup_priority: 500`), and finds its address after the display's reset. Started before it, the touch
  panel stopped answering after a reset over USB.
- 128 tiles on up to 24 pages, as on the other ESP32-S3 boards with PSRAM.
- No camera pictures yet. The PSRAM would hold them, but lying down an alert card on 320 x 240 glass has no room for a
  picture, and every board with camera pictures shows one both ways up.
- LVGL draws through a quarter of the screen (`LVGL_BUFFER_SIZE: "25%"`).

## Speaker and microphones

The BOX-3 is the first ESP32-S3 board here with audio. `packages/hardware/espressif-box3-audio.yaml` names the parts the
Waveshare P4 boards also use (docs/P4_AUDIO.md): the ES8311 for the speaker, its amplifier on GPIO46, and the ES7210 for
the two microphones, on one I2S bus at 16 kHz. Two of the chip's I2S ports share that bus
(`packages/hardware/parts/es7210/duplex.yaml`): the microphone's port gives the clocks and the speaker's follows them,
as on the Guition P4 panels, so the microphone listens while the speaker plays. A wake word keeps listening through a
sound, and a question is heard from its first word. One way at a time (`AUDIO_TRANSPORT: "i2s"`) lost the first
seconds of a question while the wake sound played. The ES7210's echo cancellation (`AUDIO_TRANSPORT: "aec"`) has not
been tried on an ESP32-S3; a screen's Override YAML can set it to try. Without it, the speaker's own sound reaches the
microphones.

Under **Screen settings → Extras**, in Tessera and on the screen: the media player's volume, the microphone on or off,
the microphone gain (0 to 36 dB, initially 30) and the automatic gain.

## Tried on a real unit

- Installed from a build of this board file, lying down and standing up, taking tiles that switch lights in Home
  Assistant.
- Colours right (red and blue not swapped), nothing shifted at the edges.
- Taps land where they should near the corners and in the middle, slider drags and swipes between pages, both ways up.
- Brightness changes from the settings, standby goes dark and a touch wakes it, night mode dims.
- The dock opens with a swipe up from the bottom edge, shows the pages, and closes with a tap above it and with a drag
  down.
- After several resets the touch panel keeps answering, with the GT911 starting after the display (above).
- The top bar takes twelve items, as on every board with PSRAM, but the glass's width shows about eight lying down,
  with icons alone (`content: icon`); the ninth left the bar.
- Memory over 31 hours without a restart, with a page of tiles: about 183 KB of internal heap free, 182 KB at the
  lowest.
- The speaker: text to speech and a radio stream from Home Assistant's media player, the volume from 10 to 100 %, while
  the screen kept drawing and changing pages.
- The microphones, with the voice assistant plugin on the voice microphone (MIC2): the wake word heard at 0.97 to 0.99,
  and four questions in a row understood and answered ("turn the office light on", "off", and so on), asked right
  after the wake word while its sound played. Internal RAM at about 98 KB free at the lowest with audio running.

The host render (`tools/render/run.py esp32s3box3`) fails on the dock and on a clickable below the glass lying down,
while on the real unit the dock opens and closes as it should. That is still open
([open issue](open-issues/box3-render-dock.md)).

## Still to check

- An early BOX-3 with the TT21100 touch controller, which this board file does not drive.
- Camera pictures, once the alert card has room for one lying down on 320 x 240 glass.
- The ES7210's echo cancellation (`AUDIO_TRANSPORT: "aec"`) on an ESP32-S3.

## Hardware references

| Part | Pins |
| --- | --- |
| Display bus (SPI) | clock GPIO7, data GPIO6, 40 MHz |
| Display control | chip select GPIO5 and data/command GPIO4, from ESPHome's model; reset GPIO48, active high |
| Touch (GT911, I2C 0x5D or 0x14) | SDA GPIO8, SCL GPIO18, interrupt GPIO3; its reset is the display's |
| Backlight | GPIO47, PWM |
| Audio codecs (ES8311 at 0x18, ES7210 at 0x40) | the touch panel's I2C bus |
| Audio (I2S) | MCLK GPIO2, BCLK GPIO17, LRCLK GPIO45, speaker data GPIO15, microphone data GPIO16 |
| Speaker amplifier | enable GPIO46, high for on |

GPIO3, GPIO45 and GPIO46 are strapping pins of the ESP32-S3, wired to the touch panel's interrupt and the audio on this
board.

- [ESPHome mipi_spi](https://esphome.io/components/display/mipi_spi/), model `S3BOX`: the panel's init sequence, its
  size, its mirroring and its chip select and data/command pins.
- [ESPHome's BOX-3 package](https://github.com/esphome/wake-word-voice-assistants/tree/main/esp32-s3-box-3): the
  display, the backlight, the I2C bus, the PSRAM and the audio.
- [Espressif's board support package](https://github.com/espressif/esp-bsp/tree/master/bsp/esp-box-3): the touch
  controller and its interrupt pin, and the audio pins.

## What to report while testing

1. A successful boot and appearance in Tessera.
2. Correct colours lying down and standing up (red and blue not swapped), and nothing shifted at the edges.
3. Taps near each corner and in the middle, slider drags and edge swipes, both ways up.
4. Dimming from 10 to 100 %, standby going dark and waking on a touch, and night mode.
5. `sensor.<screen>_heap_free` with a full layout, any reset or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
