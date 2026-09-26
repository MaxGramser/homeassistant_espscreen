# Camera images on a screen

App 0.2.66 with firmware 0.2.57 shows camera images on every board with the memory for them: the
4-inch Guition, the 4.3-inch and 7-inch Waveshare and the 10.1-inch Guition. The CYD is the one
that cannot (see below). The numbers further down were measured on the 4-inch Guition.

- **A camera tile.** Add a `camera.*` or `image.*` entity as a tile. A tap opens the image full
  screen, with the round back key at the top left like every card, and a spinner until the first
  image is there (firmware 0.2.73). The image is refreshed every four seconds while it is open. It
  is not video: ESPHome has no video decoder.
- **An alert with a picture.** Add `camera: camera.front_door` to the `esp_screens_show_alert`
  event, and `screen: hallway-screen` for one screen only (app 0.2.133). The card shows the picture of that moment (it stays that picture), with the card's round
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
free block is about 45 KB). It shows the alert without the picture, and the editor doesn't offer
camera tiles for it.

## The album cover on the media card

App 0.2.77 with firmware 0.2.64 uses the same road for a media player's picture. The media card
(a tap on a media player's tile, or a media tile of size *Full page*) shows the album cover of
what plays, with the title, the artist and the album, a progress bar and the keys under it.

- The screen asks ESP Screen Manager for the cover with the size it draws it at and the colour
  behind it (the event `esphome.screen_camera` with `size` and `bg`). The app fetches the
  picture where Home Assistant's state points (`entity_picture`), cuts it square, sizes it,
  rounds the corners over that colour and serves it on port 8098 as a BMP, like a camera image.
- A cover is fetched once per picture: the state carries a short mark of the picture, and the
  screen asks again only when the mark changes (a new track), when the card opens again or
  when the page turns back to a full-page media tile. Nothing polls.
- A player without a picture (a radio station, a player that is off) keeps the player's icon in
  the cover's place; the app answers with an empty link and the screen stops asking.
- The CYD shows the same card without the picture: its icon stands in for the cover.
- One picture loads at a time. An alert closes an open card and its cover. Under a media tile of
  size *Full page* the alert's picture goes first: the tile's cover waits until the alert's picture
  is there, and a cover already on its way finishes before the alert's picture starts.

## A live picture on a camera tile

App 0.2.91 with firmware 0.2.77 puts the camera on the tile itself: **Display → Live picture** in the
tile's settings, with a pace of 15 or 30 seconds (`refresh`). The tile shows a small square of the
camera's view in the icon's place, the middle of the snapshot cut square with the tile's rounded
corners, and refreshes it while that page is on the screen. A tap still opens the camera full screen.

- **One download per page.** The screen asks ESP Screen Manager for all the live tiles of the page at
  once (the event `esphome.screen_camera` with `tiles`, the entities in slot order, `size`, the side of
  the icon's circle, and `bg`, the colour of each tile behind the corners). The app answers with one
  BMP: a strip of squares, top to bottom in that order, and every tile draws its own square out of it
  (LVGL's image offset). Six live tiles cost the screen one download of about 50 KB; a tile over the
  whole page gets one square of 128 px.
- **At the pace of the fastest tile.** The page loads its strip every 15 s when any of its tiles says
  15 s. The app fetches a camera again only when that camera's own pace has passed, so a 30 s camera
  on a 15 s page is fetched every other load. The strip comes whole every time, never as a 304:
  ESPHome's `http_request` logs a 304 as a failed request and raises its error flag, which a page of
  slow cameras would do every 15 s. Nobody loading means nothing fetched, as with the camera full
  screen.
- **After the other pictures.** The strip waits for the alert's picture, a cover on its way and the
  camera full screen (one picture loads at a time), and does not load under an open card, in standby
  or under a finger. A page turn, dark mode (other colours behind the corners) or a changed tile drops
  the strip and asks for a new one.
- **A camera without a picture** keeps its icon: the app names it with an empty entry in its answer
  and paints a plain square of the tile's colour in the strip.
- **A media tile's album cover** (app 0.2.92, firmware 0.2.78) rides in the same strip: **Display →
  Album cover** on a single or double-width media player tile. The app fetches the player's picture
  only when its address changes (a new track), so a page with a camera and a Sonos loads its strip at
  the camera's pace with the cover reused, and a page of media tiles alone loads once. The screen asks
  for the page again the moment a player's picture mark in its state changes. A player without a
  picture keeps its icon; the tile over the whole page keeps the card's big cover.
- The strip lives in a third `online_image` of the Guition profile (`tile_image`, PSRAM); the CYD has
  none and the editor does not offer the live picture there.

### A camera that fills a taller tile

From app 0.3.8 with firmware 0.3.3, a live camera on a 1 × 2 or 2 × 2 tile fills the whole card instead
of the icon's place. Two settings appear in the tile's settings once the tile is taller:

- **Picture**: **Fill the tile** (`fit` left out, the default) cuts the picture to the card, the way a
  photo fills a frame. **Whole picture** (`fit: contain`) shows all of it, with black above and below
  or at the sides.
- **On the picture**: **Name** (`overlay` left out, the default) writes the tile's name at the bottom
  in white. **Nothing** (`overlay: none`) leaves the picture alone.

The screen does none of this work. On a page with a picture that fills its card, the screen asks for
the page's pictures as frames (`atlas`: the place, size and corner of each), and the app answers with
one BMP in which every picture already has its card's exact size in pixels, its crop or its black bars,
its rounded corners and, under the name, a soft shade that keeps white text readable on a bright
picture. The screen draws that image as it is. A smaller picture does not load faster: the picture
already has exactly as many pixels as the card shows. What sets the pace is the 15 or 30 seconds of the
tile and the time the camera takes to answer.

A screen with firmware 0.3.3 or newer gets its live pictures in 8-bit colour: a palette of the picture's own
256 colours, dithered so a shade stays smooth. That is a third of the bytes of a 24-bit BMP (a 2 × 2 card
on the 4-inch Guition: about 100 KB instead of 300 KB), at about the quality of the screen's own 16-bit
colour. ESPHome decodes a BMP while it downloads, in the screen's main loop, so fewer bytes means a picture
that arrives sooner and a screen that answers a touch sooner. Preparing the palette costs Home Assistant a
few milliseconds per picture, also on a Raspberry Pi. Older firmware keeps 24-bit pictures.

The camera's state ("Idle") is not written on the picture. Until the first picture arrives, the tile
shows its icon and name as any tile does. Older firmware ignores both settings and keeps the small
picture in the icon's place.

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

1. The screen asks ESP Screen Manager for a camera (the event `esphome.screen_camera`), or the app
   sends the picture of an alert by itself.
2. The app fetches the snapshot from Home Assistant with its own access (the same pictures the
   Home Assistant frontend shows), and makes it exactly as large as the screen draws it: at most
   480×480 full screen, 392×220 on an alert card, proportions kept.
3. It serves the result as an uncompressed 24-bit BMP on **port 8098** under a random link, and
   sends the link to the screen. ESPHome's `online_image` loads it.

While a camera is open, the screen loads its link every four seconds, one image at a time. The app
serves the last snapshot at once and starts fetching the next one, so each load gets a picture one
load younger: the picture changes at the screen's steady pace. (A fetch on its own clock next to the
screen's made the picture change after 1.5 s one time and 6 s the next.) A slow camera makes the
images older, never the screen slower, and nothing queues up. Nobody loading means nothing fetched.
A link that nobody loads for two minutes stops working; an alert's picture stays for half an hour.

**Why BMP.** ESPHome decodes a BMP piece by piece while it downloads (16 KB per round of its main
loop since firmware 0.2.73, 4 KB before). A JPEG of the full screen took 0.6 s in one piece on the
Guition, during which the screen missed taps. A full-screen BMP is about 390 KB; on the bench
Guition it comes in about 1.8 s (2.8 s with 4 KB).

## Network

- **Home Assistant OS:** the app publishes port 8098 on the Home Assistant host. Keep it at 8098 in
  the app's network settings; the screens need to reach Home Assistant's address on that port.
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
- Standby, **Back to page 1** and a new layout close the camera; nothing loads in standby.
- The first image (firmware 0.2.73, measured 2026-09-19 with an EZVIZ camera): the screen asks when
  the camera opens and loads the link as soon as it comes. About 2 s when the app still has the
  camera's last snapshot (it keeps one for 30 s after the last load), 4.5 s when it must ask Home
  Assistant first, of which 2.4 s is the camera's own snapshot. Firmware 0.2.72 took 3.4 s and
  5.8 s. Details in docs/TEST_RESULTS_0287.md.
- Wi-Fi without power save (firmware 0.2.74 sets `power_save_mode: none` itself) makes the screen
  wait on its Wi-Fi less often while an image comes in: a loop held over 50 ms in one of eleven
  opens, against five of twelve with power save.

## For developers

- `screen_manager/app/camera_feed.py`: fetching, sizing, links and the port; `encode_live` and `CameraFeed.live`
  make the strip for a page's live tiles (`Manager.answer_live` in `server.py` checks the tiles against the layout).
- `components/smart_display/camera_view.h`: when to ask for a link and when to load again
  (`tests/test_camera_view.cpp`).
- `components/smart_display/runtime_tiles.h`: the full-screen view, the alert picture, the live tiles
  (`live_tick`, `live_place`) and the `camera` message.
- `packages/boards/guition-4848s040.yaml`: the three `online_image` components (the camera full screen and the
  cover, the alert's picture, the live tiles' strip), the alert frame, and the diagnostic action `preview_camera`
  (an entity opens it, an empty entity closes it).
- `tests/test_camera.py`: the app side and the words both sides share.
