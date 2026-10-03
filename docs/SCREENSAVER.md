# The screensaver

A screen can show something when Auto standby dims it, instead of the dimmed tiles: the cover of the music that plays, a
camera, or a large clock with the date. Each screen has its own choice, and you put the three in the order the screen
tries them. It shows the first one that is there right now. It needs app 0.4.48 and firmware 0.29.0.

## Using it

1. In Tessera, open the screen and go to **Settings**. The **Screensaver** card stands under Brightness.
2. Turn on **Show in standby**. The screen also needs **Auto standby** on, since the screensaver takes the place of
   the dimmed tiles.
3. Choose a media player under **Music playing** and a camera under **Camera**. An `image` entity counts as a camera
   too, such as the last snapshot a doorbell keeps. Under the camera, you can optionally choose a binary sensor for
   movement detection. With one selected, the camera shows while the sensor is on and for one minute after it turns off.
   If the sensor is unavailable, the camera step is skipped. Without a sensor, the camera behaves as before.
4. Drag the rows into the order you want, and turn off a row you never want to see.

**More than one player** (app 0.4.54). Once a player is chosen, an empty row under it adds the next, up to four. The
screen shows the first of them that plays with a cover, in the order of the rows. A speaker that also plays the
television's sound is the usual case: put the speaker first and the television's player second. While the speaker
plays music you see its cover. While it plays the television's sound it has no cover, so you see the poster of what
the television plays. Set a row back to its first line to take that player out.

For example, with the order Music playing, Camera, Clock:

- music plays on that player and Home Assistant has a cover for it: the screen shows the cover with the title and the
  artist;
- nothing plays, or the player shows no cover (a radio station, a paused player): the screen shows the camera;
- the camera is unavailable: the screen shows the clock.

When a movement sensor is selected for the camera, the camera step is available only while that sensor detects movement
and for one minute after it clears. If the sensor is missing or unavailable, the next available step in the chosen order
is shown.

With every row off or unavailable, standby shows the dimmed tiles as it did before.

A tap wakes the screen, as it always did in standby, and that first touch never switches a lamp or opens a card
under the screensaver. The one exception is a player's keys.

**A player's keys** (app 0.4.55, firmware 0.33.0). Over a cover three round keys stand in the bottom right corner:
play or pause at the bottom, volume down over it and volume up at the top. A tap on one of them does what it says for
the player on the glass, and the screen stays in standby with its screensaver. A tap anywhere else wakes the screen.
A player without a volume in Home Assistant (many televisions) has the play key alone.

Hold volume down for a second and a half to mute the player. The key then shows a muted speaker. The next tap on either
volume key takes the mute off and changes nothing else, and after that the two keys are the volume again.

With the keys a paused player still counts, so the key that paused it can start it again. A player that plays always
goes first, whatever its row, with one exception: the player you paused on the screen keeps the screen for two minutes,
so its play key is still there. Ten minutes after the pause the screensaver moves on to the next step, the camera or the
clock, since a speaker stays paused in Home Assistant for days.

## What you see

- **Music playing**: the cover over the whole glass, with the title and the artist small at the bottom left. On a screen
  that is much wider or taller than square (the 7 and 10-inch boards) a cover cut to the glass would lose too much, so
  there it takes the full height at the left, or the full width at the top, and the rest is the cover's own colour with
  the words in it.
  A title too long for one line takes two, above the artist (firmware 0.30.0); one longer still ends in dots.
  When the next track plays, the last cover and its title stay until the new cover has loaded (firmware 0.32.0).
  The words end before the keys, so a long title takes its second line and then its dots in the room left of them.
- **Camera**: the camera over the whole glass, cut to it the way a photo fills a frame, with its name small at the
  bottom left, refreshed every 15 seconds.
- **Clock**: the time in the bedside clock's digits and the date under it, white on black whatever the look, so the
  glass gives as little light as it can (firmware 0.31.0; before, it stood in the screen's own colours). On 12 hours AM
  or PM stands after the time. Small in the middle at the bottom is the outside temperature: Home Assistant's forecast
  for its home (Met.no's, else its first weather entity) unless you choose one under the clock in the editor (or none), whole degrees in the unit Home
  Assistant is set to (app 0.4.52).

The cover and the camera are a little darker everywhere, so the words always read. A camera has nothing else on it,
and a cover only its three keys: no bar, no spinner.

The screensaver shows at **Standby brightness**, the level standby always dimmed to, and during the night hours at
the night brightness. Raise Standby brightness for a cover that reads from across the room. With a level of 0 the
screen goes dark and shows no screensaver. Sleep pressed in Home Assistant keeps the screen at its standby level
without a screensaver.

The CYD, the Waveshare 3.5-inch and the Hosyond 4-inch have no memory for pictures (see [CAMERA.md](CAMERA.md)). On
them the card offers the clock alone. The Waveshare 4.3 and 7-inch never go into standby, so they have no
screensaver either.

## How it works

Tessera Screen Manager decides what the screensaver shows and makes its picture; the screen shows it with what it already
has.

- **The choice** is kept per Home Assistant device in `screensavers.json`, next to the layouts
  (`screen_manager/app/screen_saver.py`). The layouts' own storage does not change, so an older add-on still reads
  every layout. `PUT api/screens/<inbox>/screensaver` stores the whole choice, and the screen's entry in the editor's
  inventory carries it as `screensaver`, with `ready` (the firmware takes one), `pictures` (the board draws pictures)
  and `standby` (the board goes into standby at all).
- **The pick.** The app follows the chosen players, camera and optional movement sensor like a tile's entities
  (`watched_entities`). After every pass of a screen it works out the first step that is on and available
  (`screen_saver.pick`): the first player of the
  list (`media`, then `more`, `screen_saver.player`) whose state is `playing` with an `entity_picture`, a camera whose state is not `unavailable` or `unknown`, the clock always. A
  board without pictures has only the clock.
- **On the wire** the answer is one message in the screen's session, sent when it changes and once in every new
  session: `{"op": "saver", "k": "media" | "camera" | "clock" | ""}`. A player adds its entity (`e`), its name
  (`n`), the title (`t`) and `x`: the artist, the album, the picture's mark and the cover's colour, the things its
  picture and words are made from. Where the track is goes along with none of it, so a player that reports its
  position sends nothing new. With several players the message names the one that shows, so the screen needs nothing
  new for the list. A screen whose hello also lists `saver_keys` (firmware 0.33.0) gets two more fields with a
  player: `s`, its state (`playing` or `paused`), `f`, Home Assistant's `supported_features`, and `m: 1` while it is muted. For such a screen a
  player paused less than `PAUSED_SECONDS` ago counts after every player that plays.
- **The keys** (`saver_keys_draw`, `saver_key_event` in `runtime_tiles.h`) are the only clickable objects of the
  screensaver, so their tap never reaches the dim overlay and the screen stays in standby. A tap goes through the touch
  guard like every key and sends `media_player.media_play_pause`, `volume_up` or `volume_down` for the player on the
  glass. Volume down held for `SAVER_MUTE_HOLD_MS` sends `volume_mute` where `f` has VOLUME_MUTE, and a tap on a
  volume key of a muted player sends the unmute instead of a step. The play key and the mute show their other face
  at once and Home Assistant's word follows. Where they stand is
  `saver_view::keys`: the play key needs PLAY or PAUSE in `f`, the volume keys VOLUME_SET or VOLUME_STEP. A camera adds `e` and `n`. The screen says it takes the message
  with `screensaver` in the feature list of its hello; a screen without it never gets one.
- **On the screen** (`runtime_tiles.h`, "The screensaver") the last word is kept until the screen goes into standby.
  Then `apply_screen_settings` sets the standby level as before and `saver_sync` draws it, when that level is above 0,
  on LVGL's top layer, under an alert, with no clickable object: the touch falls through to the dim overlay, which
  wakes the screen, and `wake_tap` leaves the tile under it alone. A new word in standby redraws at once.
- **The picture.** A cover and a camera both open the camera's full view without its keys, its name and its spinner.
  Its request carries `saver` (`media` or `camera`), and the app answers with `t: "saver"` and a link to one picture of
  the screen's whole full box (`camera_feed.encode_saver`): the camera or the cover cut to the glass, or on long glass
  the cover beside its colour (`saver_shape`, five to four either way), all darkened by `SAVER_DIM`, in 8-bit on the
  picture's own palette as live pictures go. A picture under the size cap (the 10-inch's 1280 x 800 comes as
  1024 x 640) is scaled to the glass on the screen. A camera loads every 15 seconds (`SAVER_CAMERA_MS`), a cover once
  per track. The app lets the screen load the chosen camera and player although no tile shows them
  (`camera_allowed`).
- **The words** stand where `saver_view.h` puts them, by the same five-to-four rule, pure arithmetic that
  `tests/test_saver_view.cpp` checks on every glass. `tests/test_screen_saver.py` covers the choice, the pick, the
  message, the picture and the delivery.
