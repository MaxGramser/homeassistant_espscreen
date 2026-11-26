# Makerfabs E32S3RGB43 V3.1, 4.3 inch

This is the **Makerfabs ESP32-S3 Parallel TFT with Touch 4.3 inch V3.1** (E32S3RGB43): an 800 x 480 RGB panel with
GT911 capacitive touch, an ESP32-S3, 16 MB flash and 8 MB octal PSRAM.

The board was tested on real V3.1 hardware with Tessera: the display, GT911 touch, Home Assistant connection, page
changes and tile interaction work. The stock backlight is always on. An optional hardware modification can expose
PWM brightness control; it is deliberately not part of the default profile, so an unmodified board needs no soldering.

## Install

Update Tessera Screen Manager and choose **Makerfabs · 4.3 inch** (E32S3RGB43 V3.1) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys.
Use the native USB connector for USB Serial/JTAG logs and flashing.

The remote package is `packages/makerfabs43.yaml`; the checkout entry is `checkout/makerfabs43.yaml`.
Both combine `packages/core.yaml` with `packages/boards/makerfabs43.yaml`.

## Hardware and layout

- 800 x 480 RGB panel, 3 x 3 cells in landscape and 1 x 4 in portrait.
- ESP32-S3 with 16 MB flash and 8 MB octal PSRAM.
- GT911 capacitive touch on I2C: SDA GPIO17, SCL GPIO18, address 0x5D.
- GPIO38 is the GT911 reset line. This V3.1 profile uses no separate GT911 interrupt pin.
- RGB panel: DE GPIO40, HSYNC GPIO39, VSYNC GPIO41 and PCLK GPIO42 at 16 MHz, inverted.
- RGB data: red GPIO45/48/47/21/14, green GPIO5/6/7/15/16/4, blue GPIO8/3/46/9/1.
- Panel timings: H front/pulse/back 40/48/88; V front/pulse/back 13/3/32.
- LVGL uses a 12% draw buffer, leaving internal RAM for networking and the RGB panel while its frame lives in PSRAM.
- Camera tiles and the shared picture features use the board's PSRAM.

## Backlight

The stock V3.1 board does not expose software brightness control, so Tessera keeps its backlight on and does not offer
standby or night brightness for the default profile.

Makerfabs provides pads for a backlight-control modification. On the V3.1 schematic, **R59** is unpopulated between
GPIO44/RXD0 and the Q7 (S8050) backlight transistor network. **R29** is the 0-ohm link between the CP2104 USB-to-UART
TX signal and the same GPIO44/RXD0 net. The optional setup tested with Tessera populates R59 and removes R29, leaving
GPIO44 dedicated to the backlight. Follow Makerfabs' hardware documentation for the soldering itself; the V3.1
schematic marks R59 as `NC` and does not specify a resistor value.

### Dimming with the R59/R29 modification

After the hardware modification, open the screen in Tessera, choose **··· → Override YAML** and add:

```yaml
substitutions:
  BACKLIGHT_DIMMABLE: "true"
  CAN_STANDBY: "true"

output:
  - id: !remove gpio_backlight_pwm
  - platform: ledc
    id: gpio_backlight_pwm
    pin:
      number: GPIO44
      inverted: true
    frequency: 1000Hz
```

Then use **Save & check** and **Update firmware**.

The transistor stage is active-low on the tested V3.1 board, hence `inverted: true`: Tessera 0% is off and 100% is
full brightness. With the override, the screen reports its actual dimming and standby abilities to Tessera, so the
brightness, standby and night controls appear for that modified screen without changing the stock board profile.

Removing R29 disconnects the CP2104 TX path from GPIO44. Use the **USB-Native** connector for USB Serial/JTAG logs and
flashing when using this modification.

## Hardware references

- Makerfabs product repository: https://github.com/Makerfabs/ESP32-S3-Parallel-TFT-with-Touch-4.3inch
- V3.1 schematic and board files are under that repository's `hardware/` directory.

## Hardware acceptance

Tested on a physical V3.1 board on 2026-10-29/30:

1. 800 x 480 image and colour order stable in the full Tessera firmware.
2. GT911 touch works across the UI after using GPIO38 as reset rather than interrupt.
3. Home Assistant/Tessera connection, tiles, page changes and touch interaction work.
4. 16 MB flash and 8 MB octal PSRAM are detected and the full firmware builds and boots.
5. Optional GPIO44 PWM backlight control works after the R59/R29 modification, including the active-low polarity.

The integrated I2S audio hardware is not enabled by this board profile yet.
