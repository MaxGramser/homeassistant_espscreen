# Troubleshooting reports

"My screen doesn't work right" is a button on a screen's page in the app (app 0.4.91). It makes one report of that
screen, shows every file in it before anything leaves, and sends it to the Tessera website only after a consent per
report. A developer then has what they used to ask for one by one: the board, every version, the plugins, the crash,
the logs.

## What a report holds

| File | What it is |
|---|---|
| `report.md` | The facts first: board, versions, the plugins the app installed on the screen and the ones the screen's own hello named (a screen that was restarting while the report was made named none, so the installed ones stand in and the report says so), the last crash, warnings, the list of files. Start here. |
| `summary.json` | The same facts as data, plus the hello's memory, the firmware's heap and Wi-Fi sensors, Last boot, the pages and tiles count and the card types. |
| `profile.yaml`, `override.yaml`, `plugins.yaml` | The screen's own YAML and the files beside it, redacted. |
| `screen.log` | The crashes the app saw this screen reboot from, decoded when the ELF is here, then 45 seconds of live log over the native API with the config dump (reset reason, partitions, versions); the app turns the screen's Debug mode on for those 45 seconds and back to what it was after them, because a screen writes its warnings and errors alone while it is off (docs/SETTINGS.md). When the task watchdog restarted the screen because its main loop stopped, the record also holds the main loop's own stack at that moment (`LOOP0:` and on, newest first, from `loop_record.h`): ESPHome's own record then only names the idle task, since the main loop was waiting on something, and these lines say on what. Beside it stands ESP-IDF's esp_timer task (`*** THE ESP_TIMER TASK AT THE LAST TASK WATCHDOG ***`, its state and `TIMER0:` and on): it runs the watch that restarts a screen within four seconds when a copy of the P4's picture engine never comes back (`ppa_trace.h`), so when such a copy stopped the screen and the task watchdog restarted it instead, these lines say where that task stood. The previous boot's internal RAM rides along too (`*** INTERNAL RAM ON PREVIOUS BOOT ***`, from `heap_watch.h`): `Lowest:`, the least internal RAM that boot had free and when, and `Failed:`, how many allocations found no room and the last of them (its size, the memory it asked for, the function and task, and the internal RAM free then); the H.264 encoder's first ask for its reference frame, more than the chip's internal RAM, falls back to PSRAM by itself and is not counted there. An abort or a failed assert leaves what it said too (`*** ABORT ON PREVIOUS BOOT ***`, from `abort_record.h`): the `Details:` ESP-IDF gave it (with compact asserts the assert's address) and `AT0:` and on, the code addresses on the aborting task's own stack, which name who called what failed. These records are logged with the config dump, so every log subscriber gets them, this report's included. |
| `home-assistant.log` | Home Assistant's log lines about this screen (the ESPHome integration and its library), and the warnings and errors Home Assistant kept. |
| `diagnostics.json` | Home Assistant's own diagnostics of the screen's ESPHome entry: config, device info, dashboard, versions, OS, repairs. |
| `addon.log` | The app's own log. |
| `build.log` | The last build of this screen in the app, when there was one. |

The full report, an opt-in on the page that says what it adds, also holds `layout.json` (the pages and tiles with
their entity ids and options), every ESPHome log line of every screen, every warning Home Assistant kept, and the whole
storage of the ESPHome entry (every entity it knows).

## What never leaves

`redaction.py` runs over every file: passwords, keys and tokens after their word, Wi-Fi names, IPv4 and IPv6 addresses,
MAC addresses in both forms, coordinates, and the keys Home Assistant's own diagnostics redact (and more: host,
unique_id). The screen's names (device, friendly, node) read `<screen>` so the lines stay readable and can be followed
from one file to the next. Entity ids stay in the log lines about this screen; the layout with every entity id is only
in the full report. The note and the e-mail address are the person's own words, sent as typed.

## Where it goes

The zip is kept under `/data/reports/` (the last five), served to the page file by file and as a download. Send posts
it to `POST api/v1/addon/reports` of the website with the board's feedback key as bearer (feedback.py, so a board keeps
one key), the board id, versions, depth, consent, the note, the optional e-mail address and a JSON summary. The website
answers a reference `TR-XXXXXX` to quote on GitHub or Discord, keeps the report for its retention period (its
`ADDON_REPORT_RETENTION_DAYS`, 30), mails the maintainer at once, and shows it under Admin, Troubleshooting reports,
with every text file readable inline and the zip to download. Five reports a day per board.

## Crashes

ESPHome keeps a record of a crash in RAM that survives the reboot (`esp32/crash_handler.cpp`): the reason, the PC, up to
16 backtrace addresses. It is logged, and cleared, for the first client that subscribes to the log after the boot.
Home Assistant subscribes only when the entry's "Subscribe to logs" option is on, so the record waits for the app.
`Reports.watch` looks at every screen's "Last boot" sensor; when it changes, the app connects for eight seconds as the
first subscriber, reads the record and the debug component's reset reason, decodes the addresses with the toolchain's
`addr2line` and the ELF of the screen's build under `/data/build/<name>/build/firmware.elf`, and keeps the crash in
`/data/crashes.json` (ten per screen, one capture per five minutes). The page shows the last crash and how many the
week had; the report carries them all.

A build from a build server has no ELF here (build_server.py leaves the debug symbols there): its crash stays a list of
addresses, and the report says `no_elf`. The panic's `ELF file SHA256:` is the first nine characters of the ELF's SHA-256,
so a wrong ELF decodes nothing (`elf_mismatch`) rather than the wrong names. Asserts print only an address because the
packages build with `assertion_level: SILENT` (49 KB of flash on the CYD); a board with room may set `ENABLE` in its own
file for `assert failed: function file:line (condition)`.

## Where a change of this kind goes

- `screen_manager/app/reports.py` (collecting, the crash watch, sending), `redaction.py` (what leaves), the routes in
  `server.py` under "My screen doesn't work right", `tests/test_reports.py`.
- The page: `web/src/components/ReportPanel.vue`, route `report` in `web/src/router.ts`, texts `editor.report.*`.
- The website: `AddonReportController`, `ValidateAddonReportClient`, `App\Support\AddonReports`, the admin pages
  `Admin/AddonReports.vue` and `Admin/AddonReport.vue`, `tests/Feature/AddonReportTest.php`.
- A new file in the zip: name it in `reports.py` (the order of `ordered`), in this table, and in the website's
  `AddonReports::isTextEntry` when it is text to read inline.
