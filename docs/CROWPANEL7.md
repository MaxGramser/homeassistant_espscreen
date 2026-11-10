# Elecrow CrowPanel ESP32 HMI7.0 inch (DIS08070H), experimental

This is the **Elecrow CrowPanel ESP32 HMI Display7.0-inch** (SKU DIS08070H): a7.0-inch800 x480 TN panel over a
16-bit RGB parallel bus (EK9716BD3 + EK73002ACGB), GT911 capacitive touch, and an ESP32-S3-WROOM-1-N4R8 with4 MB
of flash and8 MB of octal PSRAM, a CH340 behind its USB port, a PCA9557 I/O expander and a speaker amplifier.

No acceptance run on glass yet: the display, the touch and the backlight in this file come from the configuration
that has been run on this board (Elecrow's own example, the devices.esphome.io device page for it, and a unit
flashed with it over serial), and the layout has been through the host render. What only a person at the panel can
check is listed under "What to report while testing" below.

## Which board

- **Hardware revision V3.0** (printed on the back). V3.0 added the touch timing control Elecrow's wiki documents:
  the PCA9557 at I2C0x18 carries the GT911's reset line on IO0, and the board file gives the GT911 driver that
  line as its `reset_pin`, so the reset and address latch happen inside touch setup, where the board needs them.
  An earlier revision without the expander is not covered by this file.
- **An N4R8 module:4 MB of flash, not16.** Many shop pages and older examples say16 MB; a16 MB build stops at
  every start with "Detected size(8192k) smaller than the size in the binary image header". The firmware keeps its
  wide update slots in the table `components/flash_layout/` writes (`Screen flash` in Home Assistant says which
  table a screen has).
- **One USB port through a CH340**, on UART0: the logs and a serial flash go through it, and the chip's own USB
  serial JTAG is not brought to a connector.

## Install

Choose **CrowPanel ·7.0 inch, DIS08070H** (marked Experimental) in **New screen** of Tessera Screen Manager and
follow [Easy setup](EASY_SETUP.md). A screen that still has Elecrow's own firmware needs a first flash over USB:
its bootloader and partition table are not ESPHome's, so erase the flash and write the factory image (`firmware
at0x0`), the same as for a first install of any other board. After that every update is over Wi-Fi.

The remote package is `packages/crowpanel7.yaml` and the checkout entry `checkout/crowpanel7.yaml`. Each combines
`packages/core.yaml` with the board file `packages/boards/crowpanel7.yaml`. The chip, its memory and the RGB
panel's ESP-IDF settings come from `packages/hardware/esp32s3-rgb.yaml`, the4 MB slots from
`packages/hardware/flash-4mb.yaml`, with this board's pins in the board file.

## Layout and capabilities

-800 x480 at133 dpi, the compact look, as every board with4 MB of flash has: its font set is what fits this
  board's update slot (the standard look's fonts are about300 KB over it). A screen starts with four columns of
  five lying down and two of eight standing up; the editor's Grid button gives it another. The proposal suggests
  four rows, but a cell at least twice the compact look's cell height (99 px at this density) makes the renderer
  stack each card's icon above its name, which the self test's geometry check measures and fails; five rows keeps
  every cell under that line and lands the tiles at the16 mm the grid proposal asks for.
- The panel is800 x480 itself, so it lies down without a turn.
- The backlight is a PWM pin (GPIO2) at1220 Hz: brightness is a percentage, and standby, night mode, Sleep, Wake
  and the alert's flashes are enabled.
- The GT911 reports pixel coordinates, with no calibration (a calibration section on this board turns a working
  probe into "Communication failed", esphome/esphome#13307).
- The I2C bus on GPIO19/GPIO20 has the touch and the PCA9557 on it, and is not scanned at start. The USB serial
  JTAG D+ pull-up issue (esphome/esphome#15356) has not shown up on this board: the bus answers at400 kHz
  without the workaround, and a probe of the touch that does not answer reports a clean not-acknowledged rather
  than a timeout.
- No camera pictures, no album artwork and no maps in this file: the picture fetching and decoding do not fit
  beside this board's fonts in the update slot, and the board has no camera of its own. The speaker amplifier
  (I2S on GPIO17/GPIO42/GPIO18) is not wired up either; both are the first things to revisit if a later core
  gets smaller.

## Hardware references

- [Elecrow's wiki for the CrowPanel ESP32 displays](https://www.elecrow.com/wiki/esp32-display-702727-intelligent-touch-screen-wi-fi26ble-800480-hmi-display.html)
  and the V3.0 touch timing sequence in the board's own GitHub repository, which the board file follows.
- [The devices.esphome.io device page for DIS08070H](https://devices.esphome.io/), whose configuration ran on
  this glass: the RGB pins, the porches, `invert_colors` and the GT911 at0x5D or0x14.
- [ESPHome's mipi_rgb display platform](https://esphome.io/components/display/mipi_rgb/) for what the panel's
  timings mean; this board states its own (model RPI with the board's data pins and porches), not one of
  ESPHome's named models.

## What to report while testing

The host render cannot show any of these; they are what a run on the panel is for.

- Touch: the corners and a drag across the glass, on a cold start as well as a warm one (the V3.0 reset runs at
  every start).
- The backlight at every brightness, including standby and night mode, and whether1220 Hz is audible on this
  unit's driver.
- The colour order and the rotation, lying down and standing up.
- A page switch by an edge swipe, and a tap that does nothing when it starts on the tiles.
- What `Screen flash` in Home Assistant says after the first update, and after the second (the table the wide
  slots replace it with).
