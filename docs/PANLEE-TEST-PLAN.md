# Panlee ZX3D95CE01S-TR-V12 Hardware Test Plan

This document outlines a practical test sequence for validating the Panlee ZX3D95CE01S-TR-V12 board profile on physical hardware.

**Prerequisites:** ESPHome development environment, USB cable, Panlee display.

---

## Phase 1: Initial Boot and Serial Logs

1. Build the firmware using `checkout/panlee-zx3d95ce01s.yaml`
2. Flash via USB at 115200 baud
3. Monitor serial output immediately after reset

**Expected:**
- Boot messages from ESP32-S3
- I²C scan showing touch controller address (0x38 for FT6336U, 0x5D for GT911)
- Display initialization completing without SPI errors
- "Connecting to WiFi..." message

**If blank screen or boot loop:**
- Check serial output for assertion failures or panic backtraces
- Verify power supply can deliver sufficient current (500mA minimum)

---

## Phase 2: Display Initialisation and Backlight

1. Observe the backlight at boot
2. Check if the Tessera UI appears

**Expected:**
- Backlight should illuminate within 1-2 seconds of boot
- UI should appear within 5 seconds

**Troubleshooting:**

| Symptom | Likely Cause | Action |
|---|---|---|
| Backlight off | Wrong GPIO pin or PWM frequency | Verify GPIO38, try 100Hz or 1kHz |
| Backlight on, no image | Display init sequence failure | Verify GC9503V chip marking; try Guition init if ST7701S |
| Garbled colours | Wrong colour order or inversion | Toggle `invert_colors` or change `color_order` to BGR |
| Image shifted or striped | Wrong RGB data pins or timing | Verify `data_pins` match PCB markings |

---

## Phase 3: Resolution, Orientation, and Colour

1. Verify the UI fills the entire 480×480 panel
2. Check that tiles are square and text is sharp
3. Test rotation via the screen's Settings → Screen → Rotation

**Expected:**
- All four edges of the UI touch the panel edges
- No black bars or cropped elements
- Rotation changes apply immediately

---

## Phase 4: Touch Detection and Coordinate Mapping

1. Tap each of the four corners
2. Tap the centre of each tile
3. Swipe from edge to edge (page navigation)
4. Long-press a tile to open its card

**Expected:**
- Taps register at the correct physical location
- Corner taps correspond to corner tiles
- Swipe changes page

**Troubleshooting:**

| Symptom | Likely Cause | Action |
|---|---|---|
| No touch response | Wrong touch controller or I²C address | Verify chip marking; scan I²C bus |
| Touch offset | Wrong `mirror_x`/`mirror_y`/`swap_xy` | Adjust `TOUCH_*` substitutions in board file |
| Touch only works in part of screen | Wrong calibration range | Verify `x_max` and `y_max` match panel |
| Erratic touch | Interference or wrong update interval | Try 50ms or 100ms update_interval |

---

## Phase 5: Wi-Fi Connection

1. Verify Wi-Fi credentials in `secrets.yaml`
2. Check the top bar shows Wi-Fi signal strength
3. Note the IP address in the serial log or Settings page

**Expected:**
- Wi-Fi connects within 10 seconds
- Signal strength shows in top bar
- IP address is reachable on local network

---

## Phase 6: Home Assistant Discovery

1. Open Home Assistant → Settings → Devices & Services
2. Look for the new ESPHome device
3. Add it and verify entities appear

**Expected:**
- Device appears as "My Panlee" (or configured friendly name)
- Entities: Display Backlight, Screen Layout, Screen Features, etc.

---

## Phase 7: Tessera UI Rendering

1. Open the Tessera Screen Manager add-on
2. Add tiles and arrange pages
3. Verify tiles render correctly on the physical display

**Expected:**
- Tiles display icons and states correctly
- Page navigation works via swipe or top bar
- Settings page opens on long-press of top bar

---

## Phase 8: Custom Cards and Display Features

1. Test climate card (if applicable)
2. Test media player card
3. Test alert overlay
4. Test dark mode toggle

**Expected:**
- All cards render within their tile bounds
- Alerts display full-screen with dismiss button
- Dark mode inverts colours correctly

---

## Phase 9: Reboot and Recovery Behaviour

1. Press the reset button or power-cycle the board
2. Verify the display re-initialises correctly
3. Verify Wi-Fi reconnects automatically

**Expected:**
- Clean boot with same display output
- Wi-Fi reconnects within 10 seconds
- Home Assistant re-establishes connection

---

## Hardware Verification Checklist

Before declaring the profile stable, verify:

- [ ] Actual LCD controller chip marking photographed
- [ ] Actual touch controller chip marking photographed
- [ ] Backlight works at multiple brightness levels
- [ ] Display shows correct colours (no inversion needed)
- [ ] Touch maps correctly to all four corners
- [ ] Wi-Fi connects reliably
- [ ] Home Assistant discovers the device
- [ ] Tessera UI renders correctly
- [ ] Reboot is reliable

## Reporting Results

Open an issue on the repository with:
1. Chip markings (photos preferred)
2. Any init sequence changes required
3. Any `transform` or `calibration` adjustments
4. General stability assessment

This will allow the profile to be promoted from `experimental` to `stable`.
