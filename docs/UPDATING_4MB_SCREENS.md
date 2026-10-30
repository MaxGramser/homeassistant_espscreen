# Screens with 4 MB of flash: more room, and what to do if you flash yourself

This page is for the CYD (ESP32-2432S028, with an ILI9341, ST7789V or ILI9342 display) and the Hosyond 4-inch. They
have 4 MB of flash. Since app 0.4.56 and firmware 0.33.1 these boards get a partition table of their own, and a
screen you already have moves to it during a normal update. If you only ever update from the Tessera panel in Home
Assistant, there is nothing to do: read the first two sections and skip the rest. If you build or flash your screens
yourself, with ESPHome Device Builder, the ESPHome command line or a USB cable, read on from "If you flash yourself".

## What changed, and why

A screen keeps its firmware in two slots, so an update can be written next to the running one. ESPHome's standard
layout for 4 MB of flash gives each slot 1,835,008 bytes and keeps 448 KB at the end for settings. Tessera's firmware
had filled the slot almost to the last byte, and a screen uses only a few hundred bytes of that settings area.

The new table takes the settings out of that area and puts them in 16 KB that were never used, in front of the first
slot. Each slot grows to 2,031,616 bytes, about a tenth more. Those bytes are what new features for these boards will
be built in from now on.

The table is `components/flash_layout/partitions-4mb-wide.csv` in the repository. Everything the screen keeps comes
along when it moves: its touch calibration, the settings from the settings page, which way it hangs, the radio's
calibration. The Wi-Fi name and password, the API key and the update password are not in that area at all. They are
part of the firmware itself, and a new table does not change them.

## What you notice when you update from Tessera

- Update the screen as you always do, from the Tessera panel or in the nightly round. This one update takes a few
  minutes longer, and the screen restarts two or three times instead of once.
- Afterwards the screen has a new diagnostic sensor in Home Assistant, **Screen flash**. It says `wide` when the
  screen has the new table.
- Update the Tessera Screen Manager app first, then the screens, as always. Once a firmware no longer fits the old
  table, the app installs a small firmware in between, sends the table, and then installs the screen's own firmware.
  The glass is dark for a minute or two while it does. An older app does not know this way: it builds the firmware,
  the screen refuses it because it is too large, and the app reports a failed update. The screen keeps running its
  old firmware; update the app and try again.

How the move works, in short: a screen that still has the old table keeps a copy of its whole settings area where
the new table looks for them. The copy is made when the screen starts and again when an update begins, and compared
with the settings both ways. Only when the copy is exact, the screen runs from its first slot and ESPHome has
confirmed the new firmware (a minute after an update) does the screen say `widen`, and only then does Tessera send
the table, with ESPHome's own tools. The whole story, for the curious, is in [FLASH_LAYOUT.md](FLASH_LAYOUT.md).

## If you flash yourself

A screen gets the new table in one of three ways. Pick the one that matches how you work.

### 1. Let Tessera do it once

Press **Update** on the screen in the Tessera panel once. Tessera adds the line the table needs to the screen's YAML
(see below), installs the firmware, waits for the screen to say it is ready, and sends the table. After that, build
and install with Device Builder as before: the line stays in the YAML, and a screen with the new table takes any
later firmware the usual way.

### 2. Once over USB

An install over USB writes the new table straight away, together with the firmware, and the screen fetches its
settings from the old place the first time it starts, so nothing is lost. Any of these does it:

- In ESPHome Device Builder: **Install**, then **Plug into this computer** or **Plug into the computer running
  ESPHome Device Builder**.
- In the Tessera panel: **Firmware & USB**, then **This computer · install from this browser** or **Download · flash
  from your own computer**, for an existing screen.
- From ESPHome Device Builder's **Install → Manual download**, the factory format, written with
  [ESPHome Web](https://web.esphome.io/?dashboard_install).

The screen restarts once more the first time it starts with the new table. The CYD does not ask for a new touch
calibration: the old one comes along.

### 3. Over Wi-Fi by hand

This is what Tessera does, step by step. You need the screen's YAML and secrets on a computer with ESPHome
2026.7.0 or newer (**Download screen files** in the screen's details in the Tessera panel gives you exactly that).

1. Add one line to the `ota:` block of the screen's YAML. It lets the screen take a partition table over Wi-Fi, and
   it has to stand in the screen's own YAML, not in a package:

   ```yaml
   ota:
     - platform: esphome
       password: "your-update-password"
       allow_partition_access: true
   ```

2. Install the firmware over Wi-Fi as usual (**Install → Wirelessly** in Device Builder, or
   `esphome run kitchen.yaml --device 192.168.1.50`). The screen now runs firmware 0.33.1 or later, still with the
   old table.
3. Wait a minute and look at the screen's **Screen flash** sensor in Home Assistant:
   - `widen`: go on to step 4.
   - `widen_next`: the update landed in the screen's second slot. Install the same firmware over Wi-Fi once more, wait
     a minute, and it says `widen`. (ESPHome would move the firmware itself if you sent the table now, but that
     takes about a quarter of a minute on these boards and can run into the watchdog on a slow flash chip. Tessera
     never does that, and neither should you.)
   - `old` for longer than two minutes: see below.
4. Send the table from the same folder you built in:

   ```sh
   esphome upload --partition-table kitchen.yaml --device 192.168.1.50
   ```

   This takes a second. The screen restarts with the new table and its settings, and the sensor says `wide`.

### What the Screen flash sensor says

| Word | Meaning |
| --- | --- |
| `wide` | The screen has the new table. Nothing to do. |
| `widen` | ESPHome's old table, the copy of the settings is in place and checked, the firmware is confirmed: the screen is ready for the table. |
| `widen_next` | As `widen`, but the firmware runs from the second slot: install it once more first. |
| `old` | ESPHome's old table, not ready yet: the new firmware is still on trial (the first minute after an update), the copy could not be made, or the YAML lacks the `allow_partition_access` line. |
| `other` | A partition table that is neither ESPHome's own for 4 MB nor Tessera's, for example one you wrote yourself. The screen keeps it, and Tessera leaves it alone. |

### "The OTA partition on the ESP is too small"

An install over Wi-Fi from Device Builder or the command line may stop with this message from ESPHome: the firmware
has outgrown the old table's slot, and the screen refuses it before anything is written. Take route 1 or route 2.
Route 3 cannot help here: the firmware the screen would need in order to say `widen` is the one that does not fit.
Tessera's own update works through this with the small firmware in between.

## Things to know

- **Power.** The table itself is written in a fraction of a second. A screen that loses its power in exactly that
  moment does not start again. It is not broken: an install over USB (route 2) brings it back, with its settings,
  since they are already in their new place.
- **A table of your own.** If your screen's YAML names a partition table under `esp32: partitions:`, Tessera leaves
  it alone and the sensor says `other`. You are on your own there, and you have been before.
- **Going back.** The firmware runs with either table, so an older firmware installed over Wi-Fi is no problem. An
  install over USB of firmware from before 0.33.1 writes ESPHome's old table again, and that firmware does not know
  where the settings went: the screen starts with its defaults, and a CYD asks for its calibration again.
- **Other boards.** Nothing changes for a board with more flash. Their firmware stays as it is, they are offered no
  update for this, and they have no Screen flash sensor.
