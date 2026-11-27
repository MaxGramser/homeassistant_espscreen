# Hosyond ES3C28P, 2.8-inch ESP32-S3 display, 320 × 240 (experimental)

The 2.8-inch IPS display module documented on lcdwiki as the **ES3C28P** ([2.8inch ESP32-S3 Display](https://www.lcdwiki.com/2.8inch_ESP32-S3_Display)),
also sold by diymore ("ESP32-S3 WiFi Development Board Bluetooth Smart Display TFT Module Touchscreen, supports
Xiaozhi"). It is the CYD's glass on an ESP32-S3: a 240 x 320 **ILI9341V** IPS panel over SPI, **FT6336G capacitive
touch** over I2C, an ESP32-S3 N16R8 module (16 MB flash, 8 MB octal PSRAM), an **ES8311** codec with a speaker behind
an FM8002E amplifier and a MEMS microphone, a WS2812 RGB LED, a microSD slot and a battery charger.

Take the ES3C28P. The ES3N28P is the same board without the touch panel.

The board is **experimental**: its file was built from lcdwiki's pin table and an ESPHome configuration that ran on a
real board, and one owner runs it with Tessera ("What was tried on the glass", below).

## Install

Choose **Hosyond · 2.8 inch** (ES3C28P) in **New screen** and follow [Easy setup](EASY_SETUP.md). The remote
package is `packages/es3c28p.yaml`; the checkout entry is `checkout/es3c28p.yaml`. Both combine `packages/core.yaml`
with `packages/boards/es3c28p.yaml`.

## Layout and capabilities

- Lying down: 320 x 240, two columns of three cells, the CYD's grid. Standing up: 240 x 320, one column of four.
- The compact look at 143 dpi (400 diagonal pixels over 2.8 inches), the CYD's own density, so letters and keys have
  the CYD's size in millimetres.
- Capacitive touch, no calibration. With 8 MB of PSRAM it keeps 128 tiles on up to 24 pages, as the Waveshare 3.5.
- Dimmable backlight (PWM on GPIO45). The BOOT key (GPIO0) is the standby key.
- Speaker and microphone through the ES8311 (`parts/es8311-voice.yaml`, ESPHome's own I2S both ways): the screen is a
  media player in Home Assistant, and plugins that need a speaker or a microphone fit it. Echo cancelling is left out:
  it has not been tried on an ESP32-S3 with an SPI panel. The amplifier follows the sound, so the speaker does not hiss
  in silence.
- The WS2812 is a light called **LED** in Home Assistant, off after every start.
- No camera pictures yet: on 240 pixels of glass the alert card has no room for a still, which the camera feature and
  its checks count on.

## Hardware notes

| Part | Pins |
|---|---|
| Display (ILI9341V, SPI) | CLK GPIO12, MOSI GPIO11, MISO GPIO13, CS GPIO10, DC GPIO46; reset on the chip's EN |
| Backlight | GPIO45, lit high |
| Touch (FT6336G, 0x38) | SDA GPIO16, SCL GPIO15, INT GPIO17, RST GPIO18 (not used, below) |
| Audio (ES8311, 0x18, on the touch bus) | MCLK GPIO4, BCLK GPIO5, LRCK GPIO7, to the codec GPIO8, from the codec GPIO6 |
| Amplifier (FM8002E) | GPIO1, on while low |
| RGB LED (WS2812) | GPIO42 |
| microSD (SDIO, not configured) | CLK GPIO38, CMD GPIO40, data GPIO39, 41, 48, 47 |
| Battery ADC (not configured) | GPIO9 |

What an ESPHome configuration on a real board found, and the board file keeps:

- The IPS panel needs both `invert_colors: true` and `color_order: bgr` (checked with red, green and blue test bars).
- The FT6336's reset pin stays untouched. ESPHome reads the chip's ID right after its reset pulse, before the chip is
  ready, and the touch never starts.
- The I2C bus runs at 100 kHz. At 400 kHz the touch reported random coordinates.
- The ES8311's volume register is steep: 0 dB is three quarters of ESPHome's range, and above it a full-scale sound
  clips. The media player stops at the DAC's 0 dB, as on every board with this codec (`features/audio-player.yaml`).

Not configured yet: the microSD slot (lcdwiki does not say which of the four data pins is which) and the battery. On
the board tried, `features/battery-adc.yaml` on GPIO9 read 0.0 V with a battery attached, and the board went dark as
soon as its USB cable came out, so neither the battery nor its measurement could be checked.

## What was tried on the glass

On one board (diymore, ESP32-S3 revision v0.2, 16 MB flash, 8 MB PSRAM), 2026-11-27:

- Picture, colours and pages, lying down and standing up; touch in the four corners and a drag, both ways up.
- Standby and waking with the BOOT key.
- The speaker: a FLAC streamed from the local network played through the media player, with 143 KB of internal RAM
  left at its lowest (145 KB free at rest, 8 MB of PSRAM free).
- The LED: red, green and blue from Home Assistant.
- A plugin tile (Nightscout) with data from Home Assistant.
- Wi-Fi on its own power supply. On a computer's USB port the same board failed to join the network ("Auth Expired"
  from every access point): give it a good supply.

Still to try: the microphone (a voice assistant or a call). [Tell others how it went](https://tessera-maxgramser.on-forge.com/community/share?type=installation&board=es3c28p).
