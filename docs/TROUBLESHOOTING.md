# Troubleshooting

The user-facing symptoms (the screen's own messages, touch, picture, Home Assistant, Docker) are on the Troubleshooting page of the Tessera website; this file keeps the checks for contributors and the manual USB route.

| Symptom | Check first |
|---|---|
| No USB port | Data cable, a different USB port, board power; compare `python -m serial.tools.list_ports` before/after connecting. Install the USB chip vendor's driver if needed. |
| Permission denied on Linux | Access to the serial device group (often `dialout`); log in again after a group change. |
| Port busy | Stop ESPHome logs, the IDE monitor, and other serial readers. One reader at a time. |
| Upload keeps connecting | Check the correct board/port. Hold BOOT while connecting and release afterward if the board requires it. |
| ESPHome Web shows no port or can't connect (Download) | Chrome or Edge on a computer; Safari, Firefox and phones can't reach USB. A data cable, and the driver for the board's USB chip if the computer asks for one (CH340 on most CYDs). Hold BOOT while choosing the port if it keeps failing to connect. |
| Build fails | ESPHome 2026.6.2 or newer with a Python it supports (the app's 2026.9.0 needs 3.12–3.14); the full unpacked folder, local fonts/components present, internet, and disk space. Save the first real error from the build log. |
| White/black, garbled or wrongly rotated image (CYD) | Pick the other **Display controller** (ILI9341 or ST7789V) under **New screen**, or the board **CYD ESP32-2432S028 ILI9342** for a CYD with an ILI9342; then `DISPLAY_DATA_RATE: 20MHz` or `DISPLAY_INVERT_COLORS: "true"` in the Override YAML ([EASY_SETUP.md](EASY_SETUP.md)). Choose lying down or standing up under New screen; don't copy fixed `dimensions` or `rotation` from a different CYD model, they break portrait. |
| Duplicate HA action | Check both the touch logs and your HA automations: an automation that reacts to the same entity can repeat or undo what the tile did. |
| Wi-Fi doesn't connect | 2.4GHz, correct local secrets, network range. USB calibration doesn't need HA. |
| A new screen stays on its card under Screens | Tessera adds a screen to Home Assistant by itself once it is on the Wi-Fi, and the card says when that doesn't work out. Usually Home Assistant can't reach the screen: another network segment or VLAN without mDNS, or guest network isolation. Make port 6053 reachable, or add it by hand ([EASY_SETUP.md](EASY_SETUP.md#adding-a-screen-by-hand)). |
| A screen built outside Tessera isn't in Home Assistant | Tessera only adds a screen whose YAML (with its key) is in the ESPHome folder it reads. Add it by hand ([EASY_SETUP.md](EASY_SETUP.md#adding-a-screen-by-hand)); Tessera then allows its actions. |
| Status works but action doesn't | Tessera turns **Allow the device to perform Home Assistant actions** on by itself; when it can't, the screen's page in Tessera offers **Allow actions**. In Home Assistant it is the ESPHome integration's **Configure**. Then check the real entity ID and a supported action. |
| Vacuum/climate partly usable | Supported modes/attributes differ per integration; test the same action in Home Assistant first. |
| Wrong pagination | Tiles keep the cell you gave them in Tessera: the board's grid decides how many fit on a page ([RESPONSIVE.md](RESPONSIVE.md)), up to eight pages and 64 tiles (more on a board with PSRAM, as many as its memory takes: [TILE_MEMORY.md](TILE_MEMORY.md)), and saving applies it without a reflash. The page buttons hide on a screen with one page, and **Page buttons** off hides them everywhere; then only swiping and Go to page tiles change the page, and the editor warns about a page nothing leads to. |
| Freeze/reset | Keep the USB log, check the reset reason/power, and run the render test. Note the action and time. A screen that restarts on "Loading tiles..." with firmware 0.3.6 needs firmware 0.3.7+ (app 0.3.13+); flash it once over USB if it can't stay up for an update over Wi-Fi. |

## Advanced: manual USB route

On a CYD or a Hosyond 4-inch, a USB install writes the partition table of firmware 0.33.1 and later, and the screen
takes its settings along the first time it starts with it: [UPDATING_4MB_SCREENS.md](UPDATING_4MB_SCREENS.md).

The touch measurement over USB with `tools/calibrate.py` ([CALIBRATING.md](CALIBRATING.md)). A CYD normally calibrates on the screen itself: **Calibrate touch** under Settings → This screen.

| Symptom | Check first |
|---|---|
| No measurement screen | The upload must be complete, not just the build. Flash with `-s CALIBRATION_ON_BOOT true`. Look for `USB calibration ready` in the USB logs; a normal boot shows no crosshairs. |
| No measurements | Five crosshairs visible, other log reader closed, correct port. Press Enter in the wizard first, then tap the requested point three times, releasing in between. |
| Tap jumps to a different spot | Check the independent `verify`, your own `calibration.yaml`, and a fixed orientation. Don't use the same taps to both fit and verify. |
| Fit reports spread/error | Measure again following the prompts. Don't fix unstable ADC readings by raising the tolerance; check power, cable, and touch hardware. |

For a USB log (stop other readers):

```sh
python diagnostics/capture_serial.py --port <USB_PORT> --seconds 120
```

Measurements from another screen are not calibration for a new board. Start at [README.md](../README.md), keep a working
local configuration, and change one cause at a time.
