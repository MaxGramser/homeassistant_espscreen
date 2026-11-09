# Elecrow ESP Terminal 3.5-inch parallel (DLC35010R)

Experimental support for the parallel Elecrow ESP Terminal DLC35010R linked below. This is not the SPI Terminal (DLC35020S),
not a CrowPanel HMI resistive board, and not a continuously scanned RGB panel.

A contributor has successfully built and flashed the firmware through a
customized Tessera installation on Home Assistant OS. Display output and
capacitive touch work correctly in normal use on physical hardware.

The board remains experimental. The confirmed results and remaining acceptance checks are listed below.

## Hardware and sources

- [Elecrow product](https://www.elecrow.com/esp-terminal-with-esp32-3-5-inch-parallel-480x320-tft-capacitive-touch-display-rgb-by-chip-ili9488.html)
- [Manufacturer wiki](https://static-cdn.elecrow.com/wiki/esp-terminal-with-35inch-rgb-capacitive-touch-display.html)
- [Manufacturer examples and schematic](https://github.com/Elecrow-RD/CrowPanel-ESP32-Terminal-with-3.5-inch-parallel-480x320-TFT-capacitive-touch-RGB-display)
  (`example/Arduino/ESP_Terminal_RGB_Arduino/ESP_Terminal_3.5inch_RGB_code/LVGL_RGB_/LVGL_RGB_.ino`,
  bundled LovyanGFX `Panel_ILI948x.hpp`, and `Eagle_SCH&PCB/RGB/ESP32- 3.5 TFT Display(RGB)-V2.0.sch`).

ESP32-S3-WROOM-1-N16R8: 16 MB flash, 8 MB octal PSRAM. ILI9488 native 320×480, landscape 480×320,
3.5 inches, 164.825 dpi. FT6236 capacitive touch at I2C address 0x38. The USB-C port uses a CH340C UART bridge.

| Signal | GPIO |
|---|---|
| LCD D0–D7, in order | 47, 21, 14, 13, 12, 11, 10, 9 |
| LCD D8–D15, in order | 3, 8, 16, 15, 7, 6, 5, 4 |
| WR / RD / DC | 18 / 48 / 45 |
| Backlight | 46, active high PWM |
| Touch SDA / SCL | 38 / 39 |
| Buzzer | 20 |
| USB bridge UART TX / RX | 43 / 44 |

CS is permanently selected and the LCD reset follows board reset; neither gets an invented GPIO.
RD is held high. No touch interrupt pin is assumed; the touch driver polls every 20 ms.

## Implementation

`packages/boards/elecrow-terminal-rgb.yaml` provides hardware and layout only. Shared Tessera cards, Home Assistant
API, OTA, touch filtering and rotation stay unchanged. The board starts at 2×2 cells in landscape and 1×3 in portrait,
with up to 128 tiles / 24 pages subject to the existing memory budget. It includes still camera pictures, self-test,
snapshot, standby and PWM dimming. Live video through direct RGB/DSI framebuffers is not available on this i80 panel.
The buzzer is an RTTTL output, not a media speaker or Assist device. SD and optional Crowtail peripherals are not configured.
No battery percentage is invented: the charging connector alone supplies no verified battery measurement.

The local external component `ili9488_i80` uses ESP-IDF's i80 DMA peripheral with the manufacturer's register values.
It reserves 10,240 bytes of internal DMA RAM, copies LVGL RGB565 pixels in bounded chunks, converts byte/colour order,
and waits for completion before reusing its buffer. A transfer error or one-second timeout stops the display instead
of corrupting an in-flight DMA buffer. Default bus speed is a conservative 10 MHz, configurable up to 20 MHz.
The driver remains in native portrait orientation; LVGL rotates display and touch together. MADCTL defaults to 0x08
(unmirrored native portrait, BGR). LVGL rotation 270 matches Elecrow's offset_rotation=2 plus rotation=1,
and maps touch to (479 - raw_y, raw_x), matching its example without an extra touch transform.
Display output works in normal use on the tested unit. Dedicated colour-pattern tests and checks of both
orientations have not yet been recorded; `madctl` can be overridden if a board revision differs.

## Build locally

Use the ESPHome version in `requirements.txt`. Create `checkout/secrets.yaml` following `checkout/README.md`, then:

```sh
esphome config checkout/elecrow-terminal-rgb.yaml
esphome compile checkout/elecrow-terminal-rgb.yaml
```

Do not flash a build made with demonstration credentials. For an actual installation, let the customized Screen
Manager create the device's Wi-Fi/API configuration, or provide your own secrets before compiling.

## Installation on Home Assistant OS

Follow [Easy setup](EASY_SETUP.md) using a Tessera version that includes `elecrow-terminal-rgb`, then select
**Elecrow ESP Terminal 3.5 parallel (DLC35010R)** when creating the screen.

When testing support from a fork before it is included in an upstream release, both the Screen Manager app and its
firmware packages must use that fork. The generated device YAML's package URL and `ref`, and the package's external
component and font sources, must refer to the intended repository and branch. Adding a fork to Home Assistant's app
store alone does not change these firmware URLs. Existing device YAML files retain their saved package references.

## Validation status

Confirmed by a contributor on a physical DLC35010R:

- Firmware built and flashed through a customized Tessera installation on Home Assistant OS.
- Display output and capacitive touch work correctly in normal use.

These results apply to the tested custom firmware. The contribution branch based on a newer upstream `dev` must
be built and tested separately. They do not establish that every feature or acceptance check below has passed.

The following checks have not yet been individually recorded: boot-log memory and controller verification, solid
colour patterns, all four touch corners and full-width dragging, both orientations, brightness, standby and wake,
OTA updates, cold power cycles, full-layout page swipes, still camera pictures, and free internal heap measurements.

## Hardware acceptance checklist

1. Build using the real screen's configuration. Connect the Terminal's USB-C cable to the machine used for flashing;
   select its CH340 port by identity. If needed, hold BOOT while pressing RESET, then release BOOT.
2. Verify the boot log reports 16 MB flash, 8 MB PSRAM and the FT6236 at 0x38, without display setup/DMA failures.
3. Check solid red, green and blue, readable text and all four touch corners; drag a slider across the whole width.
4. Test landscape and portrait using Tessera's rotation setting. Confirm one touch triggers the expected tile.
5. Test brightness, standby and touch-to-wake; then OTA update and a cold power cycle.
6. Test a full layout, page swipes and still camera images; record free internal heap and responsiveness.

Keep the board experimental until the remaining checks pass on physical hardware. Record the tested firmware
revision and ESPHome version with the results in the pull request, including any checks that remain untested.
