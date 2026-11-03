# Pictures: one system, three routes

Every picture a screen has to do with takes one of three routes, and the three share one vocabulary, one question and
one service in ESP Screen Manager:

| Route | Direction | What travels | Where it is drawn | Boards |
|---|---|---|---|---|
| **Stills** | ESP Screen Manager to the screen, pulled | one picture, made for exactly its place, once or at a pace | LVGL, from the picture store | every board that draws pictures |
| **Streams** | ESP Screen Manager to the screen, streamed | JPEGs, one after the other, for a rectangle of the glass | past LVGL, straight into the panel's frame buffer | a board whose chip decodes JPEG in hardware (the ESP32-P4) |
| **Capture** | the screen to Home Assistant | the screen's own camera, as an ESPHome camera | not on the glass | a board whose files name a camera sensor (`camera_sensor`) |

docs/CAMERA.md says what a person sees of cameras on a screen; docs/PLUGINS.md what a plugin may do with pictures.
This file is the design every one of them follows; docs/PICTURE_ARCHITECTURE.md is the code under it, the layers it is
built in and the seams between them.

## The words

- **Place**: where a picture lands. A rectangle of an owner on the glass: a tile's card, the icon's circle, the full
  view, an open card, the screensaver, an alert's frame, a place a plugin laid out. A place has a size in pixels, a
  corner radius, the colour behind its corners (its ground) and how the picture fills it.
- **Source**: what a picture is of, as a typed address (below). The screen names the source; ESP Screen Manager alone
  knows how to get it, and whether this screen may have it.
- **Question**: what a screen asks for one owner: its places, a source per place, how each is painted, and how it
  wants it delivered. One shape for every owner (below).
- **Delivery**: a still (once, or again after a pace) or a stream (a rectangle of the glass, on a board that streams).
- **Owner**: who wants a picture on the screen (the full view, an alert, an open card, the library, a tile, a plugin's
  card or screensaver). The screen's loader decides between owners (`picture_loader.h`); ESP Screen Manager never needs
  to know about them beyond authorising the question.

## Sources

A source is a short text. The kinds:

| Source | What it is | Who may ask |
|---|---|---|
| `tile:<index>` | the picture a tile of the layout shows by its settings: a camera's snapshot, a media player's cover, a favourite's cover, a map, the covers of a player at rest | a tile of that index on this screen's layout |
| `camera:<entity>` | a `camera.*` or `image.*` entity's snapshot | the full view and screensaver of a tile or a choice of this screen, an alert sent to it, a plugin tile of that entity |
| `cover:<entity>` | the picture of what a `media_player.*` plays, through Home Assistant's proxy for that player | a media card, a screensaver's music step, a plugin tile or card of that entity |
| `entity:<entity>` | an entity's own picture (`entity_picture`: a person, an image) | a plugin tile or card of that entity |
| `map:<index>` | a map tile drawn by ESP Screen Manager, with `focus` and `move` as the screen asks | the full view of that map tile |
| `vacuum:<entity>` | a vacuum's map, cleaned up and in the screen's look | a vacuum card of that entity |
| `library:<entity>/<page>` | a page of a player's library, its covers in one picture | the library of that player on this screen |
| `photos:` | the photo the screensaver's photos step shows now | the screensaver |
| `step:` | the screensaver step's own picture (the cover of the music step, the photo of the photos step) | a screensaver face of that step (a plugin's `backdrop` or place) |
| `https://...` | a picture on the internet | a plugin whose manifest names that host under `permissions.network` |
| `/api/image/serve/...`, `/api/image_proxy/...`, `/local/...` | a picture Home Assistant serves | a plugin tile or card of an entity |

A plugin uses the same kinds as the core where they make sense for it (`cover`, `camera`, `entity`, `step` and
addresses), with one rule set for both: `pictures/sources.py` decides, never a list of its own beside it. The core can
show nothing a plugin of the same entity cannot.

## The question

A screen asks with Home Assistant's event `esphome.screen_camera`, as it always has, with the fields of its session
(`inbox`, `session`, `rev`), the question's number `n` (one count for every owner) and the question itself as compact
JSON in `q`:

```json
{
  "src": ["tile:3"],
  "box": [480, 270],
  "at": [[0, 0, 480, 270, 12, 0]],
  "fit": ["cover"],
  "bg": "1C1C1E",
  "look": "d",
  "cap": 1310720,
  "fmt": ["bmp8", "bmp24"],
  "pace": 15000,
  "live": [480, 270]
}
```

- `src`: one source per place, or one source for every place.
- `box`: the picture's size in pixels. `at`: each place in it, `[x, y, w, h, radius, shade]` (shade 0 or 170: the
  dark band under words). One place covering the box is the common case.
- `fit`, and where a place asks for more, `fx`: per place, `cover` (filled, cut to the place) or `contain` (whole, on
  the ground), and effects: `turn` (`left`, `right`), `mirror`, `dim` (a screensaver's darkening), `move` (a photo cut
  larger for slow motion).
- `bg`: the colour behind rounded corners and around a contained picture. `look`: `d` or `l`, the screen's look.
- `cap`: the most bytes one decoded picture may take on this screen. `fmt`: the formats its decoder takes, best first.
- `pace`: milliseconds until the next picture of a source that changes by itself (a camera); 0 or absent for once.
- `live`, and `sound`: this screen can stream to that rectangle, with the camera's sound. Absent on a board that does
  not stream. A source that streams (a camera) is then answered with a stream; any other with a still.

The answer is the screen message every picture has always come in, with `t` = `q` and the question's number:

```json
{"v": 1, "op": "camera", "t": "q", "n": 42, "u": "http://192.168.1.10:8098/camera/<token>.bmp", "m": {}}
```

`u` is a link on ESP Screen Manager's camera port (a still ends in `.bmp` or `.jpg`, a stream in `.mjpeg`), or empty
when there is no picture now. `m` carries what a picture brings beside its pixels (where the markers on a map are).
An alert's picture comes without a question: ESP Screen Manager sends it with the alert, as before.

## In ESP Screen Manager: one service

In `screen_manager/app/`:

| Module | Its one job |
|---|---|
| `picture_question.py` | reads a question (`q`) into one model and checks every number and text; what a screen can show (its boxes, its cap, its formats) |
| `picture_legacy.py` | reads the questions of older firmware (every shape since 0.2.57) into the same model, with the `t` and `e` their answers go back with |
| `picture_sources.py` | the source kinds: whether this screen may have one (one rule set for the core and for plugins), and getting it, reading the app through `Providers`; the cameras' snapshots and the players' covers, fetched once for every screen, in the screen's own rhythm |
| `picture_paint.py` | one way to make a picture for its places: read (JPEG, PNG, HEIC, EXIF turned), fill or show whole, round, shade, dim, turn, mirror, the atlas of several places, and the format the screen takes (BMP 8-bit, 24-bit, baseline JPEG) |
| `picture_links.py` | the camera port: links that last a while, a 304 for an unchanged picture, the streams' links beside them |
| `lan_address.py` | where the screens reach the app: the address the links carry, on the screen's own network, with the published port |
| `picture_service.py` | a question in, an answer out: authorise, get each source, paint, link or stream |
| `plugin_pictures.py` | what a plugin's manifest allows its places, and the pictures at its addresses, kept by address |
| `camera_source.py` | a camera live: one source per camera for every screen that watches it (Home Assistant's WebRTC, else snapshots), its stills first and its sound |
| `live_pictures.py` | a live camera's frame as the screen takes it: sized for the rectangle it asked for, its own JPEG untouched where the decoder takes it, made once per frame and room |
| `live_stream.py` | how a live camera travels: its links, the stream on the camera port, the tiles' cameras a full view keeps running, a Live tile's pace |
| `server.py` (`HomeAssistant.picture_bytes`, `picture_address`) | one way to read a picture from Home Assistant or the internet: a byte limit per kind, Home Assistant's token only to Home Assistant, no redirects, nothing from an address in the house unless Home Assistant serves it |

A camera has one source in the app for both routes: while a stream of it runs for a screen, a still of it (a tile, an
alert, the screensaver) is that stream's newest frame, not another snapshot from Home Assistant.

## On the screen: one loader, one store, two presenters

- **The question** (`picture_question.h`): every owner builds the same `Question`; one function sends it
  (`runtime_tiles::picture_ask`), as a question to an app whose hello says `pictures`, or as the fields an older app
  reads; one count numbers every question, and an answer finds its owner by its number.
- **The loader** (`picture_loader.h`): decides between owners, one download at a time, the most urgent first.
- **The download** (`picture_fetch`): beside the main loop, into a buffer of its own in one of three slots (the full
  view and the cards, an alert, the tiles).
- **The store** (`picture_store.h`): every still on the glass and on kept pages, within one budget from the board's
  PSRAM. The streams that run take their share of the same budget (`live_view::held_bytes`, at most half of it), and no
  picture is ever larger than the store can keep (`picture_store::cap_for`).

### Memory

One picture is in memory once. The store takes a finished download's buffer over as it is (`picture_store::adopt`) and
the slot lets go of it (`picture_fetch::hand_over`), keeping its link's ETag so an unchanged picture still answers 304;
nothing is copied. The picture it replaces, a camera's last frame or the photo before, stays on the glass until its cards
show the new one and goes at the next `collect`. So a picture that changes over to the next one holds two buffers for
that moment, the one on the glass and the one that comes, and never three; every other moment it holds one. A slot that
cannot give its buffer away (the editor's WASM preview) is copied once into one the store owns. A 304 for a picture the
store let go meanwhile is loaded whole again (`runtime_tiles::picture_done`).
- **Two presenters**: LVGL draws a still from the store; `live_view` writes a stream past LVGL into the panel's frame
  buffer, with the rules of docs/CAMERA.md ("Nothing of LVGL's under a live picture", "One writer on the glass").

### Formats

The question names the formats the screen takes, best first (`fmt`), and the app picks per picture
(`picture_service.format_for`). Every board takes BMP: 8-bit where the owner allows it (a palette of the picture's own
256 colours, dithered), 24-bit otherwise; the screen decodes it row by row as it comes, without a copy. An ESP32-P4 and
an ESP32-S3 with PSRAM also take JPEG: their engine takes the format whole (`picture_engine::whole_formats`, which
`runtime_tiles::picture_ask` names first in every question), so the download gathers the whole JPEG
(`picture_fetch::Gather`, at most `MAX_JPEG`) and the engine decodes it, about a tenth of a BMP's bytes on the network.
A P4 decodes with the hardware decoder its streams use (`picture_engine::decode`, under the same lock of the 2D-DMA, the
glass's); an S3 with Espressif's software decoder, esp_new_jpeg, into a picture buffer of its own that LVGL draws as it
drew a BMP's rows, a row of MCUs at a time with a pause between, as its RGB panel reads its picture from the same PSRAM
(a 480 x 270 camera still in 28 to 45 ms on a Guition 4848S040). What such
a JPEG is (baseline, whole MCUs of 16, the shown size and the flat places' corners in an APP15 segment the screen makes
exact again) is one profile on both sides, `picture_jpeg.h` and `picture_paint.encode`, kept equal by `tests/test_camera.py`. A
photograph (a camera, a cover, a photo, a poster) goes in the format the screen named first, JPEG on a P4 or an S3 with PSRAM; a drawn picture
(a map, a vacuum's map: lines, words and flat colours, which JPEG blurs) goes as the first BMP the screen takes. Streams
are JPEG on every P4 (`live_view`); the P4 has a hardware H.264 encoder but no decoder, so the app decodes a camera's
H.264 and sends JPEG (`camera_source.py`, `live_pictures.py`).

## Capture: the screen's own camera

- The **board** names the sensor's I2C bus and clock (`CAMERA_I2C`, `CAMERA_XCLK_PIN`: the feature `camera_sensor`)
  and powers it. Nothing else of a camera is in a board file.
- The **Screen camera plugin** brings the camera, in layers, each in a folder of its own:
  - `esp_video_camera`: the ESP32-P4 camera driver (ESPHome pull request #16944), a copy of its release. Changes to it
    go upstream; a change we cannot wait for is marked and listed in its NOTICE.
  - a folder per sensor driver that Espressif's `esp_cam_sensor` does not have yet, with its image tuning.
  - `screen_camera`: the camera of the screen's device in Home Assistant (`ts_camera`, the feature `camera`), and what
    the screen works out from the camera itself, which never leaves the screen (light level, motion), off until a
    person switches it on.
- Motion wakes the screen through the plugin API (`tessera::wake`, 0.16), never a script of the core.
- **The core shows when the camera is in use**: a dot in the glass's top right corner, on top of everything (pages,
  cards, the full view, the screensaver), that no plugin or setting can take away. Home Assistant taking pictures or a
  stream the core sees by itself on `ts_camera` (`plugin_host::watch_camera`, bound when a plugin provides `camera`); a
  plugin that uses the camera on the screen itself says so (`tessera::capturing`, plugin API 0.17). The dot is solid
  while anyone watches (Home Assistant, or a plugin's `Capture::CAMERA`) and a ring while the camera only senses on the
  screen (`Capture::SENSING`, plugin API 0.20: a light level, motion), so a glance tells "seen" from "counted". It lies
  in the top bar's row, so it never lies over a live picture.

## Compatibility

- **An older screen with a newer app.** The app reads every question older firmware asks (`picture_legacy.py`) and
  answers it as that firmware expects. Nothing changes for it.
- **A newer screen with an older app.** The app says in its hello that it reads questions (`features: ["pictures"]`).
  Until a screen has heard that, it asks the way an older app understands (`picture_question.h`, the legacy fields of
  the same question), so a screen built from main before its app is updated still gets its pictures.
- **Plugins.** Everything of plugin API 0.10 to 0.16 stays. What 0.17 adds (below) only adds.
- When every supported app reads questions, the screen's legacy fields go, and later the app's legacy shapes: each in
  a release of its own, named in the CHANGELOG.

## For plugins (plugin API 0.17)

- A place without its soft block (`ui::picture(parent, Placeholder::NONE)`), for places that lie over each other or
  reach past their picture (a cover flow with reflections). A place is the core's: a plugin sizes and places it, never
  styles it.
- Whether a place's picture came: `on_picture(place, state)` on a tile, a card and a screensaver (`PictureState`
  `SHOWN`, `NONE`, `FAILED`), once per address, so a plugin can show something else where a picture does not come.
- The core's sources (`cover:<entity>`, `camera:<entity>`, `entity:<entity>`, `step:`) for a place of that entity, under
  the same rules as the core's own pictures.
- `slide_pictures` may be called from any call of a tile or card, `on_state` included.
- `ui::live(place)`: a tile's place with the address `camera:<entity>` of its own entity streams on a screen that
  streams, exactly as a camera tile set to Live (`runtime_tiles` live places: on the glass, the page still, nothing over
  it; its stills under it until the first live picture). Its question names the owner `plugin_tile` and `live`; the app
  answers with a stream into the place's room (`picture_service._stream`). A card's and a saver's places show stills.
- `tessera::capturing(plugin, Capture::CAMERA, on)` for a plugin that uses the screen's own camera on the screen itself
  while someone watches, `Capture::SENSING` (0.20) while it only senses.

A plugin never writes the glass itself: `live_view` is the one writer past LVGL, and a plugin's video goes into a place
it laid out. A plugin with video of its own one day (an intercom's caller over SIP and RTP, for instance) gets the same
way in: the stream's renderer stays apart from where its pictures come from, so frames a plugin receives can be handed
to a place as the app's stream is now. Its camera going out is a capture (`capturing`), with the dot.

## How it is tested

- ESP Screen Manager: the question and every legacy shape read into the same model; every source's rules; the painter
  against pictures made by the code it replaced (the same bytes, or a difference named and looked at); the links and
  304s; the streams.
- The screen, on a PC: the question built by every owner, its legacy fields, the answer routed by number, the store
  taking buffers without copies and keeping its budget with streams running.
- tools/render: every owner's question on a small, a middle and the largest glass; Tessera's own plugins built and
  drawn against the core of the same commit.
- On glass: a reTerminal D1001 (streams full screen and on tiles, stills, the photos screensaver, plugin pictures, its
  own camera in Home Assistant), a Guition ESP32-S3 (stills), and the CYD (no pictures, its flash budget).
