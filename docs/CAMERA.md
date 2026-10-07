# Camera images on a screen

App 0.2.66 with firmware 0.2.57 shows camera images on every board with the memory (PSRAM) for them:
the 4-inch, 7-inch (JC1060P470 and V2) and 10.1-inch Guition, and the 4B, 4.3-inch and 7-inch Waveshare.
The CYD, the Waveshare 3.5-inch and the Hosyond 4-inch cannot (see below). Which boards can is
`camera` in `screen_manager/app/boards.json`, worked out from whether the board file includes
`packages/features/camera.yaml`. The numbers further down were measured on the 4-inch Guition.

- **A camera tile.** Add a `camera.*` or `image.*` entity as a tile. A tap opens the image full
  screen, with the round back key at the top left like every card, and a spinner until the first
  image is there (firmware 0.2.73). The image is refreshed every four seconds while it is open. It
  is not video: ESPHome has no video decoder.
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
(`camera_feed.picture_cap`); an older app keeps the common cap. A picture that is still smaller than its place sits in
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
   (`camera_feed.PICTURE_MAX_SIDE` and `PICTURE_MAX_BYTES`): the JC8012P4A1's 1280×800 canvas gets a
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
time and half a second (`camera_feed.CameraFeed.ahead`), so the next load finds a snapshot a fraction of a second old
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

## Network

- **Home Assistant OS:** the app publishes port 8098 on the Home Assistant host. When another app
  already uses 8098, pick another port in the app's network settings: the app sends the screens
  links on the port you chose (app 0.4.24+). The screens need to reach Home Assistant's address on it.
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

## For developers

- `screen_manager/app/camera_feed.py`: fetching, sizing, links and the port; `CameraFeed.live` makes a tile's picture
  (with `tile_art.encode`) and an older screen's strip (`encode_live`); `Manager.answer_live` in `server.py` checks the
  tiles against the layout.
- `components/smart_display/camera_view.h`: when to ask for a link and when to load again
  (`tests/test_camera_view.cpp`).
- `components/smart_display/picture_loader.h`: the one route every picture goes (`tests/test_picture_loader.cpp`
  drives it through fast page turns, cards closed before their picture, priorities, pictures that left the store,
  refreshes, answers without a picture and failures).
- `components/smart_display/tile_picture.h`: a tile's own picture, its frame, its key, the question and how an answer
  finds its tile (`tests/test_tile_picture.cpp`).
- `components/smart_display/runtime_tiles.h`: what each picture wants (`pictures_round` and the `*_want` functions
  beside it), the full-screen view, the alert picture, the tiles' pictures (`card_picture_wants`, `tile_ask`,
  `tile_picture_place`), the store (`picture_of`, `pictures_collect`) and the `camera` message.
- `components/smart_display/picture_fetch.h` and `picture_fetch.cpp`: the download beside the main loop, one task per
  picture, and the BMP decoder (`tests/test_picture_fetch.cpp` checks the link, the answer's head and the decoder).
- `packages/features/camera.yaml` (included by every board with camera pictures): the three pictures bound to their
  cards (the camera full screen and the cover, the alert's picture, the tiles' own pictures), the 50 ms hand-off of a
  finished download, the `LV_USE_IMAGE` flag, the alert frame, and the diagnostic action `preview_camera` (an entity
  opens it, an empty entity closes it).
- `tests/test_camera.py`: the app side and the words both sides share.
- Every step of every picture is in the screen's log at DEBUG (`logger: level: DEBUG` in a screen's Override YAML),
  under the tag `picture`: who wants which picture, the question and its answer, the download, the store keeping,
  renewing, retiring and freeing each copy (and why), a picture put on its card on the glass or on a kept page, and an
  answer to an older question dropped. The `store:` line at INFO sums it up whenever it changes; "0 to go" means no
  copy waits to be freed.
