# Camera images on a screen

App 0.2.66 with firmware 0.2.57 shows camera images on every board with the memory (PSRAM) for them:
the 4-inch, 7-inch (JC1060P470 and V2) and 10.1-inch Guition, and the 4B, 4.3-inch and 7-inch Waveshare.
The CYD, the Waveshare 3.5-inch and the Hosyond 4-inch cannot (see below). Which boards can is
`camera` in `screen_manager/app/boards.json`, worked out from whether the board file includes
`packages/features/camera.yaml`. The numbers further down were measured on the 4-inch Guition.

- **A camera tile.** Add a `camera.*` or `image.*` entity as a tile. A tap opens the image full
  screen, with the round back key at the top left like every card, and a spinner until the first
  image is there (firmware 0.2.73). The image is refreshed every four seconds while it is open. It
  is not video: ESPHome has no video decoder. A P4 board plays the camera live instead (see
  [Live on the P4 boards](#live-on-the-p4-boards)).
- **An alert with a picture.** Add `camera: camera.front_door` to the `esp_screens_show_alert`
  event, and `screen: hallway_screen` for one screen only (app 0.2.133). The screen's own actions
  `esphome.<screen>_show_alert` and `_show_alert_choice` have no `camera`: Home Assistant makes every
  field of an ESPHome action required, so a new field would break every automation that calls it.
  The event also takes the second button (`button2_text` and the rest, app 0.3.8, firmware 0.3.3). The card shows the picture of that moment (it stays that picture), with the card's round
  corners (firmware 0.2.73); a tap on it opens the camera full screen over the alert, and Back
  returns to the alert. Since firmware 0.2.103 the card makes room for the picture in the picture's
  own proportions: a wide camera across the top of the card, a square or standing doorbell camera
  on the left of the words where the glass is wide and low (the button stays on the right). Until
  the picture arrives the card shows a camera icon where a 16:9 picture would go, and then takes
  the picture's shape. The picture keeps one size in millimetres on every board, at most about
  58 x 45 mm, so a big screen shows it as a phone-sized picture, not a poster.
- **How the picture travels.** The app fetches the camera's snapshot once for all screens, reads its
  size from the file's header (turned the way its EXIF says), works out for each screen the frame
  its card makes for those proportions (the same rule as the firmware, `screen_manager/app/
  alert_layout.py`) and scales the snapshot once per frame size to exactly that frame. Screens that
  draw the same frame share one picture; frames of different sizes are made at the same time, from
  the same snapshot, and each screen gets its own link to its own size. The frame is worked out
  from the density and look the screen reports itself, so an Override YAML that changes
  `DISPLAY_DPI` is followed. The screen gets a BMP that is its frame, pixel for pixel: about 350 KB
  at the standard look's density, up to about 430 KB for a square picture on the denser 4.3-inch.
  Firmware before 0.2.103 has one fixed frame and gets the picture fitted into it.

The CYD has no memory for images (a 320×180 image needs 115 KB in one piece, the CYD's largest
free block is about 45 KB), and neither have the Waveshare 3.5-inch and the Hosyond 4-inch (no
PSRAM). They show the alert without the picture, and the app refuses a camera tile on them ("This
screen cannot show camera pictures", `server.py` and `page_service.py`).

## The album cover on the media card

App 0.2.77 with firmware 0.2.64 uses the same road for a media player's picture. The media card
(a tap on a media player's tile, or a media tile of size *Full page*) shows the album cover of
what plays, with the title, the artist and the album, a progress bar and the keys under it.

- The screen asks Tessera Screen Manager for the cover with the size it draws it at and the colour
  behind it (the event `esphome.screen_camera` with `size` and `bg`). The app fetches the
  picture through Home Assistant's own proxy for the player (`/api/media_player_proxy/...`), cuts
  it square, sizes it, rounds the corners over that colour and serves it on port 8098 as a BMP,
  like a camera image.
- Home Assistant's token goes to that proxy only (app 0.4.15). A player whose picture lies on the
  internet or on a server in the house hands out the picture's own address and the proxy beside
  it, and the app takes the proxy, so Home Assistant fetches the picture itself. A player that
  hands out an address without a proxy gets its picture fetched from the internet only, never from
  an address in the house, and without following a redirect.
- A cover is fetched once per picture: the state carries a short mark of the picture, and the
  screen asks again only when the mark changes (a new track), when the card opens again or
  when the page turns back to a full-page media tile. Nothing polls.
- A player without a picture (a radio station, a player that is off) keeps the player's icon in
  the cover's place; the app answers with an empty link and the screen stops asking.
- A board without camera pictures (CYD, Waveshare 3.5, Hosyond 4-inch) has no place for a cover on its media card
  or on a media tile over the whole page (firmware 0.46.0): the title, the bar and the keys stand together in the
  middle and take the room, with shuffle and repeat where they fit. Before, an empty square with the player's icon
  stood where a cover never came.
- One picture loads at a time, the most urgent first (see "One route for every picture" below). An alert closes an
  open card and its cover. Under a media tile of size *Full page* the alert's picture goes first: a cover already on
  its way finishes, and the tile's cover follows the alert's picture.
- A new track keeps the card's cover and colour until the next cover is here, then changes both at once. A media tile
  over a whole page on a kept page has its next cover fetched ahead while the screen is in use, after everything on
  the glass.

## A live picture on a camera tile

App 0.2.91 with firmware 0.2.77 puts the camera on the tile itself: **Display → Live picture** in the
tile's settings, with a pace of 15 or 30 seconds (`refresh`; 5 and 10 seconds too from app 0.3.13). The
picture refreshes while that page is on the screen, and a tap still opens the camera full screen. From
app 0.3.13 with firmware 0.3.7 the picture fills the whole tile on every size (see
[A camera that fills its tile](#a-camera-that-fills-its-tile)). Older firmware shows a small square of the
camera's view in the icon's place of a single, double-width or full-page tile: the middle of the snapshot
cut square with the tile's rounded corners, delivered as described below.

- **A picture per tile** (firmware 0.52.0, GitHub #183). Every tile with a picture asks for its own: a live camera,
  a media tile's album cover, a favourite and a map. The screen asks Tessera Screen Manager with the event
  `esphome.screen_camera` as for a page of one tile: `tiles` the entity, `idx` the tile's index (the app prepares the
  picture the way that tile's settings say), `bg` the colour behind its corners, `dark` the look, and `atlas` one
  frame at the top left with the picture's size in pixels, its corner radius and its shade
  (`components/smart_display/tile_picture.h`). The app answers with a link to a BMP of exactly that frame and the
  question's number, by which the screen finds the tile. Every app since 0.3.8 answers this question, so a new
  screen works with an older app too.
- **A plugin tile's places** (plugin API 0.10, docs/PLUGINS.md, "Pictures on a plugin tile") ask the same question
  with an atlas of several frames, one per place, and `src` and `fit` beside it: one picture for a tile of eight
  posters, each place its piece of it.
- **Each at its own pace.** A camera tile loads its next picture when its own pace has passed, 5 to 30 seconds. The
  app fetches the camera just before that load, at the pace of the quickest of its tiles (as for the full view below),
  so the picture on a tile is a fraction of a second old when it comes, not a whole pace. A new
  track replaces the cover of its tile and sends no camera again; a page of covers alone loads once per track. The
  picture comes whole every time, never as a 304. Nobody loading means nothing fetched, as with the camera full screen.
- **No picture smaller for another.** The size cap (below) holds for each picture alone, so a page of five 2 × 2
  cameras on the 10-inch glass shows every one at the full size of its tile, whatever else the page holds.
- **After the other pictures.** One picture loads at a time, the most urgent first: the alert's picture, the camera
  full screen, an open card's cover, then the tiles on the glass, and last what is fetched ahead for a page out of
  sight, which breaks off for them. Of the tiles, one that has no picture yet goes first, then the one whose picture
  is oldest, so cameras at the same pace take turns. Asking goes at once for all tiles of the page; a download waits
  for the finger to leave the glass and the pages to stand still. In standby it keeps loading while the tiles are seen
  (firmware 0.40.0+, `runtime_tiles::tiles_seen`): no screensaver over them, the clock included, and the glass at 5 %
  or more. A screensaver or a darker glass stops it until the screen wakes. Dark mode (other colours behind the
  corners) or a changed tile asks for a new picture.
- **Kept pages.** On a board with PSRAM (`picture_store.h`) every tile's picture is kept under its own key, so turning
  back shows them at once, and each camera loads its next picture at its own pace. A cover, a favourite or a map of a
  kept page is fetched ahead while the screen is in use; a camera of a kept page is not.
- **Until the next one comes** a card keeps the picture it shows of the same place: the last track's cover, a map
  before someone moved. Until the first picture arrives, a camera card shows a spinner.
- **A camera without a picture** keeps its icon: the app answers with an empty link.
- **A media tile's album cover** (app 0.2.92, firmware 0.2.78): **Display → Album cover** on a single or
  double-width media player tile. The app fetches the player's picture only when its address changes (a new track);
  the screen asks again the moment the picture's mark in the player's state changes. A player without a picture keeps
  its icon; the tile over the whole page keeps the card's big cover.
- **The library while nothing plays.** A media player's tile on *Album cover* that is 1 x 2, 2 x 2 or larger shows
  the covers of the player's library while it has nothing to show (idle, on, off or standby, or paused with no song,
  and no picture of its own), darkened as much as a cover under its track. The app takes the first folder of the
  library that holds songs (Spotify's "Liked songs", newest first), else albums, else playlists, each picture once,
  and reads it again every half hour. The covers stay square and all one size, two along the tile's shorter side and
  as many along the longer one as fill it; what reaches past the tile is cut off evenly at both ends, never squeezed.
  Every minute one of them moves on to the next cover of the folder: the one longest on the tile goes, and none shows
  twice. It is the tile's own picture by a mark in the player's state, so the firmware asks for it as for a cover and
  nothing in the firmware changed; a screen gets it once its firmware draws a player's extras (0.24.0+). A library
  whose pictures the app may not fetch, such as Music Assistant's covers of files in the house, which come from an
  address in the house, keeps the tile as it was. The rules are in `screen_manager/app/rest_mosaic.py`.
- The tiles' pictures come through the third of the screen's three downloads (`picture_fetch::live`, decoded into
  PSRAM), bound in `packages/features/camera.yaml`, which every board with camera pictures includes; the CYD, the
  Waveshare 3.5 and the Hosyond have none.
- **Older firmware** (0.51 and before) asks for all the pictures of a page at once, and the app still answers it that
  way: one image spanning them all, from the top left of the first picture to the bottom right of the last (firmware
  0.3.1+), or a strip of squares, top to bottom, before firmware 0.3.7. That image was under one cap for the whole
  page, so on a large glass every picture of a page came smaller as soon as one more tile had a picture.

### A camera that fills its tile

From app 0.3.13 with firmware 0.3.7, a live camera fills the whole card on every size: a single tile, a
double-width one, a 1 × 2 or 2 × 2 tile and a tile over the whole page. Two cameras that film in 16:9 fit
side by side on the 4-inch Guition, one single tile each. App 0.3.8 with firmware 0.3.3 did this on 1 × 2
and 2 × 2 tiles only. Two settings appear in the tile's settings with the live picture:

- **Picture**: **Fill the tile** (`fit` left out, the default) cuts the picture to the card, the way a
  photo fills a frame. **Whole picture** (`fit: contain`) shows all of it, with black above and below
  or at the sides.
- **On the picture**: **Name** (`overlay` left out, the default) writes the tile's name at the bottom
  in white. **Nothing** (`overlay: none`) leaves the picture alone.

The screen does none of this work. The screen asks for each picture at its card's exact size in pixels
(`atlas`, see above), and the app answers with a BMP that already has its crop or its black bars, its rounded corners
and, under the name, a soft shade that keeps white text readable on a bright picture. The screen draws that image as
it is. A smaller picture does not load faster: the picture already has exactly as many pixels as the card shows. What
sets the pace is the refresh the tile chose and the time the camera takes to answer. On the 4-inch Guition two single
tiles side by side are about 25 KB each per refresh, and a tile over the whole page about 160 KB. A refresh every 5
seconds works there, but the larger the picture and the slower the Wi-Fi, the longer the screen spends reading it.

From app 0.4.13 with firmware 0.9.0 no picture is larger than 1024 pixels either way or 1.25 MB once the
screen has decoded it, on a board with 8 MB of PSRAM. Since firmware 0.52.0 that cap holds for each tile's picture
alone, and a board with more memory takes larger pictures: one picture may be a third of its picture store, up to
2048 pixels a side (`picture_store::cap_for`). The P4 boards with 32 MB keep 6 MB of pictures, so 2 MB a picture: the
10-inch glass gets a camera over its whole page, its full view, a map and the screensaver at its own 1280 x 800. The
screen says so with `cap` (the bytes) when it asks for a picture of the whole glass, and the app honours up to 4 MB
(`picture_question.cap_of`); an older app keeps the common cap. A picture that is still smaller than its place sits in
the middle of its card on a dark ground, so the name under it stays readable.

A screen with firmware 0.3.3 or newer gets its live pictures in 8-bit colour: a palette of the picture's own
256 colours, dithered so a shade stays smooth. That is a third of the bytes of a 24-bit BMP (a 2 × 2 card
on the 4-inch Guition: about 100 KB instead of 300 KB), at about the quality of the screen's own 16-bit
colour. The screen decodes a BMP while it downloads, so fewer bytes means a picture that arrives sooner.
Preparing the palette costs Home Assistant a few milliseconds per picture, also on a Raspberry Pi. Older
firmware keeps 24-bit pictures.

The camera's state ("Idle") is not written on the picture. Until the first picture arrives, the tile
shows a spinner; a camera that has no picture for Home Assistant (a camera that only streams) keeps its
icon and name as any tile does. Firmware before 0.3.7 ignores both settings on a single, double-width
or full-page tile and keeps the small picture in the icon's place there.

## A doorbell

The doorbell's own event, `esp_screens_doorbell`, opens its camera live with its sound on the ESP32-P4 screens and shows
its picture in an alert on the others (docs/DOORBELL.md). An alert alone brings the doorbell's picture along:

```yaml
triggers:
  - trigger: state
    entity_id: event.front_door_ding
actions:
  - event: esp_screens_show_alert
    event_data:
      title: Someone is at the door
      icon: doorbell
      camera: camera.front_door
      timeout: 60
```

Any `camera.*` entity works, and so does an `image.*` entity, such as the snapshot a doorbell or
motion integration keeps of its last event.

## How the image gets to the screen

The screen never talks to Home Assistant about images, and it never holds a Home Assistant token.

1. The screen asks Tessera Screen Manager for a camera (the event `esphome.screen_camera`), or the app
   sends the picture of an alert by itself.
2. The app fetches the snapshot from Home Assistant with its own access (the same pictures the
   Home Assistant frontend shows), and makes it exactly as large as the screen draws it: full screen
   at most the board's canvas (`camera.full` in boards.json: 480×480 on the 4-inch Guition, 800×480 on
   the Waveshare 4.3, 5 and 7, 1024×600 on the JC1060P470), an alert card at its frame (`camera.thumb`,
   392×220 on the 4-inch Guition), proportions kept. Neither is ever larger than the cap above
   (`picture_question.MAX_SIDE` and `MAX_BYTES`): the JC8012P4A1's 1280×800 canvas gets a
   full-screen picture of at most 1024×640, shown in the middle.
3. It serves the result as an uncompressed BMP on **port 8098** under a random link, and sends the
   link to the screen. The screen downloads it in a task of its own, beside its main loop
   (`components/smart_display/picture_fetch.cpp`, firmware 0.49.0+), and decodes the rows as they arrive straight
   into the pixels LVGL draws: touch, drawing and Home Assistant never wait for the network. Before, ESPHome's
   `online_image` downloaded in the main loop, 16 KB a turn, each turn waiting for its chunk; a page of album
   covers held the glass still for two to three seconds and a camera picture for the better part of one. A
   screen on another network or VLAN than Home Assistant needs to reach this port on Home Assistant's host;
   without it a camera tile shows its name and state but no picture, and the screen's log says
   `no connection to` the link's address. The full screen, the alert and the cover are 24-bit; live tile
   pictures go to firmware 0.3.3+ in 8-bit (see above).

While a camera is open, the screen loads its link every four seconds, one image at a time. Each load sets the
camera's next fetch for just before the next load: four seconds on, less the time the camera took to answer last
time and half a second (`picture_sources.Snapshots.ahead`), so the next load finds a snapshot a fraction of a second old
and the picture changes at the screen's steady pace. A load whose fetch is still on its way waits up to 1.5 seconds
for it, then takes the last snapshot. (Firmware before 0.52.0 got the snapshot fetched at the load before, a picture
four seconds old; a fetch on its own clock next to the screen's made the picture change after 1.5 s one time and 6 s
the next.) A slow camera makes the images older, never the screen slower, and nothing queues up. Nobody loading means
nothing fetched, beyond the one fetch the last load set. A link that nobody loads for two minutes stops working; an
alert's picture stays for half an hour.

**Why BMP.** ESPHome decodes a BMP piece by piece while it downloads (16 KB per round of its main
loop since firmware 0.2.73, 4 KB before). A JPEG of the full screen took 0.6 s in one piece on the
Guition, during which the screen missed taps. A full-screen BMP is about 390 KB; on the bench
Guition it comes in about 1.8 s (2.8 s with 4 KB).

## Live on the P4 boards

A camera opened full screen on a board with an ESP32-P4 (the reTerminal D1001, the M5Stack Tab5, the Waveshare
ESP32-P4 panel and the Guition P4 boards) plays live, at the camera's own pace, about a tenth of a second behind the
camera. An ESP32-S3 board with an RGB panel plays live too, one tile at a time (see
[Live on an ESP32-S3](#live-on-an-esp32-s3)). Every other board keeps the still of every four seconds above. A map, an
image entity and the screensaver stay stills on a P4 too.

**How it travels.** The screen asks for the camera as for a still, with one key more: `live`, the room below its top
bar in pixels (`1280x715`). An app that knows streams answers with a link on its camera port that ends in `.mjpeg`; an
older app answers with a still, and the screen shows stills. The link serves `multipart/x-mixed-replace`: one baseline
JPEG a part, each with its Content-Length and X-Made (the app's clock in ms as it leaves), over plain HTTP/1.0. The
app makes the next picture once the last one has left its host, always of the newest frame the camera gave. Between
the app and the screen a dozen of a tile's small pictures still fit (the app's socket buffer, the screen's TCP window
of 64 KB), and a tile that read them one by one showed pictures a second old. So a live tile asks for each picture
instead: GET on the same link with `.jpg` for `.mjpeg`, over a kept connection (HTTP/1.1), and the app answers with the
JPEG of the camera's newest frame once it is newer than the last it sent on that link, or 204 after 2 s, and the tile
asks again; the link counts as a stream from its first ask until 3 s after its last answer. A tile asks at most six
times a second (hw::LIVE_TILE_PPS): the picture engine's budget of pictures a second shared among the tiles that stream
(`picture_engine::tile_pps`, 24 on a P4, so four tiles keep six each), never fewer than two; a busy screen's tile asks
half or a quarter of that (docs/PLATFORM_PLAN.md 4.10). An app without it answers
404, and the tile reads the stream, showing the newest picture that reached it and passing the older ones; the app
keeps a tile's socket buffer at 16 KB. Its line in the screen's log every 10 s says how long it waited for the app,
how long its pictures waited on the way and how many older ones it passed.
The app serves at most eight streams at once, of every screen together (a page of live tiles and a camera full
screen); a stream it refuses leaves that screen with its stills. A screen runs at most seven of its own. The editor's
camera card says how many of the eight are in use now ("3 of 8 live streams in use, across all screens", the inventory's
`live_streams`), and the app's log names each refused camera with its screen and why, once a minute for each:
`Live camera.door refused for Kitchen (a tile): Too many live cameras; 8 of 8 streams in use, of every screen`.

**Where the pictures come from** (`screen_manager/app/camera_source.py`; the JPEG per room is `live_pictures.py`, the
stream on the camera port `live_stream.py`). Most of the work lands on Home Assistant's host,
often a Raspberry Pi, so each kind of camera takes the cheapest road:

- A camera with a stream of its own (an RTSP camera through Generic Camera, ONVIF, Reolink, UniFi Protect and others)
  comes through Home Assistant's WebRTC: its built-in go2rtc relays the camera's H.264 as it is, and the app receives
  it with aiortc and decodes it with PyAV. The P4 cannot decode H.264 (its hardware encodes it, and Espressif's
  software decoder takes only the baseline profile most cameras do not send), so Home Assistant's host does, once per
  camera however many screens watch it. The JPEG is made straight from the decoder's YUV with FFmpeg's encoder, at the
  camera's own size where that fits the room, or scaled down to it. Until the first frame (WebRTC waits for the
  camera's next key frame, a few seconds on some cameras) the screen gets the camera's still, again every two seconds,
  each such part marked `X-Picture: still` (see "Until it is live" below). The app offers WebRTC without a STUN server:
  it and Home Assistant share a network, and gathering a STUN candidate first cost about five seconds.
- Any other camera (a snapshot camera, an ESPHome camera, a picture an integration draws) gives its snapshot, asked again
  as soon as the last one came, at most 15 a second. A JPEG the P4 decodes as it is (baseline, at most 1920 pixels a
  side) goes out untouched, which costs the app nothing; anything else is made into one.
- A camera whose WebRTC does not start within 20 seconds sends its snapshots instead, and tries WebRTC again every
  minute while anyone watches it, its snapshots going on meanwhile: a camera back from its privacy mode, or a go2rtc
  that was away, plays live again without the screen closing it. The log says the first failure and, once, when it
  works again (`Live camera.door: WebRTC works again at try 3, after 121 s of snapshots`).

**Every frame looked at** (`camera_source.FrameWatch`). Each decoded WebRTC frame is checked before a screen gets it:

- a frame the decoder marks corrupt (`is_corrupt`, after packets that never came) is left out, and the screen keeps the
  one before;
- a gap in the frames' timestamps (frames that never came), a flash (the picture at least 1.25 times and 8 steps of 255
  brighter than the median of its last frames, falling back at least halfway within 15 frames: one bright frame or a
  second of them, as a camera's own jump of exposure), the packets lost on the way, the
  NACKs and PLIs the app sent back (aiortc asks the camera for a new key frame after a loss it cannot mend), the JPEGs
  a screen would refuse and the stills are counted;
- the app's log says them every 10 seconds when anything but frames was counted, a flash at once with its timestamp and
  the brightness of it and its neighbours, and the totals every 5 minutes whatever they are:
  `Live camera.porch: 150 frames (2 key), 0 corrupt, 0 missing, 0 flashes; 0 packets lost, 0 NACKs and 0 PLIs sent; 0
  JPEGs the screen would refuse, 0 stills in 10 s`.

The brightness comes from a grid of 40 x 24 pixels that FFmpeg's scaler picks in grey: 0.05 ms for a 1080p frame. For
evidence, an empty file `tessera_frame_dump` in Home Assistant's config folder makes the app keep each flagged frame,
the two before it and the two after it as JPEGs 480 pixels wide in `tessera_diagnostics/frames/<camera>/` there, at most
50 in all, the oldest going first; delete the file to stop it.

**What it costs Home Assistant's host.** Decoding costs what the camera's resolution costs, so give a camera's tile the
camera's low-resolution stream where the integration offers one (most do, as a second camera entity). Measured on a PC
(2026-10-10, an EZVIZ camera): its 512 x 288 stream at 8 frames a second took 2% of one core for everything (receiving,
decoding, JPEGs, sending), its 1920 x 1080 stream at 15 frames a second about 15%. A Raspberry Pi 4 core is several times
slower, so on a Pi the low-resolution stream is the one to take. A JPEG from YUV took 1 ms for 512 x 288 and 7 ms for
1080p scaled to 720p, where Pillow from RGB took 3 and 19.

**On the screen** (`components/smart_display/live_view.h`). A task of its own reads the stream, decodes each picture with
the P4's hardware JPEG decoder and has the PPA scale it to fill the room and turn it the way LVGL turns its own drawing,
straight into the panel's frame buffer. LVGL would take 200 ms to draw such a picture, with touch waiting meanwhile;
past LVGL the main loop is not involved at all. The back key and the name stay LVGL's, on the view's black above the
picture, and while the camera streams LVGL draws nothing in the picture's room (a card on the page behind it that
changes would otherwise paint the view's black over the picture until its next frame). A stream that breaks is asked
for again; after three breaks the view shows the stills of every board. The panel's frame buffer is found as ESP-IDF
makes the panel for ESPHome's display (a linker wrap of `esp_lcd_new_panel_dpi`), so every display platform on a P4
serves.

Measured on the reTerminal D1001 (2026-10-10):

| The camera's stream | Pictures | Decoding | Scaling and turning |
|---|---|---|---|
| 512 x 288, scaled 2.4 times by the screen | 8 a second, the camera's pace | 2 ms | 15 ms |
| 1920 x 1080, sent as 1264 x 704 | 15 a second, the camera's pace | 10 ms | 48 ms |

Home Assistant's LL-HLS was 0.6 to 1.2 seconds behind the same camera and came in bursts of a second; its WebRTC 0.12.

**Until it is live.** The stills before WebRTC's first frame show at once, but they stand still, so the screen says
they are not live yet: a live tile (and a plugin's live place) turns the firmware's spinner, small, in its top right
corner on a round shade, and the full view turns it at the right of its top bar, the place its sound key takes once
the picture is live (the sound comes with the live stream). The stream's task draws the tile's loader itself,
over the picture it composed and every 50 ms between the stills, since LVGL draws nothing over a stream; the full
view's is LVGL's, beside the picture. The first part without the mark ends it, and `live_view` tells its owner
(`Event::LIVE`, logged as "stream N: live after ... ms"). A camera without a stream sends no marks, so it is live from
its first picture, and so is everything an older app sends; an older screen reads the mark as a header it does not know.

**Live tiles.** A camera tile with **Display → Live picture** has one more pace on a P4: **Live**, its first and default
one, so a camera tile on a P4 is live unless its pace says otherwise. The editor offers it for a screen that streams
(its hello says `live`, or, while it is offline, a P4 board with pictures); any other screen refreshes such a tile at 15
seconds, which is also what firmware before it makes of the pace (0). A live tile streams while it is on the glass, the
pages stand still and nothing lies over them (a card, the camera full screen, an alert, the settings, the screensaver);
until its first live picture, and whenever it does not stream, it shows its last still as every camera tile does. It
asks for its stream with its picture's question and `live`, the card's size; the app sends its pictures plain at that
size (cut to fill it, or whole, as the tile says: the link ends in `?fit=contain` for a whole one), and the screen lays
over each of them what the app bakes into a still: the card's rounded corners over the page, the shade under the name
(the bottom 42 %, to 150/255 black) and the name as LVGL draws it. A camera opened full screen from a live tile has its
first picture in about 0.3 seconds instead of five: the tile's streams stop before the view's own stream is opened
(`live_begin`, not the next drawing's `live_stop_covered`, so no tile's picture lands under the view once LVGL has drawn
it), and the app's source of the camera, still running, has the newest frame ready. At the view's first picture the
screen draws the whole glass once more (`glass::redraw_all`, as it does when the view's stream ends): the bands of the
room around the picture, the top bar, and whatever a tile's last picture left under them. The other way round, the cameras of a screen's live tiles keep running in the app
for as long as that screen's full view streams (`LiveFeed.hold`), so its tiles are live again within a tenth of a second
when it closes, rather than after the seconds a WebRTC session takes to start. Measured on the reTerminal D1001 with the EZVIZ: a 2 x 2 tile of its substream at
8 pictures a second (decoding 2 ms, laying out 32 ms), a single tile of its main stream at 15 (1 ms, 11 ms), beside each
other.

**Four at once.** A P4 screen streams at most four live tiles at a time (`caps.live_tiles`, PLATFORM_PLAN.md 4.1): the
first four on the page stream, the others show a still every 15 seconds, and the log says so ("4 live tiles stream; 1
more on the page keep their stills (at most 4 at once)"). What four cost, measured on a reTerminal D1001 with its own
video watched by three viewers beside them (2026-10-25): 4.2 to 5.4 pictures a second each with laying out a picture at
122 to 134 ms, against 12 to 14 at 60 ms with two; the video kept 12 fps, the panel never ran dry and 142 KB of internal
RAM stayed free. The PPA, one device for every copy to the glass, is the limit, not the memory, and that is the reason
for four. A screen counts the connections of its streams and downloads into ESPHome's socket total
(`smart_display/__init__.py`, `_sockets`, and the video's server in Screen camera): with ESPHome's own count of 12 the
four streams and the video's viewers took every socket, and the fifth tile's still found no connection. A still that
fails waits its tile's pace before it is tried again (`picture_loader.h`), where it was tried every second.

**The camera's sound.** On a P4 with a speaker (a board that includes `features/audio.yaml`) the full view plays the
camera's sound, with a key at the right of its top bar that mutes it; muted stays muted for every camera until the
screen starts again. The screen asks with `sound`; the app takes the sound through Home Assistant's WebRTC too, makes it
16-bit mono at 16 kHz and sends it in the same stream as parts of their own (`audio/x-s16le`), as it comes, never
waiting for a picture's turn. On the screen the sound goes to the board's media speaker (`ts_media_speaker`), whose
resampler makes it the bus's rate, whatever the board's: nothing in a board file is needed for it, the volume under
Extras holds for it, an announcement plays over it, and on a board whose microphone and speaker share one bus the
microphone pauses while it plays, as for any sound. A live tile on a board with a speaker asks with `sound` too: the app
then takes the sound along in the tile's own WebRTC session (and drops it while nobody listens), so the full view opened
from that tile has its sound at once.

**Nothing of LVGL's under a live picture.** A live picture writes past LVGL, so it stops the moment anything LVGL draws
lies over its room, and starts again once nothing does. What counts follows LVGL's own order of drawing
(`drawn_over` in `runtime_tiles.h`): on the way from the tile or the camera view up to its screen or layer, every object
that comes after it (a card opened on the page itself, as a lamp's colour card is); for a tile, anything on the top
layer (the update's progress, an alert, the camera full screen, the screensaver) and its page no longer on the glass;
and anything on the system layer. A plain, clear container is not in the way by itself, only what it holds. No list of
overlays: one that comes later is covered by the same rule. Beside it, every card over the page (the detail card, the
colour card, the effects and lamps pages) is one notion, `card_open()`, which stops the live tiles of the page at once. The check runs on the board's 50 ms interval and as LVGL starts every
drawing (`LV_EVENT_REFR_START`, `live_stop_covered`), so it also holds for a drawing the main loop does not run for: an
update holds the loop and has its progress drawn at once.

**Nothing of LVGL's over a live picture.** While a picture streams, LVGL must not draw its room: what it has there (the
full view's black, a tile's still with its spinner and name) would cover the live picture until its next one. So the
list of what LVGL is about to draw is cut against where the picture of every stream lies (a tile's whole card, a full
view's picture as large as fits its room; beside a picture of another shape LVGL draws the room's black itself), once,
as LVGL starts drawing (`LV_EVENT_RENDER_START`, `keep_out` in `glass_dsi.cpp`). That one place catches every way LVGL
comes to draw there: a card that changes beside a tile, an area queued before a stream's first picture, two areas LVGL
joined into one, and the whole glass, which LVGL draws when more areas come in one frame than its list holds. Each piece
goes through the display's own rounding, as LVGL's own areas do. When a picture lies elsewhere or at another size (a
doorbell's 16:9 snapshot first, then its 4:3 stream), LVGL draws where the last one lay again, so nothing of it stays
beside the new one. When a stream ends, LVGL draws its room again.

**The panel's share of the memory bus.** The DSI bridge reads the frame buffer from PSRAM without pause, a frame
every 16 ms. When another DMA holds the bus too long (the PPA scaling and turning a picture, the JPEG decoder, the
DMA2D that copies what LVGL drew), the bridge runs dry and the panel shows a frame of blue, its colour for no data;
ESP-IDF only logs that from its interrupt, on the UART. A tester with a Guition 10.1-inch P4 (pixel clock 70 MHz) saw
such flashes while a camera streamed. So the firmware does two things on a P4 (`glass.h`, "The panel's share of
the memory bus"). It watches: at the end of every frame the panel's own callback (ESP-IDF's `on_vsync`, which
ESPHome's display leaves free) reads and clears the bridge's underrun flag, so each frame of blue is counted where it
happened, with no eye on the glass. The count of blue frames stands in every stream report (`the panel ran dry N times
since boot`) and in Home Assistant as the diagnostic sensor "Panel misses", and once a minute the sensor "Panel watch"
says the minute in one line: "quiet" with the frames it saw, or how many flashes (runs of blue frames) out of how many
frames, for each flash who held the glass as it began (LVGL drawing or flushing, a stream, another writer), whether a finger was on the glass
and how many log lines came in the second before, and the DSI host's own error flags beside them (a blue that is no
underrun). The log gets the same line, once a minute and only after a flash. Home Assistant's history of the sensor is
the record a change is judged by. The flag comes with a mask the firmware takes off: the bridge only raises it for an
underrun past a line of the frame, and ESP-IDF sets that line to the panel's width, 800 of the 1280 lines of a 10.1-inch
panel, so an underrun early in the frame, which blues most of the glass, raised no flag while one late in the frame,
which blues the bottom, did. Until 2026-10-29 the count saw the second kind only, and the whole-glass flash a slider
drag or a log line brings read as "the D1001 counts none". And it shortens every PPA burst on the
screen from ESP-IDF's 128 bytes to 64, the streams' own clients and ESPHome's LVGL (which turns every flush of a turned
glass with the PPA) alike, through a linker wrap of `ppa_register_client`: between shorter bursts the bus turns to the
bridge. LVGL took the same way for the same underrun under its own PPA draw unit (lvgl/lvgl #9590). A copy takes a
little longer for it.

**A turned copy the 2D-DMA never finishes.** The P4's picture engine (the PPA) cuts a copy into units of 64 pixels
by 16 rows, and when the last unit holds fewer bits than the DMA's FIFO the DMA never counts it as received: the DONE
never comes and the task that asked waits for good on the driver's semaphore, without an error or a log line
(Espressif's hardware bug DIG-734). ESP-IDF knows and sets "bypass macro block order" for such a block, but in the
5.5 releases it works the leftover out from the input's width and height even when the block is turned, where the
hardware cuts the turned output (espressif/esp-idf #19023; the fix, 469aa16, is on master only). On a screen whose
glass is turned a quarter every copy is turned, LVGL's flush of each strip as much as a live tile's picture, so sooner
or later one hangs, the main loop stops behind it (it holds the glass, above) and the task watchdog restarts the
screen. A tester's M5Stack Tab5 (a 720x1280 panel shown as 1280x720, the one turned P4 glass) restarted every few
minutes with two live camera tiles; its crash record showed the crashed core idle, the sign of a main loop waiting
rather than working (2026-10-23). So the firmware guards every `ppa_do_scale_rotate_mirror` call through a linker wrap
(`ppa_guard.h`, `ppa_guard.cpp`): it works out both rules, the hardware's and the driver's, and a turned block the
hardware would stall on while the driver leaves the bypass off is copied in pieces, each of which the engine takes
whole; two in almost every case, never more than six. A block the driver takes as it is costs nothing. The log names
the first eight such copies (`ppa_guard: a turned copy of WxH would hang the 2D-DMA`); `tests/test_ppa_guard.cpp`
proves the pieces cover the block once and land where the whole would. Copies the guard calls safe stalled a Tab5 all
the same (docs/PLATFORM_PLAN.md 4.7), so since 2026-10-28 live pictures come turned from the app on a turned glass
(the hello's `picture_turn`, each picture's `X-Turn`) and go onto the glass in a straight copy; a tile lays its card
over each picture as it lies (PLATFORM_PLAN 4.12).

**The main loop and the C6's answers.** On a P4 the Wi-Fi runs on the ESP32-C6, and some things the main loop asks
about it (the signal strength for the Wi-Fi sensor, the access point, the power save mode at standby and at wake, the
whole setup of the Wi-Fi at boot) are questions to that chip over esp_hosted's RPC, answered over the same SDIO link
the pictures come in on. Each such wait gives up after 5 seconds, and ESPHome's task watchdog gave up on the main loop
after 5 seconds too, so when the link was busy (two live tiles, the video going out) a lost answer restarted the
screen instead of failing one call. Three screens showed it in one day: a reTerminal D1001 ten minutes after boot
with two streams just started, a Tab5 in the first minute of every boot while its two streams started (and ESPHome's
rollback then put the old firmware back), a Guition 10.1 with a live tile and the video. The main loop's stack at the
watchdog (docs/REPORTS.md) read `wait_for_sync_response` in esp_hosted's `rpc_core.c`. The answer is not slow, the
chip's work is microseconds: it is thrown away. esp_hosted's SDIO reader hands each received block to a copy task
through a double buffer, and when that task still holds the previous block (it waits on a full queue) the reader
frees the new block whole and logs `H_SDIO_DRV: task still writing Rx data to queue!` (espressif/esp-hosted-mcu #197,
open); an answer in that block never arrives, and the main loop waits the full 5 seconds for nothing. So every P4
board runs the task watchdog at 20 seconds (`packages/hardware/esp32p4-c6.yaml`): a lost answer is a failed call,
logged by ESPHome as the Wi-Fi taking long, and the screen goes on. While it waits, LVGL stands still: a standby or
a wake under that load comes 5 seconds late. A screen whose main loop truly hangs restarts after 20 seconds. The most
frequent of those questions was the top bar's: its Wi-Fi item read the signal at every draw, about once a second, so
`wifi_status::link()` now asks it at most every five seconds (`wifi_status::Signal`) and remembers it in between.

**A new firmware's first minute.** After an update ESPHome's safe mode keeps the new firmware on trial until it has
run a minute (`boot_is_good_after`); a restart before that and the bootloader puts the old firmware back, with every
fix it held and its crash record. A P4 screen with live tiles starts its streams in that same minute, while the Wi-Fi
on the C6 is set up over the SDIO link the pictures come in on, and a Tab5 with two live tiles fell back that way on
every update, the watchdog of 20 seconds or not. So live streams wait while the running firmware is on trial
(`boot_trial.h`: the partition's state is `ESP_OTA_IMG_PENDING_VERIFY`, read every two seconds until it is confirmed):
the live tiles and places show their stills and the full view asks for stills, and the first round after the
confirmation starts them. The log says `boot_trial: A new firmware on trial` and later `The new firmware is
confirmed`. An ordinary restart is never on trial, so its streams start as before. A restart after the minute leaves
the new firmware in place, and its next boot logs where the main loop was (docs/REPORTS.md).

**One writer on the glass at a time.** LVGL holds the glass for the whole of each refresh (from `LV_EVENT_REFR_START`
to `LV_EVENT_REFR_READY`: deciding what to draw, drawing it, flushing it to the panel) and a stream's task holds it for
each copy of a picture, one recursive mutex, the glass's (`glass.h`: `hold` and `release`). Without it a stream's first picture could land
while LVGL was still drawing the still and the name it had decided on before the stream armed, and that drawing then lay
over the picture until the next one: a tile's name stood over its live picture after the camera full screen closed
(2026-10-12, the D1001). `close()` takes the same lock, so once it returns nothing of the stream writes the glass.

**A live picture stays where its card was.** A stream writes at the room its card had when it asked. The moment that
card lies elsewhere (a page animated, a layout made anew) the tile stops before LVGL draws, LVGL draws the old room
again, and the tile asks again from where its card is now (`live_stop_covered`).

**The network of a P4.** Every P4 board reaches its Wi-Fi through an ESP32-C6 over SDIO, where a packet's round trip
takes long enough that ESP-IDF's default TCP receive window (5,760 bytes) held a download at about 0.7 MB/s. The P4
boards build with a window of 64 KB (`components/smart_display/__init__.py`, keyed on the chip): about 2.6 MB/s, for the
live camera and for every picture. The other boards keep the default: the window holds for every connection, and a
board without PSRAM has no room for it.

## Live on an ESP32-S3

An ESP32-S3 board with PSRAM whose display is an RGB panel (`packages/hardware/esp32s3-rgb.yaml`, such as the Guition
4848S040) plays a camera tile live and a camera opened full screen live, over the same link and the same asks as a P4
(above): the app cannot tell the two apart, and the screen's hello says how many live tiles it takes (`live_tiles`). An
S3 with another kind of display (a SPI or QSPI panel, whose frame buffer a task cannot write) and every ESP32 board
keep the stills.

**What differs from a P4.** The S3 has no hardware JPEG decoder and no 2D engine, so its CPU does both
(`picture_engine_s3.cpp`): Espressif's software decoder (esp_new_jpeg) decodes each picture into the stream's buffer in
PSRAM, and a copy row by row puts it on the glass. That copy neither scales nor turns, so the app sends a tile's
pictures at the card's size and turned as the glass is (the hello's `picture_turn`), and a full view's to fit the glass;
a picture that would need scaling is refused, and the view keeps its stills. The decode runs on core 0, away from
LVGL's core 1. The screen runs:

- **One live tile at a time.** A second camera tile on the same page shows its stills. Each live tile costs about 11 KB
  of the chip's internal RAM for its connection's Wi-Fi and network buffers, and the RGB panel's S3 has little of it.
- **Six pictures a second on that tile** at most, as on a P4; while a finger drags, the governor halves it.
- **A full view of at most eight pictures a second.** The tile under it stops while the view is open and comes back
  when it closes.
- **One stream at a time, of any kind.** A live tile, a full view and a plugin's live place each count, and so does a
  stream that is still ending (`picture_engine::limits().streams`, checked in `live_view::open`). The view's stream
  opens once the tile's has ended and its task let go of its connection and memory (`live_view::ending`), never beside
  it, however long that takes: the view shows its stills meanwhile, and after 2 s the log says it waits. A view that
  opened beside a tile still ending took a tester's 4848S040 with seven pages down to 2 KB of internal RAM and an abort
  (2026-10-30). A tile asked while the view's stream still ends asks again in its turn instead of keeping its stills.
- **A stream opens only with internal RAM to spare.** Its connection takes about 11 KB, and 32 KB stays free whatever
  streams: below 43 KB free when it would open, the tile or view keeps its stills and the log says so ("too little for
  a stream's connection"). A P4 holds seven streams and its view may still open beside a tile after 2 s. The view is always the stream: only when it cannot open does it show stills, and the log says
  so ("the full view could not stream").

**Measured** on a Guition 4848S040 (dev, 2026-10-28, a WebRTC camera, a tile of 448 x 118, each setting for 150 s):

| | Pictures a second each | Decoding | Core 0 / core 1 | Internal RAM at its lowest |
|---|---|---|---|---|
| One tile, decoding on core 1 | 5.6 | 35 ms | 3 / 39 % | 49 to 53 KB |
| One tile, decoding on core 0 | 5.7 | 33 ms | 27 / 23 % | 49 to 53 KB |
| Two tiles, decoding on core 0 | 3.8 | 40 ms | 37 / 39 % | 16 KB |
| Three tiles, decoding on core 1 | 1.9 | 37 to 50 ms | 3 / 53 % | 3 KB |

The lows of one tile come from six boots with the tile and the full view in turn; the core does not change them. So
one tile, decoding on core 0. With a finger dragging over the tile for 90 s LVGL refreshed 435 times in 10 s with
the decoding on core 0 and 410 on core 1, and no loop was slow either way. A full view of 480 x 404 showed 5.3 pictures
a second, 37 ms decoding each (on core 1).

Opening the camera full screen, measured on a Guition 4848S040 (dev, 2026-10-29, a WebRTC camera, three times each;
the first picture from the moment it opened, internal RAM at its lowest from then until that picture, both in the
log's "live: first picture" line):

| | First picture | Internal RAM at its lowest |
|---|---|---|
| From the page with its live tile streaming | 370, 558 and 1264 ms | 46 to 48 KB |
| From a page without one (cold) | 289 to 306 ms | 50 to 52 KB |

The tile's stream ended about 100 ms after the view opened, before the view's link came, so the view took the same
place (stream 0) and never ran beside it. The 1264 ms came while the app answered slowly (the tile waited 360 to
540 ms a picture for it then). A second tile would need the Wi-Fi's and lwIP's buffers in PSRAM, which is not measured
yet (docs/PLATFORM_PLAN.md 4.1).

**What only an eye sees.** An RGB panel reads its picture out of PSRAM while it draws, and when a refill of its buffers
comes too late it starts the next frame shifted sideways for one frame, and tells nobody (ESP-IDF counts no underrun on
this panel, so the glass's `ran dry` stays 0 here). A live tile or a full view adds work on that same memory. Whoever
sees a frame jump sideways on an S3 while a camera plays, please say so through the app's report.

## Network

- **Home Assistant OS:** the app publishes port 8098 on the Home Assistant host. When another app
  already uses 8098, pick another port in the app's network settings: the app sends the screens
  links on the port you chose (app 0.4.24+). The screens need to reach Home Assistant's address on it.
- **Home Assistant on more than one network:** each screen gets the address Home Assistant has on the screen's own
  network, found from the screen's IP address and the networks Home Assistant lists. A screen on a network where Home
  Assistant has no address of its own (one reached through a router) gets the address of Home Assistant's default
  network, as every screen did before. It then needs a route to that address.
- **Docker** (docs/DOCKER.md): the container uses the host network, so 8098 is open as is. When
  the screens reach the host under another address, set `SCREEN_CAMERA_URL`, for example
  `http://192.168.1.20:8098`.
- The images travel unencrypted over the LAN, like the screens' other HTTP traffic. Links are
  random, short-lived, and only issued for a camera on that screen's tiles or in a recent alert.

## Memory and speed (Guition, measured 2026-09-17)

- Full screen: 480×270 RGB565 is 259 KB of PSRAM; the alert picture 172 KB (at most 392 x 300 = 235 KB decoded
  since firmware 0.2.103, never more than the screen's own full-screen picture). Both are freed when
  the camera or the alert closes. A new alert closes an open camera first.
- The internal heap stays level while a camera refreshes: 77.2 KB free after 91 images in six minutes,
  and PSRAM unchanged.
- Standby, **Back to page 1** and a new layout close the camera. In standby only the screensaver's picture loads, or
  the tiles' pictures while the dimmed tiles are seen (see the live pictures above).
- The first image (firmware 0.2.73, measured 2026-09-19 with an EZVIZ camera): the screen asks when
  the camera opens and loads the link as soon as it comes. About 2 s when the app still has the
  camera's last snapshot (it keeps one for 30 s after the last load), 4.5 s when it must ask Home
  Assistant first, of which 2.4 s is the camera's own snapshot. Firmware 0.2.72 took 3.4 s and
  5.8 s.
- Wi-Fi without power save (firmware 0.2.74 sets `power_save_mode: none` itself) makes the screen
  wait on its Wi-Fi less often while an image comes in: a loop held over 50 ms in one of eleven
  opens, against five of twelve with power save.

## One route for every picture

Every picture on a screen goes the same way (firmware 0.52.0, `components/smart_display/picture_loader.h`): the
camera full screen and the screensaver, an alert's picture, the media card's cover, a player's library, each tile's own
picture, and the cover of a media tile over a whole page (on the glass, and fetched ahead for a kept page). Each of them
only says, every quarter second, what it wants to see: a key that names the picture, the download slot it comes
through, how much it matters, and how the app is asked for it. One loader decides for all of them:

- **The store says what is there.** Whether a picture is had is read from the store every round, never from a flag an
  owner keeps, so a picture that left the store (to make room) is asked for again at once.
- **One download at a time, the most urgent first:** an alert, the full view and the screensaver, the media card, the
  library, the tiles on the glass, and last a picture fetched ahead for a page out of sight. Of equal ones, a picture
  not yet there goes before a refresh, then the oldest picture. Something on the glass breaks off a download for a page
  out of sight; a download nobody wants any more breaks off too. Pages turned fast, a card opened and closed before its
  picture came: nothing is left behind, and the page that stays loads first.
- **Asking is free, loading waits.** Asking the app is an event and goes at once; a download waits for the finger to
  leave the glass and the pages to stand still. A picture fetched ahead asks only once nothing on the glass waits.
- **One rule for cleaning up.** A picture its owner moved on from (another track, another focus on a map, someone on a
  map who moved) goes once nothing draws it, and so does the cover of a track its player no longer plays. What an
  owner still holds stays, so a page that comes back has its pictures at once; when the store is full, by bytes or by
  places, the picture used longest ago that nothing draws makes way (`picture_store.h`). The screen's log says what
  the store holds whenever that changes (`store: 5 pictures, 578 of 1638 KB (cover tile tile cover tile), 0 to go`).

## The screen's own camera as video in Home Assistant

The rest of this page is about pictures coming to a screen. This section goes the other way: a screen with a camera of
its own (the reTerminal D1001 and the M5Stack Tab5, the feature `camera_sensor`) as a live camera in Home Assistant,
with sound, playing in the browser and the app with about a third of a second of delay.

Measured and open: watched as a live tile on the screen itself, the video comes to the app at about 0.1 s behind the
camera on average but in bursts of 1.5 to 3 s behind now and then (a reTerminal D1001, 2026-10-25, camera_source's
"behind the camera" line), where another camera through Home Assistant stays within 0.3 s. Likely the wait for a key
frame or the encoder on the screen while it streams two tiles; not looked into yet.

**Which way up.** The camera turns its picture upright by itself (plugin API 0.19, `camera_turn.h`): half way round
on a board whose sensor sits upside down against the glass (the board file's `CAMERA_ORIENTATION: "180"`, the Tab5),
and half way again while the screen is turned half way round from lying down. The sensor turns its own readout
(Screen camera's `FrameHub::turn`, its flip and mirror), so the pictures, the video and the light level and motion all
stand the same way, at no cost. A screen stood up (a quarter turn) keeps the picture lying down, as the sensor sees the
room: a quarter turn of the picture is not built. For a screen mounted the other way round from how its board is built,
the plugin's setting **Camera upside down** turns it half way on top.

**Setting it up.** Add the plugin Screen camera to the screen; its part **Video** is on when it is added (the plugin's
details, on the screen's Plugins tab, turn it off). Then, once for the whole home, open **Settings, Video in Home
Assistant** in Tessera, press **Install in Home Assistant** and then **Restart Home Assistant**. From then on Tessera
adds a camera **Video** to the device of each screen with the video by itself, and takes it away again when the part is
turned off. Nobody types a password or an address.

**What travels.** The camera hands its frames to the ESP32-P4's hardware H.264 encoder at the camera's own size, at
15 frames a second, 1 Mbit/s, a key frame every second. The encoder wants whole macroblocks of 16 pixels, so a camera
whose size is not (the Guition screens' OV02C10 gives 1288 x 728) has the edge of its frames cut off on the way, by
the P4's pixel engine: the middle, 1280 x 720. The whole of a larger mode, scaled down in the same pass, was measured
and left out (a reTerminal D1001, 2026-10-25, a forced pass of its 1280 x 720 into 960 x 528 beside two live tiles and
three viewers): the panel never ran dry, but the pass took 77 to 89 ms a frame, the video fell from 12-13 to 7-9 fps,
and the live tiles from 12-14 to 6-9 pictures a second with laying out a picture going from 60 to 92-137 ms. The PPA
is one device that the video and the tiles share (PICTURE_ARCHITECTURE.md, section 2.4, has what its driver allows).
The Guition's whole field comes another way (Screen camera 0.6.5, its default since 2026-10-27): the OV02C10 reads its
whole array with each two columns averaged in the sensor, 960 x 1080 at 15 frames a second (with its lines binned
too, the sensor stopped after one frame), and Screen camera's frame hub halves the lines once on the PPA, 960 x 528
for every consumer, in whole macroblocks so the encoder cuts nothing. Measured on a Guition 10.1 (2026-10-27, two live
tiles and three viewers, 12 minutes against Sharp's 12): the panel never ran dry, the tiles kept 14.6 and 8.0 pictures
a second, laying out a live picture took 49 to 54 ms instead of 32 to 36, the video gave 10.3 fps instead of 12.3,
and the halving took 44 ms a frame on average, up to 0.74 s while it waited its turn on the PPA. Sharp, the middle at
1280 x 720, stays a setting away. The encoder keeps its reference frame in internal RAM and that grows
with the size, so the video takes no camera above 1280 x 800; a sensor whose modes are all larger gets a smaller one
in the part's YAML (`esp_video_camera: resolution`), never in a board file. The microphone goes as Opus, 16 kHz in one channel at 32 kbit/s. A small
RTSP server on the screen (port 8554, RTP over the RTSP connection) serves up to three viewers from the one encoder.
Home Assistant's integration `tessera_video` (shipped by the app, `screen_manager/app/ha_integration/tessera_video`)
gives Home Assistant that address as the camera's stream, and Home Assistant's go2rtc passes H.264 and Opus on to the
browser as WebRTC without transcoding. Stills come from the same stream. Both ends work the password out of the API key
Home Assistant already keeps for the screen (`sha256("tessera-video:" + key)`, its first 24 hexadecimal digits), user
`tessera`.

**What changes on the screen.** The camera runs from boot, in its raw mode. Its JPEG pictures are gone, and so is the
camera "Camera" of the screen's device: "Video" gives the stills now. Light level and motion of Screen camera keep
working: they read the same frames the video gets. The dot in the top right corner is solid while anyone watches and a
ring while the camera only senses (light level, motion; plugin API 0.20). While nobody watches, for sensing alone or
for nothing at all, the sensor makes 5 frames a second, and full speed again the moment someone opens the video or
Home Assistant asks for a picture (Screen camera 0.6.5, its `frame_rate.h`; what a sensor can, its driver tells the
camera through `camera_sensor.h`, on any board). Measured on 2026-10-27 on a Guition 10.1 (OV02C10) and a reTerminal
D1001 (SC202CS): 4.9 frames a second counted at 5, the light level kept coming every ten seconds; motion at 5 a
second was not tried yet, since nobody walked past. The microphone listens only while someone watches, and the voice
assistant can listen at the same time.

**What it takes, measured on a reTerminal D1001.** Each of these cost a build to find, and each is kept in the code:

- lwIP's TCP send buffer of 5760 bytes lets four segments travel at once, which over the ESP32-C6's Wi-Fi caps one
  connection near 1.5 Mbit/s and holds the sound up behind the picture for seconds. Every P4 gets 65534
  (`P4_NETWORK` in `components/smart_display/__init__.py`). Picture and sound still share that one connection: when
  the uplink stalls (four live tiles on the same screen, 2026-10-29) a picture waited in send() and the sound behind
  it, in bursts a second late at the app. Since Screen camera 0.6.10 a picture that finds the connection more than
  half full is left behind and the sound goes between the packets of a long one; since 0.6.12 and plugin API 0.23
  the screen keeps its live tiles at a quarter while anyone hears its microphone (the governor, PLATFORM_PLAN 4.10).
- Internal RAM is what a P4 runs short of. The encoder keeps about 104 KB of it and Opus about 25 KB, for as long as
  the screen runs. What every connection holds unsent or unread lived there too: with live camera tiles on the glass
  and the video playing, free internal RAM fell from 160 KB to 13 KB in two seconds and the C6's driver aborted the
  chip. So on every P4 the network's buffers go to PSRAM first (`CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP`, the option
  ESPHome's `wifi: use_psram` sets), and the video skips frames while less than 80 KB is free, starting again with a
  key frame above 110 KB.
- The encoder keeps its reference frame in internal RAM: a strip of three rows of macroblocks across the picture (92 KB
  at 1280 wide, esp_h264 1.3.8), most of the 104 KB. In PSRAM it would free that, and its DMA reaches PSRAM, but its
  traffic then shares the memory bus with the panel's frame buffer: on a reTerminal D1001 with two live camera tiles
  and three viewers of the video (2026-10-25), the panel ran dry 39 to 53 times within a minute (blue frames over the
  live tiles; 0 with the strip inside) and laying out a live picture went from 60 to 78 ms, for 100 KB more internal
  RAM free. So it stays inside: PSRAM is one bus with the panel (docs/PLATFORM_PLAN.md, 4.4a). With the encoder's DMA
  in bursts of 64 bytes instead of its 128 as well (a wrap of h264_dma_hal_init, the same day, eight minutes), the
  panel never ran dry and laying out stayed at 50 to 70 ms, but encoding took 105 to 130 ms a frame and the video fell
  to 6 to 7 fps: a smaller burst saves the panel and halves the video, so the strip stays inside and the test's wraps
  are gone. The video's line every minute gives the encoder's time a frame (48 to 50 ms there, at
  12 to 13 fps) and what it holds of internal RAM. It is made once, at the camera's first frame, on the camera's
  own task, with the camera started at boot. Made when someone starts watching, after the pages were built, there was
  no memory left for it. Made in `setup()`, before the camera driver ran, the first frame hung the whole chip.
- An encoder whose output did not fit stays stuck, so its output buffer holds 1 MB (a key frame of a dark room is over
  200 KB), it is never closed and opened again, and a viewer never chooses another size.
- The server's own buffers (a 64 KB send batch, a second of sound) live in PSRAM, and so does its task's 32 KB stack
  (Opus needs about 27 KB of it). With less than about 90 KB of internal RAM free the Wi-Fi starved and the chip
  stalled now and then.
- The microphone's chunks go to the server whole or not at all. A partial write of an odd number of bytes split every
  later 16-bit sample in two, which sounds like white noise. A chunk that does not fit is dropped whole, and its
  samples move the sound's clock on, so picture and sound stay in step.
- Opus counts at 48 kHz in RTP whatever it carries, and the SDP says `opus/48000/2`. Sender reports every second on both
  tracks, against the same clock the camera stamps its frames with, line picture and sound up in the browser.
- One viewer at a time was not enough: Home Assistant's own stream (for HLS and stills) opens a connection beside
  go2rtc's, and while it waited the frontend fell back to HLS, three seconds late and without sound.
- esp_audio_codec 2.5.0: from 2.6 on it builds only for P4 chips of revision 3.
- A JPEG-only build of Screen camera puts an empty esp_h264 in the build folder (its component
  `esp_h264_placeholder`), and ESPHome never takes a file it wrote away again: it wipes a build folder only when a
  component it had is gone. The video's build goes without that component, which covers a screen built with Screen
  camera 0.4.0 before. For one that ran an older Screen camera, the app starts a build whose plugin parts changed from
  an empty build folder (`Build.fresh` in `build_queue.py`); in Device Builder, use Clean Build Files once. When a build
  fails to compile, ESPHome's upload sends the previous firmware: after a flash, check that the screen runs the new
  build's compile time.

## For developers

- The layers under all of this, on the screen, in the app and in the Screen camera plugin, and where the code is still
  being moved into them: docs/PICTURE_ARCHITECTURE.md.
- The app's side is one picture system, docs/PICTURES.md: `picture_question.py` (the question and its answer),
  `picture_legacy.py` (an older screen's fields read as the same question), `picture_sources.py` (what each address
  is, fetched once per camera and checked against the layout), `picture_paint.py` (sizing, cutting, the shade and the
  corners), `picture_links.py` (the links and the port), `lan_address.py` (where the screens reach the app, the address
  the links carry) and `picture_service.py` (the question in, the link out);
  `Manager.answer_camera` in `server.py` hands a screen's question to it.
- `components/smart_display/camera_view.h`: when to ask for a link and when to load again
  (`tests/test_camera_view.cpp`).
- `components/smart_display/picture_loader.h`: the one route every picture goes (`tests/test_picture_loader.cpp`
  drives it through fast page turns, cards closed before their picture, priorities, pictures that left the store,
  refreshes, answers without a picture and failures).
- `components/smart_display/tile_picture.h`: a tile's own picture, its frame, its key, the question and how an answer
  finds its tile, and the parts of a plugin tile's picture (`tests/test_tile_picture.cpp`).
- `components/smart_display/runtime_tiles.h`: what each picture wants (`pictures_round` and the `*_want` functions
  beside it), the full-screen view, the alert picture, the tiles' pictures (`card_picture_wants`, `tile_ask`,
  `tile_picture_place`), the store (`picture_of`, `pictures_collect`) and the `camera` message.
- `components/smart_display/picture_jpeg.h`: the JPEG a screen takes, one profile with the app's `picture_paint`
  (`tests/test_picture_jpeg.cpp`, and `tests/test_camera.py` for the two sides).
- `components/smart_display/picture_fetch.h` and `picture_fetch.cpp`: the download beside the main loop, one task per
  picture, and the BMP decoder (`tests/test_picture_fetch.cpp` checks the link, the answer's head and the decoder).
- `packages/features/camera.yaml` (included by every board with camera pictures): the three pictures bound to their
  cards (the camera full screen and the cover, the alert's picture, the tiles' own pictures), the 50 ms hand-off of a
  finished download, the `LV_USE_IMAGE` flag, the alert frame, and the diagnostic action `preview_camera` (an entity
  opens it, an empty entity closes it).
- `tests/test_camera.py`: the app side and the words both sides share.
- `components/smart_display/picture_engine.h` and `picture_engine_p4.cpp`: the picture engine (docs/PICTURE_ARCHITECTURE.md):
  which formats this screen's decoder takes whole, the hardware JPEG decoder for the stills and the streams alike, and the
  PPA copy with its scale and turn, through the guard; the software engine is the BMP rows of `picture_fetch`.
- `components/smart_display/glass.h` and `glass_dsi.cpp`: the panel as a surface (docs/PICTURE_ARCHITECTURE.md): its
  size and turn, the frame buffer a stream writes past LVGL, the one-writer lock LVGL holds for a refresh and a stream's
  task for a copy, the rooms LVGL keeps out of, the panel's underrun count and the PPA bursts of every client.
- `screen_manager/app/camera_source.py`: a camera live on a P4, the source per camera (WebRTC or snapshots, its stills
  first, its sound) (`tests/test_camera_source.py`); `live_pictures.py`: the JPEG of a frame for a screen's room
  (`tests/test_live_pictures.py`); `live_stream.py`: the links, the stream and a tile's pace (`live_pace`)
  (`tests/test_live_stream.py`); `components/smart_display/live_view.h` and
  `live_view.cpp`: the screen's streams, up to seven at once (`tests/test_live_view.cpp` checks the stream's framing,
  where a picture lies on a turned panel, how it is scaled, cut into a card and what is laid over it);
  `live_spots.h`: the one machine of the live tiles and a plugin's live places (what streams, asks, stops and gives up;
  `tests/test_live_spots.cpp`), and the full view's handle and tries; `runtime_tiles.h` (`live_tiles_round`,
  `live_spot_ask`, `live_spot_open`, `live_stop_covered`, `live_tick`) binds it: which spots may stream, their question,
  their look.
- Every step of every picture is in the screen's log at DEBUG (`logger: level: DEBUG` in a screen's Override YAML),
  under the tag `picture`: who wants which picture, the question and its answer, the download, the store keeping,
  renewing, retiring and freeing each copy (and why), a picture put on its card on the glass or on a kept page, and an
  answer to an older question dropped. The `store:` line at INFO sums it up whenever it changes; "0 to go" means no
  copy waits to be freed.
