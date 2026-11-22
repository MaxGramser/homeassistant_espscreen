# Files a screen downloads

A screen takes more from ESP Screen Manager than its tiles: pictures, streams, and files. A file is something the app
has and a screen keeps, such as the sound it rings with. This is how one gets there, and the recipe for a new kind.

## The way

- **One store.** `screen_manager/app/screen_files.py` keeps every file by its content: the name of a file is the sha256 of
  its bytes in hex. A file someone gave the app (a sound they cut) is written into `files/` of the app's data and is
  there after a restart. A file the app makes itself (a built-in sound) is held in memory and made again at each
  start, to the same bytes, so to the same name.
- **One path.** The app serves every file at `/files/<name>.<ext>` on its LAN port, 8098, the port the pictures and
  streams already use (`picture_links.py`). The answer carries the name as its ETag. No second port: 8098 is the one a
  house already lets through.
- **A link where it is needed.** The app puts a file's link into the message that needs it (a ring's `rt`, docs/SOUNDS.md), made from its
  address on the screen's own network (`lan_address`). Nothing is pushed: the screen asks when a message names a file it
  does not have.
- **One download on the screen.** `components/smart_display/file_fetch.h` downloads a file whole into PSRAM in a task of
  its own and hands it over on the main loop (every 50 ms, with the pictures). The screen keeps a file by the name in its
  link (`file_fetch::name_of`): the same name is the same file, so it asks for nothing. A download that fails, answers
  anything but 200, is larger than its caller allows or takes over ten seconds ends as a failure, and its caller falls
  back to what it had.
- **One HTTP layer.** `components/smart_display/http_get.h` is what every download from the app shares: the link, the
  answer's head and the socket. `picture_fetch` (pictures), `live_view` (streams), `talk_uplink` (a voice up) and
  `file_fetch` (files) each read their own body on top of it.

The names are not secret. A name nobody was given cannot be guessed, and what a file holds is nothing a screen on the
LAN may not have. A kind of file that must stay private needs short-lived links of its own, as the pictures have.

Only a board with pictures builds the download (`SCREEN_PICTURES`, `packages/features/camera.yaml`); a 4 MB board pays
nothing for it.

## The kinds

| Kind | Extension | Who keeps it | Who reads it on the screen | Doc |
|---|---|---|---|---|
| A sound: a call's ringtone, a doorbell's chime, an alert's sound | `wav` (16 kHz, mono, 16 bits) | `sounds.py` | `kept_sound.h`, `wav.h` | docs/SOUNDS.md |

## A new kind of file

1. Its owner in the add-on keeps what the file means and calls `files.add(bytes, ext)`; a new extension goes into
   `screen_files.TYPES` with its content type.
2. The message that needs it carries `files.link(base, name)` as an additive field, so older firmware never sees it.
3. On the screen, `file_fetch::get(link, most, done)` with the largest size that kind may have; `done` gets the bytes in
   PSRAM and frees them with `roomy::release` when they are replaced. Keep the name (`file_fetch::name_of`) to ask only
   for a file you lack.
4. A reader of the format that is pure, with a test of its own (as `wav.h` and `tests/test_wav.cpp`).
5. A row in the table above, and the doc of the kind.

## Tests

`tests/test_sounds.py` checks the store, the path on the camera port (200, 304 on the name, 404) and the ring's
`rt`; `tests/test_wav.cpp` the WAV reader and `file_fetch::name_of`; `tests/test_picture_fetch.cpp` and
`tests/test_live_view.cpp` the link and the head of `http_get.h`.
