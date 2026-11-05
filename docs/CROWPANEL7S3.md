# Elecrow CrowPanel Advance 7 inch, ESP32-S3, experimental

This is the **Elecrow CrowPanel Advance 7.0-inch HMI ESP32-S3 display** (SKU DIS08070H): a 7-inch 800 × 480 IPS RGB
panel with GT911 capacitive touch, an ESP32-S3-WROOM-1-N16R8 with 16 MB of flash and 8 MB of octal PSRAM, an onboard
STC8H1K28 coprocessor at I2C address `0x30` for the backlight and speaker amplifier gate, an NS4168 I2S speaker
amplifier and a PDM microphone.

## Which board

- **The CrowPanel Advance 7.0-inch with an ESP32-S3 (`DIS08070H`).** Elecrow sells several 7-inch boards with similar
  names: the earlier CrowPanel 7.0-inch without "Advance" drives its backlight from a GPIO pin and has different RGB
  pins, and the CrowPanel Advanced 7.0-inch ESP32-P4 (`DHE04107D`) is an ESP32-P4 MIPI-DSI board. Neither uses this
  board file.
- **Rear switch S1 set for the onboard microcontroller.** On the back of the board is a small two-pole DIP switch
  (**S1**) that routes `GPIO15` and `GPIO16` either to the onboard STC8H1K28 coprocessor or to the wireless module
  slot. Keep S1 in the position for the onboard microcontroller (silkscreen **1** OFF, **2** ON on V1.1, V1.2 and V1.3
  boards, so `GPIO15` and `GPIO16` reach the GT911 and `0x30`). In the other position, the I2C bus finds neither the
  touch controller nor `0x30`, and the backlight stays dark.

## Install

Update Tessera Screen Manager and choose **CrowPanel · 7 inch, Advance 7.0 ESP32-S3** (marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys. Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.

The remote package is `packages/crowpanel7s3.yaml` and the checkout entry `checkout/crowpanel7s3.yaml`. Each combines
`packages/core.yaml` with the board file `packages/boards/crowpanel7s3.yaml`, which adds its dimensions, density and
grid to the family's hardware file (`packages/hardware/crowpanel-s3.yaml`).

## Layout and capabilities

- 800 × 480 at 133 dpi, the standard look. A screen starts with four columns of four lying down and two columns of
  seven standing up, as on the 7-inch Waveshare and Sunton boards of the same glass; the editor's Grid button gives it
  another.
- Dimmable backlight with standby and night mode, through the STC8H1K28 coprocessor at `0x30` on `touch_bus` (`0` is
  full brightness, `245` is off).
- Speaker (`media_player.<screen>_speaker`) on the NS4168 I2S amplifier (`BCLK: GPIO5`, `LRCLK: GPIO6`, `DOUT: GPIO4`),
  gated by the STC8H1K28 at `0x30` (`248` on, `249` off), and the onboard PDM microphone (`switch.<screen>_microphone`,
  `CLK: GPIO19`, `DATA: GPIO20`). **Volume** and **Microphone** appear under **Extras** in Screen settings.
- Camera pictures and album covers in PSRAM; up to 128 tiles across 24 pages and 12 top-bar items.
