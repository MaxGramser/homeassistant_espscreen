# LILYGO 1.75 hardware acceptance

## Symptom

The experimental H0175Y003AM profile has passed initial hardware checks. Full brightness, rotated touch and standby/wake acceptance is still open.

## What we know

The 2026-11-17 contribution preserves the manufacturer example's CO5300 QSPI wiring, 466 × 466 RAM window with a six-column offset, GPIO16 supply enable, and CST9217 at address 0x5A. ESPHome 2026.9.0's cst9220 driver explicitly accepts CST9217. The shared Rotation setting still offers all four quarter turns on the square canvas; LVGL owns the touch transformation.

Hardware testing confirmed native rendering, taps, a hold to open Settings, and edge swipes at 0° after the CST9217's fixed half-turn transform.

The default PWM gamma mapped 20% brightness to 2/255 on the CO5300, which made the standby clock fade from view. The panel now receives the brightness percentage directly. After an OTA update, the Classic clock stayed visible at 50% standby brightness.

## Ruled out

The panel can render Tessera, accept touch input and show the standby clock at the tested brightness.

## Candidates

Cold startup and recovery, low and night brightness, touch alignment at the other rotations, and repeated standby/wake still need testing. Optional large views, keyboards and third-party plugin pages also need acceptance on this small glass.

## Deciding experiment

On an identified H0175Y003AM unit, check cold USB startup and recovery; inspect the entire panel; tap and drag at the centre and edges at 0°, 90°, 180° and 270°; use native page keys, holds, swipes and the Dock; vary brightness; enter standby and wake repeatedly; restart and confirm settings persist. Record which hardware revision and firmware commit were tested.

## Pointers

- [Board and reproduction instructions](../LILYGO175.md)
- [Hardware profile](../../packages/hardware/lilygo175.yaml)
- [Manufacturer's exact-model example](https://github.com/Xinyuan-LilyGO/T-Display-S3-AMOLED-1.43-1.75/blob/main/examples/Light_Sleep_Wake_Up_H0175Y003AM/Light_Sleep_Wake_Up_H0175Y003AM.ino)
