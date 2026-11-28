# A Guition 4 inch restarts through a watchdog after an update

## The symptom

After an update over Wi-Fi a Guition 4 inch (ESP32-S3) comes back and works, but it reports "Reset Reason: Other
Watchdog" for that restart where the other boards report a restart that was asked for. The app reads a screen's log
after a restart, takes a watchdog for a crash and writes "rebooted after a crash: Other Watchdog" in its log and in
the screen's crash record, so the owner of such a screen finds a crash after every update that was none they saw.

## What we know

2026-11-24, one Guition 4 inch with ten pages and three plugins, three updates on one day:

| The firmware it restarted out of | Into | What the app logged |
|---|---|---|
| a build of 0.63.0 from an earlier day | 0.63.0 | rebooted after a crash: Other Watchdog |
| 0.63.0 | 0.64.0 | nothing (within the time the app leaves between two crash readings) |
| 0.64.0 | 0.64.0 | rebooted after a crash: Other Watchdog |

A CYD, a Guition 10.1 and a reTerminal D1001 updated in the same rounds and reported nothing. So it is this board or
this screen's layout, and it is older than firmware 0.64.0.

## Ruled out

- A crash while the screen runs: the screen was up and online before each update, and the line comes once, right
  after the restart the update asks for.
- Firmware 0.64.0 as the cause: the first row is a restart out of an older firmware.

## Candidates

1. The restart after the update hangs on this board (the RGB panel, the PSRAM or a plugin's component that does not
   stop), and the watchdog ends it. The screen then loses a few seconds, and a settings write at that moment could
   be lost.
2. ESPHome reports this reset reason on an ESP32-S3 for a restart that went well, and nothing hangs. Then the app's
   list of harmless reasons (`HARMLESS_RESETS` in `screen_manager/app/reports.py`) lacks a case, for this chip only.
3. Only this screen: one of its plugins holds the restart.

## The deciding experiment

Update a second Guition 4 inch without plugins and read its log over USB through the restart: the time between
"Rebooting" and the boot loader's first line, and the boot loader's own `rst:` line, say whether a watchdog fired
(candidate 1) or the reason is only named so (candidate 2). The same with the plugins of the first screen added one
by one decides candidate 3.

## Pointers

- `screen_manager/app/reports.py`: `crash_summary`, `HARMLESS_RESETS`, the capture after a restart.
- ESPHome's `debug` component: the reset reason's words. `ota` and `App.safe_reboot()`: the restart after an update.
