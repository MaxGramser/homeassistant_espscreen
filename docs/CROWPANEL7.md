# Elecrow CrowPanel Advanced 7 inch, ESP32-P4, experimental

This is the **Elecrow CrowPanel Advanced 7-inch ESP32-P4 HMI display** (SKU DHE04107D): a 7-inch 1024 x 600 IPS
panel with an EK79007 MIPI-DSI driver, GT911 capacitive touch, an ESP32-P4 with 16 MB flash and 32 MB PSRAM, an
ESP32-C6 beside it for Wi-Fi, a loudspeaker and a PDM microphone.

It is the [CrowPanel Advanced 10.1](CROWPANEL101.md) behind smaller glass: Elecrow builds the 7, 9 and 10.1-inch
boards on one design and serves them with one ESPHome example, and the two board files share every pin
(`packages/hardware/crowpanel-p4.yaml`). The 10.1 has run on this hardware file; the 7-inch has not been tried on its
own glass yet, so everything under "What to report while testing" is open.

## Which board

- **Hardware revision V1.1 or later.** Elecrow's V1.0 example for the 7-inch runs the Wi-Fi link's data lines D0 to
  D3 on GPIO14 to GPIO17; from V1.1 on they run the other way round, as on the 10.1, and the board file follows that.
  A V1.0 board gets no Wi-Fi with this file unless its own YAML turns `HOSTED_D0_PIN` to `HOSTED_D3_PIN` back round.
  The revision is printed on the back of the board.
- **An ESP32-P4 before silicon revision 3.** The firmware is built for the earlier silicon (`engineering_sample: true`),
  as Elecrow's own example is. A board with rev3 silicon does not boot it, and a successful flash over USB does not mean
  otherwise. The chip revision is in the first lines of the USB log ("chip revision: v1.3").

## Install

Update Tessera Screen Manager and choose **CrowPanel · 7 inch, Advanced 7.0 ESP32-P4** (marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys. Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.

The remote package is `packages/crowpanel7.yaml` and the checkout entry `checkout/crowpanel7.yaml`. Each combines
`packages/core.yaml` with the board file `packages/boards/crowpanel7.yaml`, which adds only its density and its grid
to the family's hardware file.

## Layout and capabilities

- 1024 x 600 at 170 dpi, the standard look. A screen starts with four columns of four lying down and two columns of
  seven standing up, as on the Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, the same panel at the same size; the editor's
  Grid button gives it another.
- The panel is 1024 x 600 itself, so it lies down without a turn.
- Backlight, audio, camera pictures and touch are the 10.1's ([CROWPANEL101.md](CROWPANEL101.md), "Layout and
  capabilities").

## Hardware references

- [Elecrow's GitHub repository for this board](https://github.com/Elecrow-RD/CrowPanel-Advanced-7inch-ESP32-P4-HMI-AI-Display-1024x600-IPS-Touch-Screen)
  with its ESPHome example (`example/V1.0/ESPHome/Code/advance-p4-7-inch.yaml`), and Elecrow's V1.1 ESPHome tutorial,
  which says the one example serves the 7, 9 and 10.1-inch boards.
- The pins are the 10.1's ([CROWPANEL101.md](CROWPANEL101.md), "Hardware references").

## What to report while testing

The list in [CROWPANEL101.md](CROWPANEL101.md), "What to report while testing", from the first boot on: nothing on
this list has been seen on the 7-inch glass yet.
