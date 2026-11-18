# LILYGO 1.75 hardware acceptance

## Symptom

The experimental H0175Y003AM profile has no physical acceptance result. A native render and a successful compiler cannot prove that the panel and touch work on a unit.

## What we know

The 2026-11-17 contribution preserves the manufacturer example's CO5300 QSPI wiring, 466 × 466 RAM window with a six-column offset, GPIO16 supply enable, and CST9217 at address 0x5A. ESPHome 2026.9.0's cst9220 driver explicitly accepts CST9217. The shared Rotation setting still offers all four quarter turns on the square canvas; LVGL owns the touch transformation.

## Ruled out

No claim of a panel, brightness, rotated-touch or standby/wake test follows from the software checks. No physical equipment was operated during preparation of this contribution.

## Candidates

Panel initialization or colour order, brightness command behavior, edge touch alignment at each rotation, and power or touch behavior after standby remain unmeasured. Optional large views, keyboards and third-party plugin pages also need acceptance on this small glass.

## Deciding experiment

On an identified H0175Y003AM unit, check cold USB startup and recovery; inspect the entire panel; tap and drag at the centre and edges at 0°, 90°, 180° and 270°; use native page keys, holds, swipes and the Dock; vary brightness; enter standby and wake repeatedly; restart and confirm settings persist. Record which hardware revision and firmware commit were tested.

## Pointers

- [Board and reproduction instructions](../LILYGO175.md)
- [Hardware profile](../../packages/hardware/lilygo175.yaml)
- [Manufacturer's exact-model example](https://github.com/Xinyuan-LilyGO/T-Display-S3-AMOLED-1.43-1.75/blob/main/examples/Light_Sleep_Wake_Up_H0175Y003AM/Light_Sleep_Wake_Up_H0175Y003AM.ino)
