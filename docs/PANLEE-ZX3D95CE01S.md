# Panlee ZX3D95CE01S-TR-V12

The **Panlee ZX3D95CE01S-TR-V12** is a 3.95-inch 480 × 480 IPS display with an ESP32-S3, 16 MB flash, and 8 MB of octal PSRAM. The display uses a **GC9503V** RGB LCD controller, and touch is reported by an **FT6336U** capacitive controller.

**Hardware status: EXPERIMENTAL.** The board profile has been updated to match a verified working ESPHome configuration using the `Quanghoster/gc9503v` external component. It now requires physical validation with the Tessera firmware to move to `stable`. The board identifier is `panlee-zx3d95ce01s`.

## Hardware summary

| Feature | Value | Confidence |
|---|---|---|
| Display size | 3.95 inches diagonal | High (labelled) |
| Resolution | 480 × 480 | High (labelled) |
| Processor | ESP32-S3 | High (labelled) |
| Flash | 16 MB | High (working config) |
| PSRAM | 8 MB octal | High (working config) |
| LCD controller | GC9503V | High (working config) |
| Touch controller | FT6336U | High (working config) |
| Backlight | GPIO5, PWM | High (working config) |
| Touch I2C | SDA=GPIO15, SCL=GPIO6 | High (working config) |
| Touch interrupt | GPIO4 | High (working config) |

## Key differences from the Guition 4848S040

The Guition uses an **ST7701S** LCD controller; the Panlee uses a **GC9503V**. The Tessera profile for Panlee therefore uses the `gc9503v` external component with `model: PANLEE` rather than the built-in `st7701s` platform.

The touch controller differs too: the Guition uses **GT911**, while the Panlee uses **FT6336U**. The Panlee profile uses ESPHome's `ft63x6` platform.

The RGB pinout is similar but not identical to the Guition's. The verified mapping is used in `packages/boards/panlee-zx3d95ce01s.yaml`.

## Files

- `packages/boards/panlee-zx3d95ce01s.yaml`: the board file (hardware and glass sizes).
- `packages/panlee-zx3d95ce01s.yaml`: what a screen builds from over GitHub.
- `checkout/panlee-zx3d95ce01s.yaml`: the same for a build from a clone of this repository.

## Display configuration

The profile uses the `gc9503v` platform from `Quanghoster/gc9503v` with `model: PANLEE`. This selects the manufacturer-specific init sequence and RGB timings that are known to work on this glass.

```yaml
display:
  - platform: gc9503v
    model: PANLEE
    id: my_display
    color_order: RGB
    dimensions: {width: 480, height: 480}
    # ... pins and timings as in the board file
```

The SPI initialization pins are shared with the RGB data bus:
- enable (CS): GPIO38
- SCLK: GPIO45 (shared with RGB D0 / blue LSB)
- MOSI: GPIO48 (shared with RGB D1 / blue bit 1)
- reset: GPIO41 (shared with VSYNC)

## Touch configuration

The profile uses ESPHome's built-in `ft63x6` platform:

```yaml
touchscreen:
  - platform: ft63x6
    id: ts_touch
    i2c_id: touch_bus
    display: my_display
    interrupt_pin: 4
    update_interval: 20ms
    calibration:
      x_min: 0
      x_max: 480
      y_min: 0
      y_max: 480
```

If touches land in the wrong place, adjust `TOUCH_SWAP_XY`, `TOUCH_MIRROR_X`, and `TOUCH_MIRROR_Y` in the board file or via the screen's settings.

## RGB pinout

The RGB565 mapping used in this profile:

- **Blue[0:4]** → D0–D4 → GPIO45, GPIO48, GPIO47, GPIO0, GPIO21
- **Green[0:5]** → D5–D10 → GPIO14, GPIO13, GPIO12, GPIO11, GPIO10, GPIO16
- **Red[0:4]** → D11–D15 → GPIO18, GPIO8, GPIO3, GPIO46, GPIO10

Sync pins: PCLK=GPIO39, DE=GPIO40, VSYNC=GPIO41, HSYNC=GPIO42.

Porch timings: H front 8 / pulse 10 / back 40; V front 8 / pulse 10 / back 40. PCLK is inverted.

## Test plan for physical validation

1. **Build and flash**: use `checkout/panlee-zx3d95ce01s.yaml` with a checkout of this repository.
2. **Serial logs**: watch the boot log at 115200 baud. Look for I²C scan results (FT6336U should appear at address `0x38`) and the display init completing without errors.
3. **Backlight**: the backlight should come on at boot and dim/brighten with screen settings. If it does not, check GPIO5 and the `BACKLIGHT_FREQUENCY` substitution.
4. **Display**: the screen should show the Tessera UI. If it is blank or corrupted, check the `gc9503v` external component is being fetched and the RGB pins match the board file.
5. **Touch**: tap the four corners. If touches land in the wrong place, adjust `TOUCH_SWAP_XY`, `TOUCH_MIRROR_X`, and `TOUCH_MIRROR_Y`.
6. **Wi-Fi and Home Assistant**: connect to Wi-Fi and confirm Home Assistant discovery.
7. **Rotation**: test 0°, 90°, 180°, 270° via Screen settings.

## Reporting results

If you validate this profile on real Panlee hardware, please open an issue with:
- Whether the profile worked as-is or needed changes.
- Any `transform` or `calibration` adjustments needed for touch.
- Photos of the PCB if possible.

This will let us move the profile from `experimental` to `stable`.
