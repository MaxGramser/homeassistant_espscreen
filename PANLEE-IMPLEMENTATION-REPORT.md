# Panlee ZX3D95CE01S-TR-V12 Tessera Support — Implementation Report

**Date:** 2026-10-22
**Status:** EXPERIMENTAL — board profile updated against verified working ESPHome configuration; requires physical Tessera firmware validation
**Board ID:** `panlee-zx3d95ce01s`

---

## 1. Hardware Source of Truth

A working ESPHome configuration for the Panlee ZX3D95CE01S-TR-V12 was provided and used to correct the Tessera board profile. The display uses a **GC9503V** RGB controller via the `Quanghoster/gc9503v` external component, and a **FT63x6** (FT6336U family) capacitive touch controller.

The previous board profile assumed Guition compatibility; the corrected profile uses the exact pins and timings from the validated configuration.

---

## 2. Corrected Hardware Details

| Feature | Verified value |
|---|---|
| Processor | ESP32-S3 |
| Flash | 16 MB |
| PSRAM | 8 MB octal |
| Resolution | 480 × 480 |
| Display controller | GC9503V |
| Display platform | `gc9503v` (external component: `Quanghoster/gc9503v`, `model: PANLEE`) |
| Touch controller | FT63x6 / FT6336U family |
| Touch platform | `ft63x6` |
| Backlight pin | **GPIO5** (active high, LEDC) |
| Touch I2C | SDA=GPIO15, SCL=GPIO6 |
| Touch interrupt | GPIO4 |
| RGB PCLK / DE / VS / HS | GPIO39 / GPIO40 / GPIO41 / GPIO42 |
| RGB data pins (D0–D15) | 45, 48, 47, 0, 21, 14, 13, 12, 11, 10, 16, 18, 8, 3, 46, 10 |
| SPI init pins (shared D0/D1) | enable=GPIO38, SCLK=GPIO45, MOSI=GPIO48 |
| Reset pin | GPIO41 (shared with VSYNC) |
| RGB porch timings | H: 8 front / 10 pulse / 40 back; V: 8 front / 10 pulse / 40 back |
| PCLK inverted | true |

### RGB565 mapping
- **Blue[0:4]** → D0–D4 → GPIO45, GPIO48, GPIO47, GPIO0, GPIO21
- **Green[0:5]** → D5–D10 → GPIO14, GPIO13, GPIO12, GPIO11, GPIO10, GPIO16
- **Red[0:4]** → D11–D15 → GPIO18, GPIO8, GPIO3, GPIO46, GPIO10

Note: D15 (red MSB) and D9 (green bit 4) both map to GPIO10 in the working configuration. This is the mapping used by the manufacturer reference.

---

## 3. Board Profile Files

| File | Purpose |
|---|---|
| `packages/boards/panlee-zx3d95ce01s.yaml` | Board hardware definition |
| `packages/panlee-zx3d95ce01s.yaml` | GitHub package entry point |
| `checkout/panlee-zx3d95ce01s.yaml` | Checkout build entry point |
| `boards.yaml` (updated) | Catalog registration |
| `screen_manager/app/boards.json` (regenerated) | UI board metadata |
| `tests/fixtures/overrides/panlee-zx3d95ce01s-contract.yaml` | Override test fixture |
| `docs/PANLEE-ZX3D95CE01S.md` | Board-specific documentation |
| `docs/PANLEE-TEST-PLAN.md` | Hardware validation test plan |

### Key design decisions

1. **Display platform:** `gc9503v` external component with `model: PANLEE`. This selects the manufacturer-specific init sequence and RGB timings that are known to work on this glass.
2. **External component location:** The `external_components` block for `gc9503v` lives in the board file, so it is included both for GitHub package builds and checkout builds.
3. **Touch platform:** `ft63x6` on the dedicated touch I2C bus (GPIO15/6) with interrupt on GPIO4.
4. **Backlight:** GPIO5 via LEDC, matching the working reference.
5. **No separate `spi:` bus:** The `gc9503v` platform drives the SPI init phase itself through `sclk_pin`/`mosi_pin` declarations, so no `spi:` block is needed.

---

## 4. Driver Changes Required

**No code changes to the repository's components are required.** The profile uses:
- The `Quanghoster/gc9503v` external component for the display
- ESPHome's built-in `ft63x6` touchscreen platform
- The repository's existing `smart_display` component

---

## 5. Validation Results

### Static validation (performed)
- ✅ YAML syntax of the board file
- ✅ Package references and includes
- ✅ `tools/check_packages.py` passes
- ✅ `tools/generate_entries.py --check` passes
- ✅ `tools/generate_board_shapes.py` regenerates `boards.json`
- ✅ `BOARD_ID` uniqueness and catalog registration

### Compilation / hardware validation (not yet performed)
- ⬜ `python -m esphome config checkout/panlee-zx3d95ce01s.yaml`
- ⬜ `python -m esphome compile checkout/panlee-zx3d95ce01s.yaml`
- ⬜ Flash to physical Panlee hardware
- ⬜ Verify display, touch, backlight, Wi-Fi, Home Assistant discovery, Tessera UI

### Validation commands
```bash
# From the repository root:
python -m esphome config checkout/panlee-zx3d95ce01s.yaml
python -m esphome compile checkout/panlee-zx3d95ce01s.yaml
python -m esphome run checkout/panlee-zx3d95ce01s.yaml
```

---

## 6. Build Instructions

### From a checkout (recommended for testing):
```bash
git clone https://github.com/MaxGramser/homeassistant_espscreen.git
cd homeassistant_espscreen
cp checkout/secrets.yaml.example checkout/secrets.yaml
# Edit secrets.yaml with your Wi-Fi and API keys
python -m esphome config checkout/panlee-zx3d95ce01s.yaml
python -m esphome compile checkout/panlee-zx3d95ce01s.yaml
python -m esphome run checkout/panlee-zx3d95ce01s.yaml
```

### From ESP Screens / Tessera:
- Select **Panlee ZX3D95CE01S-TR-V12** from the New screen list.
- The add-on will write the screen's own YAML with `packages/panlee-zx3d95ce01s.yaml`.

---

## 7. Remaining Work to Reach `stable`

1. Compile the checkout profile without errors.
2. Flash to physical Panlee hardware and verify boot.
3. Verify display image: no corruption, correct colours, 480×480 fill.
4. Verify touch maps to all four corners and supports swipe/gesture.
5. Verify backlight dims/brightens and wakes on touch.
6. Verify Wi-Fi, Home Assistant discovery, and Tessera UI tiles/cards.
7. Run 24+ hours for stability.

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `gc9503v` external component unavailable/fails | Low | High | Pin/fork the component into the Tessera org if needed |
| Touch axis swap/mirror needed | Medium | Low | Add `TOUCH_SWAP_XY`/`TOUCH_MIRROR_*` substitutions if required |
| Rotation offsets | Low | Low | Adjust `ROTATION_LANDSCAPE` in board or screen YAML |
| Backlight PWM frequency causes shimmer | Low | Low | Adjust `BACKLIGHT_FREQUENCY` substitution |

---

*End of report. The board profile now matches the validated ESPHome hardware configuration; physical Tessera firmware validation is the next step.*
