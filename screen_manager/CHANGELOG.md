## Unreleased

- **Tessera is looking for funding.** The home overview asks for it, before the support card, with a button that mails Max: a day job comes first, and Tessera needs funding to stay alive. "Not now" puts it away for a week.

## 0.4.93 (firmware 0.59.0)

- **A camera opens full screen at once again from its live tile.** Since 0.4.91 a tap on a live tile took about 11 seconds to show the camera full screen: its first try went out without an address while the tile's own stream was still ending, and the second came 10 seconds later.
- **An ESP32-S3 screen no longer restarts when a camera opens full screen next to a live tile.** The S3 holds one live stream at a time, and the full view could open beside a live tile that had not stopped yet, which ran the screen out of memory. The view now waits for the tile, and no stream opens when the screen's memory is already too tight for one; it shows its pictures instead.

## 0.4.92 (firmware 0.58.0)

- **The editor saves again on a screen with a light preset that has an effect or the light's own settings.** Since 0.4.91 every save of such a screen, also a delete, was refused with "Tile options need normalization": the app keeps a preset's keys in another order than the editor writes them, and the editor took the two for different presets (a WLED with an effect preset, on a reTerminal D1001 and a Guition 10.1, 2026-10-30). The editor now compares presets whatever the order of their keys, and the app keeps them in the editor's order. Beyond that bug: when a tile's options no longer fit what its tile allows, the editor takes out what does not fit and says so, naming the page and the tile ("Page 2, tile “Lamp”: took out what did not fit (refresh)"), instead of refusing the whole save; a tile it cannot put right goes off the page with such a note. A tile you did not touch never blocks a save or a delete, and a refusal names the page and the tile it is about.

## 0.4.91 (firmware 0.58.0)

- **The 4 MB boards (the CYDs and the Hosyond 4.0) build with ESPHome 2026.9.0 or newer.** That is the ESPHome the add-on ships, so a screen updated from the app notices nothing. Whoever builds these screens elsewhere with an older ESPHome Device Builder updates it first: on 2026.6.2 the same firmware is 65 KB larger and no longer fits the 97 % of the update slot the flash budget allows (docs/RELEASING.md).

- **A camera opened full screen after its tile no longer plays its sound twice.** When a live tile of a camera was on the page and the camera was then opened full screen with sound, the app kept a session for the sound beside the new one that carried pictures and sound together, and every listener got the sound twice, shifted: small snippets out of joint, words doubled or in slow motion (a Guition 10.1 showing a reTerminal D1001, 2026-10-29). The extra session ends when the pictures bring the sound along, and comes back when they stop.

- **A camera's sound on a P4 screen no longer breaks into snippets.** The sound of a live camera opened full screen could sound chopped into small pieces out of joint, from a screen's own camera and from any other camera alike (both ways between a reTerminal D1001 and a Guition 10.1, and an EZVIZ, 2026-10-29). The screen kept only 150 to 400 ms of sound in hand, and on its way through Home Assistant a piece could wait up to 635 ms behind a picture: what came late was cut and what came in a gap played at once. The screen now keeps 400 to 1200 ms, and after a gap it waits for 400 ms of sound before it speaks again, as it does at the start. The sound comes a quarter of a second later than before; the stream's log line counts the gaps.

- **A screen's own camera keeps its whole picture while someone hears its microphone.** When another screen shows this screen's camera full screen with sound, that outgoing video is the conversation: a finger on this screen's glass or a busy moment no longer halves or quarters its frames for the other side (the governor kept the screen's own camera behind the live tiles). Seen on a Guition 10.1 watching a reTerminal D1001: every tap on the D1001 and every slow loop there thinned the picture on the 10.1. The live tiles of the sending screen still give way, as before.

- **The reTerminal D1001 no longer shows a whole frame of blue now and then, we think.** On a page with four or five live camera tiles the glass could go light blue for one frame, once or twice a minute, more with the screen's own camera streamed to another screen. The panel refreshes at 58.9 Hz now instead of 68.6: the DSI bridge reads an eighth less from the memory it shares with the live pictures, the camera and the video encoder, and in a quarter of an hour of looking on 2026-10-29 the blue did not come back. The screen's own count of dry frames (Panel watch) was 0 both before and after, so this is a memory bus under load, not a panel that ran dry. Testers with a D1001: a page of live tiles for a while, and tell us whether you still see it.

- **A build server empties its build folder for a screen whose plugin part changed.** When a part of a plugin is added or removed (Screen camera's Video), the app already started that screen's next build from an empty build folder here; a build on a build server kept the server's folder, and a component the earlier build left behind (the empty esp_h264 of a Screen camera without video) shadowed the real one: "esp_h264_enc_single_hw.h: No such file or directory". The server now runs its clean for that screen first. Seen on a reTerminal D1001 going from Screen camera 0.2.0 to 0.6.13 with Video on a Mac mini build server, 2026-10-29.

- **A screen's log says why the chip started.** The first line after boot names the reset: power on, a software reset, a watchdog, or a brown-out of the supply. A troubleshooting report reads it, so a screen that restarted because its power dipped (a Tab5 as its charger was plugged in) says so instead of "no crash record".

- **Plugin API 0.24 keeps one way for each thing (for plugin makers).** Removed, as each had a newer form beside it: `Plugin::on_touch` (use `on_press`), `tessera::action(service, entity, key, value)` (use `tessera::action(service, entity, fields)` with a JSON object, or no fields), the picture address `saver:picture` (use `step:`) and a tile's `memory: { bytes: n }` (write the number). A plugin that still uses one of them no longer builds; of the plugins in the plugin list one did, and its maker is told.

- **A screen whose camera is watched with sound slows its own live tiles.** While someone hears a screen's microphone (its video open with sound on another screen, in Home Assistant, or a call later on), its live camera tiles run at a quarter of their pictures a second. Four live tiles on the same screen crowded its Wi-Fi so much that its sound reached the viewer in bursts a second late and the viewing screen cut most of it away: words gone, bits doubled. Needs Screen camera 0.6.12. This needs two or more live tiles on the page: one tile crowds nothing and runs as always.

- **A live camera tile shows its name the way its card does.** Over the live picture the name stands at the bottom of the card in light letters, also when the tile had no still picture before its stream began; it stood dark and halfway up before.

- **"Reinstall from dev" on a build server builds dev again.** A screen whose YAML follows the dev branch took the build server's last firmware when its YAML had not changed, although dev had: the server fetches the branch itself. Such a build is now taken again only within the update it was made for.

- **An ESP32-P4 screen now counts every blue flash.** When the panel of a P4 screen cannot fetch its next pixels in time it shows a frame of blue, over the whole glass or its lower part. The screen counted only the second kind: the chip's flag for it is masked for the first 800 lines of a frame, so the whole-glass flash some testers see while dragging a slider or while a camera plays was never counted and read as "none". The mask is now off, and the count stands in Home Assistant as the diagnostic sensor "Panel misses" on every P4 screen, so a flash you see and the number you read agree, and a graph of it beside what the screen was doing says what brings them on. A second diagnostic sensor, "Panel watch", says each minute in one line how many flashes there were and what the screen was doing as each began, so nobody has to sit and watch the glass for them.

- **A live camera tile shows when it slows down.** When a screen is busy (a finger on the glass, the wake word falling behind) it shows its live camera tiles at half or a quarter of their pictures a second. Each such tile now shows a small slow-speed icon in its top right corner while that lasts, so a slower picture is no mystery.

- **A doorbell's picture comes sooner.** When someone rings, the app now prepares the camera's live picture for each screen at once and sends it along with the ring, so the screen no longer has to ask for it first: the picture is on the glass in about half a second.

- **Choose how long a missed ring stays in the top bar.** The doorbell wizard asks how long a ring nobody answered stays in the top bar of your screens: 10 or 30 minutes, an hour, four hours, or until someone opens it. A new doorbell automation keeps it for 30 minutes; your existing automations keep their missed rings until they are opened, as before. In your own automation the field is `keep_minutes`. The screen takes the ring away by itself when the time is up, also while it was in standby.

- **The editor says how many live streams are in use.** The app plays at most eight cameras live at once, of all your screens together. A live camera card in the editor now says how many of the eight are in use, so a ninth camera that shows a picture every 15 seconds instead is no mystery, and the app's log names each camera it had to refuse, with its screen. A screen that plays one camera live at a time (the ESP32-S3 screens) says so in plain words.
- **A camera that was on its snapshots goes live again by itself.** A camera whose live video did not start (in privacy mode, or while Home Assistant's go2rtc was away) sent its snapshots until the screen closed it. It now tries the live video again every minute while it is watched, and plays live as soon as that works.

- **A live camera on the ESP32-S3 screens with an RGB panel.** A Guition 4848S040 and the other S3 screens whose display is an RGB panel now play one camera tile live, up to six pictures a second, and a camera opened full screen live, up to eight a second, as the ESP32-P4 screens do. A second camera tile on the same page keeps its picture every few seconds: each live tile needs memory inside the chip that these screens have little of. Testers, one thing to watch: when the panel cannot fetch its picture in time it can show one frame shifted sideways, and the screen cannot notice that itself. If you see the picture jump sideways while a camera plays, please tell us through the app's report on that screen.

- **Photos and camera pictures reach the ESP32-S3 screens as JPEG.** A Guition 4848S040, the Waveshare and Sunton 7-inch boards and every other S3 screen with PSRAM now decode JPEG themselves, so a camera's still, an album cover or a photo comes in about a tenth of the bytes it took as a BMP and shows sooner on a busy Wi-Fi. A camera picture of 480 x 270 is decoded in under 50 ms. Maps and drawn pictures still come as BMP, which keeps their lines sharp. Screens without PSRAM, such as the CYD, are unchanged.

- **Live camera pictures no longer turn on a screen whose glass is turned.** On the M5Stack Tab5, the reTerminal D1001 and the Guition 10.1 the panel is made standing up and shown on its side, and every live picture was turned by the screen's picture engine on its way to the glass, the kind of copy that now and then never finished on a Tab5 and restarted it. The app now sends such a screen its live pictures already turned (its tiles, a plugin's live place and a camera full screen), and the screen copies them onto the glass as they are. Should the app fail to turn one, it sends it upright and the screen turns it as before, so a picture is never missing. A tile's corners, shade and name are worked out once when it starts instead of for every picture. Only a tile of the screen's own camera is still turned on the screen.

- **An ESP32-P4 screen no longer restarts on a sound live picture.** The watch that restarts a screen when the picture engine never finishes a copy (a stall seen on the M5Stack Tab5) could misjudge a copy that was asked a few milliseconds after it looked at the clock, and restart a screen that was fine; a Tab5 restarted that way after an hour of live tiles (TR-NQRE3E). It now takes the copy's age as it is.
- **A plugin's README can open with a notice.** A quote at the top of a plugin's README shows as a box in the warning's colour in the plugin's details, before anything else. The Bluetooth proxy says there what it costs: the screen answers more slowly, its Wi-Fi gets weaker, and camera streams and video can stutter.
- **ESP32-P4 screens run their firmware faster.** The firmware is now built for speed instead of size on every ESP32-P4 board: on a Guition 10.1 with four live camera tiles the second processor core works 52 % instead of 63 %, and each live picture is laid out in 26.5 ms instead of 32. The firmware is 889 KB larger, which every P4 screen has room for. Measured on the Guition 10.1; the reTerminal D1001 and the M5Stack Tab5 get it too, the Tab5 not yet tried.

- **Live camera tiles show what happens now, and more smoothly.** On the ESP32-P4 screens a live tile could show pictures a second or two old, and seconds old while the screen was busy: the pictures queued on their way from the app to the screen, and a tile read them one by one. A tile now asks the app for each picture when it wants one, and the app answers with the camera's newest: nothing waits on the way, and a tile receives only what it shows, a third to a half of the bytes it took before. It also lays each picture out with half the work (the picture goes onto the glass once instead of twice), so four tiles no longer wait for each other: on a reTerminal D1001 a tile shows up to six pictures a second where it managed five or six with a second's delay, its pictures a few milliseconds on their way instead of about a second, and its processor works less than before. Six a second is the limit for a live tile on every board, so four of them leave the voice assistant its share. The app now stamps every live picture with the moment it left, and the screen's log says how long its pictures waited on the way.

- **The voice assistant hears its wake word beside live camera tiles.** On a reTerminal D1001 with four live camera tiles the wake word fell behind hundreds of times an hour, so the voice assistant missed being called now and then: the tiles' work ran ahead of it. The tiles now work below the voice assistant and only take their turn on the picture engine ahead of it: none fell behind in ten minutes at rest or in three minutes of dragging over the tiles.

- **A screen's own camera on a tile of its own comes straight from the camera.** A live camera tile that shows the screen's own camera (a screen with a camera, Screen camera 0.6.8 and Video in Home Assistant) used to take the long way round, through the screen's video, Home Assistant and the app, and back to the same screen. The screen now draws it from its camera itself: the picture is as new as the camera's, no bytes go over Wi-Fi for it, and the screen's video encoder rests while nobody watches the video in Home Assistant: on a reTerminal D1001 its processor cores worked 27 and 43 % instead of 49 and 67.

- **A camera opened full screen keeps its picture with its sound.** When pictures pile up on their way after a hiccup, the full view now passes the old ones for the newest and lets the sound play on, so the picture never trails the sound by more than a frame.

- **A busy screen gives way where you will not notice it.** While a finger drags a slider or swipes a page, or when a screen shows signs of strain (the picture ran dry for a moment, the screen held up, the voice assistant's wake word fell behind), it first gives up what nobody looks at: pictures fetched ahead for other pages, the light level and motion of its own camera, then that camera's video, and only then the live camera tiles, which show half as many pictures a second for a moment. When the voice assistant's wake word falls behind, the tiles give way at once. The glass, the voice assistant and the doorbell never give way. It comes back by itself within seconds. A new diagnostic sensor, **Pressure**, says in Home Assistant what a screen gives up right now ("normal" most of the time).

- **The doorbell can open the door.** A doorbell automation can name a lock, or another action such as a script or a gate's button, and a screen that shows the ring live then has a **Door** key beside the picture. As on a lock's tile, one tap never opens it: the first turns it orange and says "Tap again to open", and a second tap within five seconds opens the door through Home Assistant. With a lock the key shows whether it is locked or open, and follows it while the ring shows. A lock that asks for a code needs a default code in Home Assistant, since the ring's view has no keypad. The doorbell wizard has a new step for it, **A door to open?**. Beside it, a grey **Talk** key says "Coming soon": talking back to the doorbell comes once Home Assistant's two-way audio for cameras is there. The wizard can also make a ring open quiet, for a studio or another place that must stay silent: the doorbell's sound then waits for a tap on **Sound**. And it can leave the chime out, for whoever would rather not hear the ding-dong every time; both are on unless turned off. A screen shows only the keys it can use: no Door key without a lock or a door action, no Talk key without a microphone, no Sound key without a speaker.

- **The app looks at every frame of a live camera before a screen gets it.** A frame the decoder marks broken is left out, so the screen keeps the one before it. Frames that never came, a moment of up to a second much brighter than before and after, packets lost on the way and pictures a screen would refuse are counted, and the app's log says them every ten seconds when there are any, with a total every five minutes. With an empty file `tessera_frame_dump` in Home Assistant's config folder, each such frame and the two before and after it are kept as pictures in `tessera_diagnostics/frames` there (docs/CAMERA.md). It is there to find the white flash some live tiles show now and then.

- **The doorbell's chime plays whole on a Guition and a Waveshare P4.** On a screen whose speaker runs at 16 kHz the chime came in pieces: a fifth of a second of sound, a fifth of a second of silence, over and over. The screen hands the chime over four times a second, and the speaker held only a fifth of a second of it: a buffer of half a second meant for this was passed by, because the chime already has the speaker's own rate. The speaker's input for announcements and sounds now holds half a second itself, on every board: one rule for all of them, where the reTerminal D1001 (its speaker at 48 kHz, so the chime is converted) had that half second only by chance. A plugin's sounds, such as the voice assistant's wake sound, take the same way and get the same half second.

- **Plugins say that they are at your own risk.** Every plugin takes some of a screen's memory and processor time, and a screen with many at once (a voice assistant, a Bluetooth proxy, a camera and more) can run out of memory, slow down, freeze or restart. The Plugins page and a screen's Plugins tab now say so before you pick anything: you can try it, but add one or two at a time and check that the screen stays stable, and take the newest ones off first when it starts acting up. The card in the corner says it again beside Install, and names the screen when it would run four plugins or more after the build.

- **Debug mode: a screen keeps its log to warnings and errors, unless you ask for more.** A screen wrote two lines of log every ten seconds for each live camera tile, and more besides, and on a Guition 10.1 every line it wrote, to the cable on its board or to Home Assistant over Wi-Fi, came with a short flash on the live tiles; with the log quiet, a quarter of an hour went by without one. A screen now writes its warnings and errors alone, and the records a crash leaves are among them, so a crash still says what happened. ESP-IDF's own errors, such as a camera sensor that does not answer or a picture the decoder refuses, still come too: ESPHome passes them on at INFO under the tag `esp-idf`, and the screen keeps that one tag at INFO. **Debug mode** turns the whole log back on: a switch on the screen's device in Home Assistant, and a row under **This screen** on the screen's own settings page, one setting between them that the screen keeps over a restart. The troubleshooting report turns it on for its own 45 seconds of log and back again, so a report is as complete as before. To follow a screen's log in ESPHome, turn Debug mode on first.

- **A live camera tile on the right-hand half of a 10-inch screen no longer stays empty.** A live tile that fills its card gets its pictures scaled to just cover the card, and the ESP32-P4's picture decoder refuses a picture whose width times height is not a multiple of 8. The app made every side even, which is not enough: on a Guition 10.1 the tiles in the right-hand columns are one pixel narrower than those on the left (494 against 495 wide), got 494 x 278 pictures and showed nothing while the left ones streamed (2026-10-27, five live tiles on one page). Every side of such a picture is now a multiple of 8, up to 7 pixels more than the card, which the screen cuts off as it always did.

- **The camera dot tells watching from sensing.** The green dot in the top right corner that shows while a screen's own camera is in use is solid while anyone watches (Home Assistant's pictures or stream, a plugin that shows what it sees) and a ring of the same size while the camera only works something out on the screen itself, such as a light level or motion, and no picture leaves the screen. For plugins: plugin API 0.20, `Capture::SENSING` beside `Capture::CAMERA` in `tessera::capturing`.

- **"Not quite" on the feedback card goes on to help.** When a screen does not do what you expected, the card now offers two ways: **Send a report**, the troubleshooting report of that screen, which ends with a GitHub issue filled in with the report's reference, or **Read the troubleshooting guide** in the manual on the website. The card no longer builds an issue link of its own. In every language.

- **The manual in the sidebar.** A link under Plugins opens the manual on the website, named in every language.

- **A plugin's part stays in a screen's build while the screen is offline.** The plugins file the app writes for a screen left out a part that needs something of the board (Screen camera's **Video** needs a microphone) whenever the screen was offline or restarting at that moment: it then reported no board, so the app saw no microphone. A build from that file had no video server, and the screen's camera gave no picture in Home Assistant (a reTerminal D1001). While a screen says nothing, the app now goes by the board its profile builds from.

- **A screen whose glass is turned no longer freezes and restarts while its top bar is held.** On the reTerminal D1001, the Tab5 and the Guition 10.1 every picture goes to the glass through the ESP32-P4's picture engine, turned a quarter. The line that grows along the top while you hold the bar is a strip a few pixels thin, and now and then the engine never finished one: the screen stood still and restarted half a minute later. It is a known flaw of the chip (Espressif's DIG-734, espressif/esp-idf #19096), and the firmware's guard already cut most such strips into pieces the engine finishes; it now also cuts the ones whose last part is exactly the size the engine's buffer holds, the two that stopped a D1001 on 2026-10-27. Held 40 times in a row on a D1001 with live tiles: no restart, where it froze within four holds before. A restart of this kind now also leaves the last calls to the engine in the screen's log and in the troubleshooting report, the one that never came back marked. And should the engine ever stall again, the screen no longer stands still for half a minute: it restarts within four seconds, with "PPA copy never finished" and the copy's size and place as the reason in its log and its report. The first build of this missed it on a Tab5 with two live camera tiles, which stood still for 20 seconds as before; that watch now runs on its own, and on a reTerminal D1001 it caught a forced stall after three and a half seconds. On a Guition 10.1 with a chip of revision 3 (its v3 profile) the guard now also counts in the engine's own blocks of 32 rows, where it counted the earlier chips' 16 and let some thin turned strips through whole that the engine can stall on.

- **An ESP32-P4 screen comes back after an update or a restart, instead of restarting until its power goes off.** On an ESP32-P4 a software restart resets only the processors, not the link to the Wi-Fi chip beside them (an ESP32-C6), and now and then that link came out of it stuck: after an update over the air the screen restarted every 13 seconds and never came online until its power went off, and then ran the firmware from before the update (a Guition 10.1 V3 here, about one restart in five). Every restart of an ESP32-P4 screen now resets the whole chip, as a cold start does; a link that a crash leaves stuck costs one more restart. A new diagnostic sensor, **Wi-Fi co-processor**, says what firmware the C6 runs (for example `ESP-Hosted 2.3.2 (host 2.12.12)`), and the troubleshooting report includes it. A screen without this firmware yet that keeps restarting after an update: take it off power for five seconds, then update it again (docs/JC8012P4A1.md, "The Wi-Fi chip after a restart").

- **Presets for a light, one tap away.** A light's tile (and a light group's) can have up to four presets: round keys in Home Assistant's own favourite-colour style that each set a white shade or a colour and a brightness at once. Choose **Presets** under **Direct control on the tile** in the editor, or **Brightness slider and presets** on a tile two rows high; they also show on the light's card, beside its sliders on a wide screen. The key of the preset the light shows has a ring round it; on a light group with lamps that cannot all show colour, it is read lamp by lamp. **Show brightness on presets** adds each one's brightness to its key. A light with effects, such as a WLED, can also keep an effect in a preset, with its colour palette, speed and intensity, or keep the colours of the effect itself; and a preset can be one of the lamp's own presets or playlists. Such a key is grey with the first letters of its name. A tapped preset turns a spinner round its key until every lamp has taken it, then the ring shows. On every screen with 8 MB of flash or more; the CYD and other 4 MB boards keep the slider (docs/LIGHT_PRESETS.md).

- **A blind's bar reads the same everywhere.** On a cover group's page, the bar of each blind filled with the part that was open, while the tile and the cover's card fill the part that is closed, as Home Assistant does: a closed blind looked open there and the other way round. The group page and a cover's bar lying across a wide tile now fill the closed part too, and dragging works the same way round. A tilt bar lying across a card or the group page has its open end at the left, as in Home Assistant, and a cover group's **Slats open at** (100 % or 50 %) now counts for every blind on its group page.

- **A tile of your own words: the template tile.** Add **Template** from the screen's own cards and write in it as in Developer tools › Template: plain words, `{{ states('sensor.x') }}`, `{% if %}`, a heading with `#`, bullets with `-`, a small table, **bold**, and green, red or blue with `:good[…]`, `:alert[…]` and `:accent[…]`. Home Assistant fills it in and the screen follows every change; when the result is empty the tile disappears, so a page can stay quiet until something needs you (wish #88). The field completes your entities with their state, an entity's attributes with their values and the states it can have, and Home Assistant's functions and filters; under it you see the result as the screen gets it. On every screen with 8 MB of flash or more, up to eight per screen (docs/TEXT_TILE.md). Testers: try it on a 4-inch and a 10-inch screen with one tile that uses `now()`, one that reads many sensors (`states.sensor | ...`) and one with a table, and say how it reads from across the room, whether the screen stays smooth while they change, and anything the editor's result shows that the screen does not.

- **A busy calendar shows the whole week.** A calendar card could look empty from a few days ahead while Home Assistant had the events: the card carries a fixed number of events to the screen, nearest first, and long titles and places filled it by midweek. A screen without PSRAM also kept the first 24 events from Monday on, including ones already past, and didn't count the rest. Events now go to the screen short (a title of up to 28 characters, a place only for the nearest few), so about twice as many fit; a tap on an event opens it with its whole title (on two lines where one does not hold it), place and notes, fetched from Home Assistant at that moment. A screen without PSRAM keeps 48 events instead of 24, every screen keeps the nearest ones, and what doesn't fit is counted as "more". The agenda's "12 more this week" now counts this week only; it counted next week and everything the app left out too.

- **Guition screens with a camera see the whole room (#326).** Screen camera has a setting **Camera field of view**, and on the Guition screens' camera (OV02C10) **Full** is now the default: the whole of what the camera sees at half the resolution (960 x 528), 15 pictures a second. **Sharp**, the middle at full resolution and 30 a second, is still there, and a mode that gives no picture goes back to Sharp by itself. A screen whose setting shows Sharp keeps it: choose Full once to see the whole room. Tried on the Guition 10.1 and 4.3-inch. The camera of the M5Stack Tab5 and the reTerminal D1001 keeps Sharp: its sensor has no such mode we know of.

- **A camera picture beside four live tiles comes within a second.** On an ESP32-P4 page with four live camera tiles, the fifth tile's picture and a media cover could take half a minute to two minutes: the picture waited for its turn on the glass behind the live tiles, which always went first. It waits in turn with them now; on a reTerminal D1001 187 pictures in 40 minutes took 0.3 s in the middle and 0.8 s at most, and the live tiles ran smoother too.

- **A doorbell ring could restart a busy screen.** The chime, 60 KB, was made at the first ring in the chip's own memory, and a screen with many plugins and pages had no free block that large left (an M5Stack Tab5 with nine plugins and six pages). It is made in PSRAM now.

- **A camera with sound no longer turns into loud noise after a hiccup in its stream.** A change on dev of 2026-10-25 (never in a release) left the screen's sound buffer one byte short of an even size. When it ran full, a part went in cut to the room left, an odd number of bytes, and every sample after it was a byte off: seconds of full-scale noise, until it came right by chance. The buffer is even again, and a part goes in whole or not at all.

- **The editor says which live cameras wait their turn.** A screen streams four live camera tiles at once; on a page with more, the editor marks the others "Live paused" and the tile's settings say that this screen plays four cameras live at once while the others show a picture every 15 seconds, and that with two cameras each one runs more smoothly than with four. The number comes from the screen itself.

- **A fifth live camera on a P4 page gets its picture.** A screen streams four live tiles at once and shows the others as stills every 15 seconds; with the screen's own video watched as well, the fifth tile's still found no free connection and was tried every second. A P4 screen now counts its streams and downloads (and Screen camera its video's viewers) into the connections the firmware allows, and a picture that could not be fetched waits its tile's pace before it is tried again.

- **A screen's camera follows how its board mounts it and how the screen is turned.** A board whose camera sits upside down against the glass (the M5Stack Tab5) now says so, and a screen turned half way round turns its camera's picture with it, so Home Assistant shows the room upright; Screen camera 0.5.0 adds a setting to turn it once more, for a screen mounted the other way round. Tab5 owners on dev: check that the camera stands upright in Home Assistant, and say so.
- **An ESP32-P4 screen plays four camera tiles live at once.** The first four live camera tiles on the page the screen shows stream, in tile order; any more keep a picture that refreshes every 15 seconds, as a camera tile without Live does. A live tile streams only while its page is open, so the four are per page on the glass and the other pages cost nothing. The screen says the number in its hello and refuses a fifth stream itself, the app refuses it too for that screen, and the log says how many tiles kept their stills. One number for every P4 board, so you know what to expect before you add a fifth (docs/PLATFORM_PLAN.md, "A cap on live tiles").
- **One sound at a time, by rank.** The screen's loudspeaker now has an owner: a doorbell's ring comes first, then the voice assistant, then a camera's sound, then music from Home Assistant. A camera opened with sound pauses the music, which does not start again by itself; the voice assistant takes the speaker from a camera's sound and gives it back after the session; a ring takes it from everything and nothing takes it from a ring. Short sounds such as the tap and Home Assistant's announcements play over whatever plays, as before. Plugins can ask for the speaker the same way (plugin API 0.19, `tessera::audio`).
- **A screen says what its hardware can do.** The hello now carries one record (live video, speaker, microphone, echo cancellation, a camera of its own, live tiles at once, memory), which the app and plugins read instead of guessing from the board (plugin API 0.19, `hw::caps()`).

- **The audio of the Tab5 and the Waveshare P4 screens is now declared as parts.** A board names its codecs and gives their pins; a shared part file per chip does the rest, so the next board with an ES7210, an ES8311 or an ES8388 is a list of pins (docs/PROFILES.md, "Parts"). The firmware is the same on both transports, with one change: the Tab5's plain I2S bus (an Override YAML choice) reads its microphones with the same ES7210 driver as the Waveshare P4, automatic gain off and 30 dB as before. The transport is now `AUDIO_TRANSPORT` in a screen's Override YAML; `TAB5_AUDIO_TRANSPORT` and `P4_AUDIO_TRANSPORT` still work in this release and go in the next. Tab5 owners on the plain I2S bus: check that the wake word and the speaker still work, and say so.

- **The M5Stack Tab5 gets what the other P4 screens got.** Its hardware file kept a copy of its own of the chip's settings and so missed the longer task watchdog and the Wi-Fi driver's buffers in PSRAM: a Tab5 with live cameras restarted every few minutes where the other P4 screens kept going. Every P4 screen now builds on one shared file, and a check keeps the next board on it.

- **An ESP32-P4 screen keeps more of its internal RAM free with live cameras and the screen's own video.** The Wi-Fi chip's driver now keeps its packet buffers in PSRAM, and the tasks that stream a camera or download a picture keep their stacks there. With two live camera tiles and the video playing, a reTerminal D1001 stays at about 175 KB of internal RAM free (it fell to 60 KB before), with no allocation that found no room in hours of testing and the same frame rates.
- **A picture's download had almost no stack left.** Since the screen decodes JPEG pictures itself, a download used nearly all of its 6 KB of stack; it has 10 KB now, at no cost of internal RAM.
- **A restart after an abort says which.** A failed assert or an abort now leaves what it said and who called it, and the next boot logs it; the troubleshooting report keeps it with the crash (docs/REPORTS.md).

- **Live camera tiles on an ESP32-P4 screen leave its internal RAM alone.** Every packet the Wi-Fi chip received stayed in the driver's own buffers in internal RAM until the screen had read it, so two live camera tiles took a reTerminal D1001 from about 250 KB of it free to 60 KB, and the Wi-Fi driver's next buffer found no room (the lost packets a screen then waits on). Received packets are now copied into PSRAM at once, and a live stream reads into PSRAM too: with the same two tiles the D1001 keeps about 210 KB free and its lowest is 170 KB instead of 54 KB, at the same frame rate.

- **A screen says what asks its internal RAM for room.** An ESP32-P4 screen keeps every plain allocation in its internal RAM, and a screen that runs out restarts with nothing in its log to say what took it. A screen now logs each time its internal RAM falls another 16 KB below the lowest it had, and every allocation that finds no room (its size, the function and the task), and the next boot hands both on, so the troubleshooting report has them with a crash (docs/REPORTS.md). The main loop's stack at a task watchdog now reaches the report as well: it was logged at boot, before anything over the network could read it. Its line every five minutes also says how often the panel ran dry since boot (a blue frame), so a test of memory sees what it costs the glass.

- **An ESP32-P4 screen with live camera tiles no longer falls back to its old firmware after an update.** ESPHome keeps a new firmware on trial for its first minute and puts the old one back when the screen restarts in that minute. Live streams started in that same minute, and on a Tab5 with two live tiles that was enough to restart it on every update, so the update never stuck. Live tiles now show their stills until the new firmware is confirmed, then start streaming; an ordinary restart streams at once as before.

- **Opening a camera full screen over live tiles no longer leaves a band of a tile's picture under its top bar.** On an ESP32-P4 screen the live tiles of the page stop before the full view's stream is opened instead of at the next drawing, and the screen draws the whole glass once more when the view's first picture arrives, so nothing a tile copied in the meantime stays on the glass (docs/CAMERA.md).

- **The Waveshare ESP32-S3-Touch-LCD-4.3C, experimental.** The 4.3C (also in the 4.3C-BOX) has the 4.3's glass but
  Waveshare's CH32V003 expander in place of the 4.3's CH422G, so a 4.3C built as a 4.3 started with its touch in reset
  ("touchscreen is marked FAILED: Calibration error") and a dark screen. It is a board of its own now, under New
  screen, with a dimmable backlight. Built from Waveshare's own pin table and timings, not yet tried on the glass.

- **My screen doesn't work right (docs/REPORTS.md).** A button on a screen's page makes one troubleshooting report of that screen: the board and every version, the plugins, the screen's YAML, the crash it kept from its previous boot and a minute of its log, Home Assistant's log lines about it and its diagnostics, the app's log and the last build, with passwords, keys, addresses and names taken out. Every file can be read on the page and the zip downloaded; with a consent per report it goes to Tessera, which answers a reference to quote on GitHub or Discord, keeps it 30 days, and can ask a question back if you leave an e-mail address. A fuller report (your pages with their entity ids, every ESPHome log line) is an opt-in that says what it adds. The app also notices a screen that rebooted, reads the crash ESPHome kept and shows it on the page, decoded when the screen was built here.

- **An ESP32-P4 screen no longer restarts when its Wi-Fi chip answers slowly.** The P4 boards (reTerminal D1001, M5Stack Tab5, the Guition and Waveshare P4 panels) ask their ESP32-C6 about the Wi-Fi over the same link the pictures come in on, and under a busy link (two live camera tiles, the video going out) one lost answer restarted the screen: minutes after a boot with live tiles, in the first minute of a boot, under the video. The screen now waits long enough for such an answer to fail on its own and goes on, and its top bar asks the Wi-Fi chip for the signal at most every five seconds instead of at every draw; the update of a Tab5 that restarted at every boot and rolled back to its old firmware installs again (docs/CAMERA.md, "The main loop and the C6's answers").

- **A restart by the task watchdog says where the main loop was.** When a screen restarts because its main loop stopped feeding the watchdog, the next boot logs the main loop's own stack at that moment, and the troubleshooting report keeps and decodes those lines with the crash. Until now the crash record only named the idle task, because the main loop was waiting on something else, so a screen that restarted under a stuck Wi-Fi link looked like it crashed for no reason (docs/REPORTS.md).

- **A turned ESP32-P4 screen no longer restarts behind a live camera tile.** The M5Stack Tab5 (a 720x1280 panel shown as 1280x720) turns everything it draws with the P4's picture engine, and under the ESP-IDF that ESPHome builds with, a turned copy of some sizes never finishes: the screen froze behind it and its watchdog restarted it, every few minutes with live camera tiles. Such a copy now goes to the engine in pieces it finishes (docs/CAMERA.md, "A turned copy the 2D-DMA never finishes").

- **Events: alerts and the doorbell, with wizards that add the automation to Home Assistant.** Alerts in the sidebar is now **Events**, with two parts: Alerts and Doorbell. Each starts with one big button that opens a wizard: one step at a time, with a line of help on each, you point to what starts it (your doorbells first, or any sensor, switch, toggle helper, button or event of yours, and it says how it will read it), fill in the rest, choose the screens, try it once, and then either **Add to Home Assistant** saves the automation for you (no restart needed), or **Copy YAML** gives just the action to paste into an automation you already have. An alert can have one or two buttons, each with its own color and, if you like, an action of Home Assistant's for an entity of yours (open a lock, run a script), and the last step says what that means for each screen (an older screen shows one button, a screen without pictures shows no camera). Every automation from Tessera is called "Tessera: <name>" in Home Assistant, and the wizard lists them with a link to each.
- **The doorbell.** An automation fires `esp_screens_doorbell` with your doorbell's camera, started by whatever rings at your house (a doorbell Home Assistant knows, Reolink's Visitor sensor, a button). An ESP32-P4 screen wakes up, plays a chime and opens the camera full screen, live, with its sound on; any other screen shows the camera's picture in an alert. The first screen someone touches answers the ring and the others close it. A ring nobody answers closes after its timeout and stays in the top bar ("2 min ago") until someone taps it. The app fires `esp_screens_doorbell_answered` or `esp_screens_doorbell_missed` once per ring, for a notification of your own (docs/DOORBELL.md). Needs the screen's Update.

- **A robot vacuum's larger tile.** On a screen with 8 MB of flash or more, a robot's tile two rows high can now show its map, its rooms to pick, its routines, or the map with the rooms, beside its keys: a small screen of its own with the robot's state and battery at the top and Start and Dock (and the cleaning mode as icons) at the bottom. Tap rooms in the order you want them cleaned and press Start. Choose it under the tile's controls in the editor, or from the tip that shows when you drag the tile larger. Only what your robot has is offered. The CYD and the other 4 MB screens keep the tile with its keys (docs/VACUUM.md, "A larger tile").

- **A screen's own camera as live video with sound in Home Assistant** (the P4 screens with a camera: the reTerminal D1001 and the M5Stack Tab5). Screen camera 0.4.0 brings a part Video: H.264 from the screen's video encoder and the microphone as Opus, in sync, playing in Home Assistant's browser page and app about a third of a second behind. Under Settings, **Video in Home Assistant** installs the Home Assistant integration it needs (Tessera video) when you press Install, and restarts Home Assistant when you say so; then Tessera adds a camera **Video** to each screen with the part by itself, without a password to type (docs/CAMERA.md, "The screen's own camera as video in Home Assistant"). Every ESP32-P4 screen gets a larger network send buffer for it.

- **A plugin added with a link can be taken off the list again.** A release added with a link that no screen runs (an old try-out) had no way off the Plugins page except restarting the app. Its details now have "Remove from the list". A plugin a screen still runs is taken off the screen first.

- **Pictures in one system (docs/PICTURES.md).** Every picture a screen shows now goes one way: the camera full
  screen, a camera's or a cover's tile, a map, the media card's cover, a player's library, a vacuum's map, the
  screensaver's cover, camera and photos, an alert's picture and a plugin's places. A screen asks for each as one
  question (its places, what each is of, how it is painted, whether it may stream), and the app answers every question
  with the same rules, the same fetching and the same painting, where it used to have a way of its own for each. What you
  see stays as it was, with these differences: an album cover's rounded corners are smooth, a vacuum's map and a page of a
  player's library come within the screen's picture memory like every other picture, no picture is held twice in a
  screen's memory any more, and a live camera's stream takes its share of the screen's picture memory while it runs.
  A camera's still on a tile, in an alert or on the screensaver is the newest frame of its stream while one runs, not
  another snapshot from Home Assistant. Screens with older firmware keep working with this app, and screens with this
  firmware keep working with an older app.
- **The screen shows when its own camera is in use.** A small green dot in the top right corner, on top of everything,
  while Home Assistant takes pictures or a stream from the screen's own camera (the Screen camera plugin) or a plugin
  uses the camera on the screen itself. No plugin or setting can hide it.
- **A live camera no longer goes black every few seconds before its stream starts** (the P4 screens). While Home
  Assistant's stream of a camera had not given its first frame yet, the screen got the camera's picture once and then
  nothing, closed the stream after six silent seconds and asked again, black in between, for up to a minute. It now
  gets the camera's picture every two seconds until the stream comes, and a camera Home Assistant has no such stream for
  (one with HLS alone) goes over to its pictures at once instead of after 20 seconds.
- **A live camera starts sooner, and says when it is live** (the P4 screens). The app started each stream from Home
  Assistant by asking a server on the internet for its address first (STUN), about five seconds before anything else,
  which no stream between the app and Home Assistant needs. Until the stream's first frame the camera's picture stands
  still, so a live tile now turns a small spinner in its top right corner, and the camera full screen one in its top
  bar, until the picture is live.
- **Pictures as JPEG on the ESP32-P4 screens.** A camera's tile and full view, the screensaver's photos, a cover and a
  plugin's pictures now reach a P4 screen as JPEG, about a tenth of the bytes of the BMP it got before, and its hardware
  decoder unpacks them. A map and a vacuum's map stay BMP (JPEG blurs their lines and words), as does every picture for
  the other screens and the editor.
- **The album cover behind a tile of one row too.** A player's tile set to Album cover had the cover in the icon's place on a tile of one row; now the cover lies dimmed behind the whole card, as on a taller tile, with the name and what plays in light letters over it. While nothing plays, it shows the covers of your library there as one strip, as the taller tiles show them as a mosaic. Needs the screen's Update.
- **One picture after the next without a third copy in memory.** When a picture changed (the next screensaver photo,
  another track's cover, a map that moved) the screen held the old one, the download and a copy of it for a moment; it
  now takes the download as it is. A map or cover that did not change comes as "not changed" again instead of whole.
- **Smoother screens, above all the large ones.** A screen drew its whole glass again whenever it brought another
  page up to date in the background, and twice a minute it drew every card again for the clock. On a 10-inch screen
  each of those took about a fifth of a second, in which nothing moved and a sound that played stuttered. Now only the
  page keys and the cards that show the time are drawn again, and a plugin's sounds keep half a second ready.
- **Plugin API 0.18: popups.** A plugin can show a popup over the screen, the card an alert shows, as high as what it
  says and as wide as the screen allows, for a moment that wants your eye: the Voice assistant shows what it heard and
  its answer as it speaks, with rings that ripple while it listens and an arc that turns while it thinks
  (docs/PLUGINS.md, "A popup").
- **Plugin API 0.17**: a picture's place without its grey block, a call when a place's picture came or did not, a
  media player's cover, a camera's picture and an entity's own picture as a place's address, `ui::live` for a place
  whose camera streams on a P4 screen as a live tile does, and `capturing()` for a plugin that uses the screen's own
  camera (docs/PLUGINS.md). Tessera's own Cinema, New music and Picture frame use it: no more grey bars in a cover flow
  after the screen fetched its pictures again, Picture frame shows what a player plays, and a camera in Picture frame
  is live on a P4 screen.

- **The editor's cards look like the cards on your screen.** While you lay out a page, every card is now drawn at the
  sizes of your own screen: its letters in the screen's Roboto (a bold name, a plain line), its icon circle, corner and
  padding, and each part where the screen puts it. Before, the inside of a card had sizes of the editor's own, close on
  a 4-inch Guition but far too small on a CYD, a 4.3-inch or a 10-inch screen. A long name is cut where the screen cuts
  it, a light that is on says its brightness, a blind and a player on a small card say what the screen says, a lock and
  a player show their own icon, and a thermostat's number has the screen's decimal. Larger cards follow the screen as
  well: a thermostat's big number between its keys with the temperature now under it, a robot vacuum's keys, a player's
  track, artist and volume, and a player over a whole page with its cover, progress bar and keys. A card you drag keeps
  its look while it moves.
- **Stars for plugins, and a heart for any plugin.** A few days after a screen first runs a plugin from the Plugins
  page, a card above the screen asks how it works for you: one to five stars, then Send. Later asks again in two
  weeks; Don't ask again, what is shared and the privacy page are behind the card's ⋯ menu. A plugin's details take
  stars at any time too, and its card and details show its rating and how many homes use it. You can now give a heart
  to any plugin of the Plugins page, also one that is on none of your screens, right on its card. On the first card,
  on the In use tab or in Settings you can let the app count your plugins in the store, as Home Assistant's analytics
  counts integrations: once a day the names and versions of your plugins and your screen models go to Tessera, nothing
  else, and turning it off removes them there. The Plugins page sorts by best rated and most used, and every plugin
  has its own page on the Tessera website with these numbers per screen model.
- **A weather card that fills a cell says its condition in the screen's language (#298).** A weather card on a page of its own showed Home Assistant's key, `clear-night`, under the temperature, where the editor said "Klare Nacht" (Home Assistant sends the key in every language and only its frontend translates it). The card's state line (`detail_state`) now says the condition with the same words the weather cards and the editor use, in the screen's language; a condition the screen has no word for keeps Home Assistant's word or the key, as before. Reaches the preview and the screen after the firmware is rebuilt. Not tried on a screen yet.
- **The camera of the Guition ESP32-P4 screens, experimental.** The Guition JC8012P4A1 (10.1 inch, also its V2 and V3),
  JC1060P470 V2 (7 inch) and JC4880P443 (4.3 inch) in their camera version (the "C" in the model name) carry an
  OmniVision OV02C10. Their boards now name the bus it answers on, so the Screen camera plugin fits them: the screen
  becomes a camera of its device in Home Assistant. Tried on a JC8012P4A1 V3 by
  [@Heronimonimo](https://github.com/Heronimonimo) and [@ivanfmartinez](https://github.com/ivanfmartinez); on the
  other boards it is untried yet. It needs the Screen camera plugin's version with the OV02C10.
- **Speaker and microphone on the Guition and Waveshare ESP32-P4 screens, experimental.** The Guition JC8012P4A1
  (10.1 inch, also its V2 and V3), JC1060P470 (7 inch, also its V2) and JC4880P443 (4.3 inch) now use their speaker and
  microphone, both at once, and the Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, LCD-7 and LCD-10.1 their speaker and two
  microphones with echo cancellation, as the Waveshare P4 86 panel does. Such a screen is a media player in Home
  Assistant for announcements and music, has Volume and Microphone under Settings, Extras (the Waveshare boards also
  Microphone gain, Automatic gain and Echo cancellation), and fits the plugins that need a speaker or a microphone.
  Thanks to @Eugen417, who runs this audio on a Guition JC8012P4A1 V3 (#259), and to @Nulifier, who ran it on the
  Waveshare LCD-7 (#274); on the other boards it is untried yet. These screens now build with ESPHome 2026.9.0 or newer,
  the one the app has.
- **The Guition 7 inch on the yellow board without a case (#289).** The JC1060P470 also comes as a yellow board
  without a case, sold as a 7-inch CYD, and on that one every tap landed half a turn round: a tap on the top left
  reached the bottom right. New screen now asks under Board whether it is the black one in a case, as before first, or
  the yellow one, which gets its touch turned round and the speaker and microphone on its own pins. Screens you already
  have keep what they have; a yellow one gets the same with `BOARD_VARIANT: "yellow"` under `substitutions:` in its
  Override YAML. Thanks to [@svenar-nl](https://github.com/svenar-nl), who found it and tried the fix.
- **Your music while nothing plays.** A media player's tile on Album cover that is 1 x 2 or 2 x 2 was an empty block
  while nothing played. It now shows the covers of the player's library side by side, darkened, with the player's
  name and state over them: for Spotify the covers of your Liked songs, newest first. Every minute one cover moves on
  to the next. A tap opens the player as before. Screens out there get it with the app, without a new build. Music
  Assistant shows the covers it gets from streaming services; covers of your own files keep the tile as it was.
- **Plugins fit a 4 MB screen again (#292).** Since 0.4.88 the app refused every plugin for a CYD, a CYD ILI9342 or
  a Hosyond 4 inch once it had built that screen, and said the screen had room for about 0 KB more. The app kept a
  plugin under 93 % of the screen's update slot, and the firmware of these boards alone is now past that. Plugins may
  now fill the slot up to 97 %, which leaves about 50 KB for plugins on a CYD.
- **A vacuum's second line set to Nothing shows nothing (#293).** A vacuum tile with Second line "Nothing" still
  showed " / 100 %" under its name, and its own text or a value of the entity got the battery added after it too. The
  battery now ends only the automatic line ("Docked / 100 %"), and not the Unavailable word either.
- **A new screen swipes out of the box.** A screen set up with New screen now has Swipe between pages on from the
  start, so it swipes through its pages, opens its settings from the top edge and opens the Dock from the bottom edge
  without turning anything on first. Screens you already have keep the setting they have through the update. Turn it
  off under the screen's Settings, Swipe between pages.
- **A tap stays a tap on the Waveshare 7B.** On the 7-inch Waveshare ESP32-S3-Touch-LCD-7B a short tap could count
  as holding the tile: a plugin's tile then did nothing and only showed its press, and a large tile could open its
  card instead of switching. The screen heard a finger let go one step late, and on this large glass the redraw of a
  pressed tile can take longer than the time that makes a touch a hold. A touch screen now takes the moment the finger
  lets go from its touch panel as soon as the panel reads it. Holding a tile still opens its card. Comes with the
  next build of the screen.
- **A plugin's screensaver follows its options at once.** Changing an option of a plugin's clock or screensaver
  face (a colour, seconds on or off) now shows on the screen right away, as Tessera's own clock does, instead of only
  after the screensaver was turned off and on again. On main since 2026-10-18 for screens that are built again.
- **New screen accepts a secrets.yaml of comments only (#263).** ESPHome Device Builder can leave a `secrets.yaml`
  with only comments in it, and the Wi-Fi step of New screen called that file invalid and stopped. It now reads it as
  a file without Wi-Fi yet, as ESPHome does, and adds the two Wi-Fi lines below the comments. A file that is not a list
  of secrets is still left alone.
- **The M5Stack Tab5 with an ST7123 display (#240).** The Tab5 is sold with an ST7121 or an ST7123 display controller,
  and the wrong one leaves the screen black. New screen now asks which one the Tab5 has, with the ST7121 as before
  first. Tab5 screens you already have keep the ST7121. Thanks to @pedromfa and @the-make-r, who found and tested the
  ST7123.
- **The Waveshare 4.3 inch with 8 MB of flash (#265).** Some Waveshare ESP32-S3-Touch-LCD-4.3 boards carry 8 MB of
  flash instead of 16 MB, and a screen built for 16 MB started over and over on them with a black glass. New screen
  now asks how much flash the board has, with 16 MB as before first. Screens you already have keep what they have.
- **A plugin's screensaver step shows its entity's picture (#286).** A plugin's own step of the screensaver that shows
  a picture of its entity, such as a photo of an image entity, got every picture refused. The step now tells the
  screen which entity it belongs to, so its pictures arrive, as they already did on the plugin's tile. Screens out
  there get it with the app, without a new build.
- **Pictures reach screens on a second network (#276).** When Home Assistant is on two networks, for example the
  home network and a separate one for devices, screens on the second network got the picture address of the first
  and showed no camera images, covers or maps. Each screen now gets the address Home Assistant has on its own network.
  With one network nothing changes.
- **Firmware & USB knows a screen's address (#143).** Installing over Wi-Fi from Firmware & USB asked for the
  screen's address, although the app already knew it for the screen's Update. It now fills in the address of a paired
  screen when you choose its profile. An address you type yourself stays as you typed it. Thanks to @woozer for the
  change.
- **A plugin tile can follow several Home Assistant entities (plugin API 0.15, #288).** A plugin may now ask in a
  tile's options for entities to choose, each with its own searchable list, such as the grid, the solar panels and
  the battery of an energy dashboard. Tessera sends each chosen entity's state to the tile and follows it, and a new
  choice takes effect without building the screen again. Thanks to @vajpeters, who built it for the Victron plugin.
- **Plugins can wake the screen (plugin API 0.16).** A plugin can now wake a screen the way Home Assistant's Wake
  button does, for example when a camera sees someone come: a screen in standby lights up, and one that is on stays on
  for its standby time from then, while Back to page 1 keeps counting from the last touch. A plugin that does this has
  a setting of its own for it, off until you turn it on. Thanks to @Heronimonimo, who asked for it for the Screen
  camera plugin.
- **Opening a page from Home Assistant wakes a screen that is still preparing.** A layout that reaches a screen in
  standby is prepared once the screen is lit, and the Show page action did nothing in between. It now wakes the screen
  first, and the page it asked for opens as soon as the pages are ready.
- **A plugin tile of a plant is no longer called gone (#262).** The editor said that a plugin's tile of an entity
  Tessera has no tile of its own for, such as a plant, showed an entity that no longer exists. It now knows those
  entities from the plugins' own list, and calls one gone only when Home Assistant really no longer has it.
- **The editor finds its way back after hours in the background.** Opened again in the Home Assistant app on a phone
  after a few hours, Tessera said that ESP Screen Manager could not be reached and kept saying so for minutes, until
  you went to another page of Home Assistant and back. Home Assistant renews the app's access within a minute of
  coming back, but the editor waited up to five minutes before it asked again. It now asks every ten seconds until it
  gets an answer, and opens its live connection again when that connection has gone quiet.
- **Russian (#259).** The screens, the editor and the app's messages now speak Russian, the first language in another
  script than Latin. A screen built in Russian carries the Cyrillic letters in its fonts, so names and states in
  Cyrillic show on it; no screen in another language spends flash on them (a Russian CYD takes about 33 KB more).
  Choose it under Settings, Language & region, then update the screen; the editor follows the language of your Home
  Assistant profile. Thanks to [@e2ret](https://github.com/e2ret), who translated the screen's texts. The rest is a
  first draft that no native speaker has checked yet: corrections are welcome.
- **A new board, experimental: the Waveshare ESP32-S3-Touch-LCD-4 V4.0**, the 4-inch board without the "B" in its
  revision 4.0, with Waveshare's CH32V003 expander, 480 x 480 glass, GT911 touch and a dimmable backlight. Its board
  file is the one Simismin ran on such a board ([wish 117](https://tessera-maxgramser.on-forge.com/wishlist/117)),
  brought in by [@PedanticAvenger](https://github.com/PedanticAvenger)
  ([#275](https://github.com/MaxGramser/homeassistant_espscreen/pull/275)), who ran it with Home Assistant, rotation
  and touch; [@leonardospina](https://github.com/leonardospina) ran the same board with a board file of their own
  ([#213](https://github.com/MaxGramser/homeassistant_espscreen/pull/213)). Earlier revisions of the same name have
  another expander and are not supported. Choose it under New screen.
- **A new board, experimental: the Seeed SenseCAP Indicator D1 series with the GX panel**, 3.95-inch 480 x 480 glass
  with FT6336U touch and a dimmable backlight on its ESP32-S3. The D1, D1S, D1L and D1Pro share that side of the board;
  the RP2040, its sensors and the LoRa radio stay as they are. Run on a D1L by
  [@sillevl](https://github.com/sillevl) ([#277](https://github.com/MaxGramser/homeassistant_espscreen/pull/277)), who
  checked touch, rotation, brightness, standby and a cold start. The DX panel is not covered. Choose it under New
  screen.
- **A new board, experimental: the Freenove FNK0104S**, a 4-inch ESP32-S3 board with 480 x 320 ST7796 glass over SPI,
  FT6336 touch and a dimmable backlight. Run by [@bwalshin](https://github.com/bwalshin)
  ([#285](https://github.com/MaxGramser/homeassistant_espscreen/pull/285)), who checked its colours and the touch in the
  middle and the corners. Choose it under New screen.
- **A new board, experimental: the Wireless-Tag WT32-SC01 Plus**, a 3.5-inch ESP32-S3 board with 480 x 320 glass on an
  8-bit bus, FT6336U touch and a dimmable backlight. Run by [@cjd](https://github.com/cjd)
  ([#238](https://github.com/MaxGramser/homeassistant_espscreen/pull/238)), who checked touch, colours, dimming and
  standby, and by [@wiktorschmidt](https://github.com/wiktorschmidt). Choose it under New screen, as WT32.
- **A new board, experimental: the Waveshare ESP32-P4-WIFI6-Touch-LCD-7B**, the 7-inch ESP32-P4 board with 1024 x 600
  MIPI-DSI glass, GT911 touch and a dimmable backlight, built for the rev3 silicon Waveshare ships now (a board with the
  earlier silicon needs one line of Override YAML). Run by [@tomvanoosterwyck](https://github.com/tomvanoosterwyck)
  ([#271](https://github.com/MaxGramser/homeassistant_espscreen/pull/271)), who checked the picture, touch, brightness,
  standby and the wake. Its speaker and microphones are in use too (the first entry here). Choose it under New screen.
- **A new board, experimental: the Waveshare ESP32-P4-WIFI6-Touch-LCD-7**, the 7-inch ESP32-P4 board with 1280 x 720
  MIPI-DSI glass, GT911 touch and a dimmable backlight, built for the earlier ESP32-P4 silicon (a board with rev3 needs
  one line of Override YAML). Run by [@Nulifier](https://github.com/Nulifier)
  ([#274](https://github.com/MaxGramser/homeassistant_espscreen/pull/274)), who checked the picture, rotation, touch,
  the backlight and Wi-Fi. Its speaker and microphones are in use too (the first entry here). Choose it under New
  screen.
- **A new board, experimental: the Waveshare ESP32-P4-WIFI6-Touch-LCD-10.1**, the 10.1-inch board of the same series,
  with 1280 x 800 MIPI-DSI glass, GT911 touch and a dimmable backlight, on the earlier ESP32-P4 silicon. Its display,
  touch and backlight are those of a configuration Amazingwun runs on the board
  ([wish 125](https://tessera-maxgramser.on-forge.com/wishlist/125)), in a board file by
  [@icodeforyou](https://github.com/icodeforyou) ([#281](https://github.com/MaxGramser/homeassistant_espscreen/pull/281)).
  This board file itself has not been run on one yet. Its speaker and microphones are in use too (the first entry here).
  Choose it under New screen.
- **Dev in Docker.** A Docker install can try what comes with the next release: the image
  `ghcr.io/maxgramser/homeassistant_espscreen:dev` is the dev app, as the repository URL with `#dev` is in Home
  Assistant. Its screens build from dev, its Plugins page lists the plugins that wait for the next release, and each
  screen can be reinstalled from dev. Set `SCREEN_CHANNEL` to `main` to point the screens back at main
  (docs/DOCKER.md, "Testing dev").

## 0.4.90 (firmware 0.57.1 for waveshare43, waveshare5)

- **The Waveshare 4.3-inch and 5-inch update again with ESPHome 2026.10.** ESPHome 2026.10.0 checks more closely
  whether a pin is used twice, and on these boards the display and the backlight named the same line of the board's
  expander, so every update stopped with "Pin 2 is used in multiple places". The backlight now has that line to itself,
  as on the 7-inch, and the screen lights as before.

## 0.4.89 (firmware 0.57.0)

- **A thermostat's state line no longer runs into its card.** On screens with dense glass (the Waveshare P4 and
  the Tab5) a thermostat with many modes and a fan row drew "Heat · Now ..." against the top of the card with its
  - and + keys. The line now gets the room its text needs.
- **A screen whose Override YAML was deleted builds again.** ESPHome Device Builder lists a screen's Override YAML
  (`<name>.local.yaml`) as a device of its own, and deleting that entry there left the screen's YAML including a file
  that was gone, so every update stopped with "file not found". The app now writes the missing file again, empty, when
  it starts and before every build. Overrides that were in it are not brought back.
- **Photos as a screensaver.** The screensaver has a new step, Photos: the photos of a folder of Home Assistant's
  media, one after the other over the whole glass. Pick an album, a person or a tag of Immich, a folder under
  Home Assistant's media, or Synology Photos; choose how long each stands, shuffled or in order, and whether a photo
  fills the glass or shows whole, and whether it stands still or moves slowly across the glass. iPhone photos are read
  too. Screens that show pictures only.
- **Screensavers from plugins.** A plugin can now bring its own face for the clock, the music or the photos, or a step
  of its own in the screensaver's list, with keys you can tap without waking the screen. A screen without that plugin
  keeps the step's own face.
- **The screensaver's play and mute keys follow Home Assistant as every key does.** They show their change at once and
  go back when Home Assistant does not follow, by the same rules as the keys on the pages.
- **Build on a faster computer.** Settings has a Build server card now: pair Tessera with ESPHome Desktop, ESPHome
  Device Builder or a headless `esphome-device-builder --remote-build-only` on a computer on your network, compare its
  fingerprint, and every screen's firmware is compiled there instead of on your Home Assistant machine: updates, plugin
  builds, New screen and Firmware & USB. The server builds with the same ESPHome version as the app (it installs that
  version once, beside its own), plugins from a folder go along, and the installing, the bridge on 4 MB boards and the
  download stay as they were. The card shows whether the server is there and what it builds, every build says where it
  runs, and when the server is off, away or cannot build it, the build simply runs here as before and says why. A
  build takes the screen's own YAML and secrets (its Wi-Fi password and keys) along to the server, encrypted to the
  key you paired, and to no other computer.

- **A cover shows that it is on its way.** A blind, curtain or garage door sent somewhere no longer jumps back to
  where it was while it moves: from the tap on, its tile and card show where it goes and say Opening or Closing, the
  slider's handle steps aside and a thin stripe glides over the slider in the direction it moves, until Home Assistant
  reports it there or stopped. The slider still takes a finger, so a cover sent the wrong way can be turned around at
  once, and the slats' tilt works the same way.
- **Slats that are open at 50 %.** Home Assistant counts a blind's tilt from 0 (closed) to 100 (fully open), and the
  screen draws its slats that way. Some blinds are open at 50 % and closed at 0 % and 100 %, one way and the other
  (the SwitchBot Blind Tilt among them). A cover tile with slats now has the choice "Slats open at 50 %" in the editor:
  the slats then stand flat at 50 and turn one way below it and the other way above it, open goes to 50, and close
  goes to the nearer closed side. Home Assistant's way stays the default.
- **A screen follows Home Assistant to another time zone.** Home Assistant's ESPHome integration tells a screen its
  time zone only when it connects, so a screen kept the old hour after the time zone changed in Home Assistant (a
  home on wheels crossing one) until Home Assistant restarted. The app now reloads each screen's integration when the
  time zone changes, and the screens show the new hour within seconds.
- **The editor remembers where you are.** The open screen, the page of the app and a screen's Override YAML are in the
  page's address now: a reload opens the same screen again, the browser's Back and Forward go through what you had
  open, and a link to a screen can be kept. Leaving a screen with unsaved changes by the address bar asks first, as the
  sidebar does. Older links such as `#settings` still work.

- **A plugin's README fits a phone.** A README with a table no longer made the plugin's details wider than the screen;
  the text wraps to the width of the phone and a wide table or code block scrolls on its own.
- **A tile added from Home Assistant no longer undoes a save made at the same moment.** An automation's tile event
  waits on Home Assistant for the entity's capabilities; a save from the editor during that wait is kept now, and the
  tile is placed on the new layout.
- **The Plugins tab says when a screen does not run a plugin.** A plugin the app built into a screen that the screen
  itself does not report, because it crashed at boot or the firmware on it was built without it, shows "Not running on
  the screen" instead of "Installed".
- **A plugin the firmware refuses by its API is named.** When a screen's update stops because a plugin was written for
  another plugin API, the message names that plugin and offers its update, as it already did for a compiler error.
- **The weather card and its chart agree on their colours.** A clear night, lightning with rain and snow with rain had
  another colour on the card's icon than in the chart beside it; every weather colour comes from one table now.
- **The overview opens fewer connections.** The small still screens on the overview take the normal refresh instead
  of a live stream each, so a home with many screens keeps connections free for the editor itself.
- **The compile cache is checked against GitHub's digest.** The prebuilt compile cache a build fetches is unpacked only
  when its checksum matches the one GitHub names for it.

- **Every file of the app is written whole or not at all.** The layouts, the settings, the plugins and now the Wi-Fi
  secrets of your screens too are written to a temporary file first and swapped in one step, so a power cut or a stop
  during a save never leaves half a file. A file the app cannot read is set aside beside the new one instead of being
  started over, and a file written by a newer version of the app is left exactly as it is.

- **A plugin's build no longer sees the app's own keys.** ESPHome runs a plugin's component while it builds a screen,
  inside this app. That build now gets only the environment the compilers read, never the token the app holds for Home
  Assistant or anything else of the app's own. The warning before you add a plugin now says where its code runs: on the
  screen, and its build in this app. The plugins repository checks a listed plugin's Python at every release it takes:
  ESPHome and a little of the standard library, files beside itself, nothing of the computer it is built on, and no
  secret or include of the screen's in its YAML.
- **The app comes back by itself, when you let it.** Turn on **Watchdog** on the app's Info page in Home Assistant:
  Home Assistant then starts Tessera again when it stops unexpectedly, and from this version also when it stops
  answering. A slip while the app adds new screens to Home Assistant or answers a picker on a screen is logged and the
  app goes on, instead of ending. A request the app could not read says so in the log as well, with where it went
  wrong, so a bug is not taken for bad input.

- **New clock faces for the screensaver.** On screens with 8 MB of flash or more, the screensaver's clock can now be
  Glass (a dial that is the glass itself, with ticks along its edge), Classic (a round watch dial with the day, the
  date, the temperature and your entities beside or under it) or Bauhaus (the whole glass a grid of colourful shapes
  with a round clock). Pick one under Screensaver, Clock, each shown as a small picture of your own screen, and choose
  its look (dark, light or the screen's own), the numbers on Glass and the seconds hand. Every face fills the glass on
  any screen shape, and none stands still: Glass and Classic shift a fraction every minute, and Bauhaus paints a new
  picture every ten minutes, so nothing marks the glass. The CYD and the other 4 MB screens keep the digital clock.
- **A plugin's card can show pictures (plugin API 0.13).** The card a plugin opens over the page, such as the details
  of an album or a film, can now show its cover or poster large, the same way the plugin's tile shows them. It comes
  as quickly as the cover on Tessera's own media card, and it is freed again when the card closes. Screens without the
  memory for pictures, such as the CYD, show the card without them.
- **Plugins can keep lists and send richer actions (plugin API 0.12).** A plugin tile's option can now hold several
  values: several artists, stops or calendars, each added from a list or found by typing a few letters, in the order you
  put them and dragged into another. The plugin asks its web service once per value and shows one list, newest first if
  it likes, and on a tap it can send Home Assistant an action with several fields of any kind (a text, a number, a list),
  such as playing an album through Music Assistant. Plugins written for an older API keep working as they are.
- **A screen update that a plugin stops says which plugin.** When a plugin doesn't build with the new firmware, the
  screen's update no longer ends in "Build or install failed" alone: it names the plugin and, when a newer version is
  on offer, asks you to update that plugin first and then the screen.
- **A Valetudo robot's map shows as a map.** A robot running Valetudo hands Home Assistant a placeholder that asks to
  install a Lovelace card, with the real map hidden inside it, so the vacuum card and a camera tile showed that
  placeholder. The app now reads the map out of it and draws the rooms, walls, path, zones, charger and robot, once
  for every map the robot sends.
- **A tile that grows shows more controls.** Drag a tile larger and it now gets the controls that fit its new size:
  a blind shows its position and its slats, a thermostat its temperature and mode keys, a light its brightness. A tip
  beside the tile lists every set that fits, so you can keep that one, pick another or choose none, and pointing at
  one shows it on the tile first. A set you chose yourself is kept and added to. "Don't show again" hides the tip;
  the inspector's Controls works as before.
- **A media player shows its volume and its playback keys together.** On a tile two rows high or larger, a player can
  now have both: the volume slider above previous, play/pause and next, as Home Assistant stacks them. Pick "Volume and
  previous, play/pause, next" under Controls, or drag a player's tile larger and it is suggested. A screen gets it after
  its next update; until then it shows the playback keys. On a tile wider than high the volume stands at the right,
  the whole height of the tile, with the keys at the left under the track.
- **A large player tile reads from across the room.** When a media player takes a big tile, on a 7- or 10-inch screen
  for example, the track's title now takes the largest text the screen has, its artist grows with it, and the keys and
  the volume grow up to half again their size. Smaller tiles look as they did.
- **The vacuum card shows the map, the rooms and the routines.** On every board with 8 MB of flash or more, a robot
  vacuum's card now shows its map, cleaned up and in the screen's own colours, with its state and battery above it.
  Tap rooms in the order you want and Start cleans just those (Home Assistant's clean by area), its own routines run
  with one tap, and suction and water stay one tap away. The card shows only what your robot offers and fits each
  screen: on a large screen everything is on the card, on a smaller one rooms, routines and suction open their own
  view. The keys follow what the robot can do, an error says why, and while it cleans you see the room and how far it
  is. The CYD and the other 4 MB boards keep the card they had.
- **Slats at their angle, and on more tiles.** A blind's tilt slider now shows its slats at the angle they stand at:
  flat when open, overlapping when closed, in a soft tint so the handle stays on top. With **Slat tilt** switched on, a
  cover tile lays out what its room holds: the position and the slats standing side by side, with open, stop and close
  under or beside them on a large tile, two bars on a low one, or one bar and a key that swaps it to the slats on the
  smallest. On the CYD and the 4.3-inch Waveshare the slats no longer drop off a 1x2 or 2x2 tile, and a cover with only
  tilt keys gets them as a second row.
- **Covers on 1x1 and 2x1 tiles.** On larger screens a cover's controls now fit a single tile too: a position bar, open,
  stop and close, or position and slats as two bars. A double-width tile takes the slats as well. Choose them under
  Controls in the editor; where a tile has no room for them, it looks as it did. This needs the new firmware.
- **Awnings and blinds without feedback keep their buttons.** A cover whose motor does not report whether it is open
  (many awnings, Somfy RTS and other radio motors) shows its state as unknown in Home Assistant. Its tile had no buttons
  on the screen then, although the editor showed them. Now open, stop and close work as they do in Home Assistant, and
  a cover that only assumes its state keeps both open and close at hand.
- **Cover groups, one cover at a time.** On every board with 8 MB of flash or more, the card of a cover group has a key at the top right, where a light group's
  lamps key stands. It opens a page with a card for every cover in the group: its position bar, or open, stop and close,
  and for a blind with slats a … key that opens its tilt.
- **Tap sound clicks as your finger lands.** With the Tap sound plugin the click now comes the moment a finger touches
  a tile, a key, a slider or a row of the settings, instead of after you let go. Dragging a slider, a cover's
  position or a player's seek bar clicks softly at every step, evenly spaced however fast you drag: every 5 %, or every
  position of a slider with only a few. A push that wakes a dimmed screen and a touch
  between the tiles stay silent. Plugins get this as `on_press` and `on_step` (plugin API 0.11).
- **A live camera's top bar goes with it.** On the ESP32-P4 boards the black bar with the back key and the camera's
  name now and then stayed over the page after the camera full screen closed, until a swipe drew the page again. A
  camera's pictures are no longer decoded while the screen draws, and once the camera's stream has ended the screen
  draws the whole page once more.
- **The Dock: swipe up for every page at once.** On every board with 8 MB of flash or more, a swipe up from the bottom
  edge now opens the Dock, a drawer with all pages as small pictures with their names, in two rows. It comes up with
  your finger and opens the rest of the way when you let go (pulled up only a little, it falls back). A tap on the
  page dots at the bottom opens it as well. Tap a page to go there, drag it down to close it, or swipe up once more to go home. The swipes need Swipe between pages, which stays off until you turn it on under the screen's
  settings. The CYD and the other 4 MB boards keep going home on that swipe and get none of its code, so their room
  for updates stays the same.
- **In the Dock, per page.** On a screen whose board has the Dock, a page's settings say how it stands there: its
  **Picture** (the default), an **Icon** of its own from the same icons as the tiles, or **Hidden**. A page left out of
  swiping is not in the Dock either.
- **The top bar's settings start from the bar itself.** At the head of its settings the editor draws the top bar as the
  screen does: the title on the left, every item, and a + to add one. Tap a part and only its settings show under it;
  the bar stays in view and shows each change on the item at once, also while you pick an icon. Drag an item left or
  right in the bar to move it, or pull it out of the bar to take it off, as an icon out of a menu bar; a right click on an
  item takes it off as well. The screensaver clock's row of entities works the same way. Many items go on more lines, and an item the screen leaves out for want of room is
  dashed in orange. Copying the bar to other pages is in the menu behind the three dots.
- **A right click in the editor.** On a tile it opens the tile and shows the same menu as the ··· in its settings:
  rename, show another entity, read its data, move it to another page, copy, cut and remove. On tiles chosen together
  it copies, cuts or removes them all, on an empty cell it adds a tile there or pastes there, and anywhere else on a
  page it shows the page's own menu. A finger held on a tile still drags it; on a touch screen the ··· is the way to
  the menu.
- **A page's settings start from the page.** A small page at the head shows its top bar, its tiles and, on a board with
  the Dock, its place in the Dock: tap the Dock for how the page stands there, or the top bar to set that up, and a
  back button takes you to the page again. Escape goes one step back at a time, and the settings have room between
  their groups instead of lines.
- **The screensaver's clock and a tile start from themselves too.** The clock's settings draw its row of entities at
  the head, white on black as the screensaver does: tap the clock for its temperature, an entity for how it shows, or +
  to add one, and drag an entity left or right to move it. A tile's settings show the tile itself at the head as its
  page draws it, with every change and the icon you point at. Its icons, the actions to perform and another entity now
  take the place of the settings under it instead of opening between them; Done or Escape goes back. Tap the tile's icon
  for its icons, or its name to rename it.
- **Two small fixes in the editor.** The screensaver's steps show their grip again when the pointer rests on one,
  instead of an empty square, and the rotation's four angles go under their name on a narrow card instead of running
  past its edge.
- **A new page asks what it needs.** The Add page window chooses the top bar with chips: the home key is on, and the
  clock and the screen's other items are a tap away instead of a clock on every new page. On a screen with the Dock it
  also asks how the page stands in the Dock: its picture, an icon, or hidden.
- **A wide tile's slider lines up with the tiles above it (#250).** On a tile three cells wide or more, a player's
  volume, a brightness or a -/+ took only the last cell at the right end, a short slider where the editor showed half
  the tile. The first cell now keeps the name, as on a tile of one cell, and the control fills every cell after it, on
  the screen and in the editor, so its edges stand where the tiles above and below have theirs. A tile two cells wide
  stays as it was. The screen needs this firmware.
- **Tab5: echo cancellation, and the microphone keeps listening while it plays.** Like the Waveshare P4 86 panel, the
  Tab5 now plays and listens at the same time, and takes the sound of its own speaker out of what the microphone hears.
  An Echo cancellation switch is under Extras and in Home Assistant. On both screens music now plays at 48 kHz, the
  echo cancellation works on the microphone at 16 kHz. The screen needs this firmware.
- **Editor: a long list of media players scrolls and has a search.** Adding a player to the screensaver opened a menu
  that ran off the window in a home with many players, and the ones below could not be reached. It now opens a search
  field with a list that scrolls, and typing narrows it by name or area. Every other menu of the editor scrolls when it
  is taller than the window, too.
- **An icon alone in the top bar opens its card (#252).** An entity in the top bar that shows only its icon now opens
  its card on a tap too, as it does when it shows its state. The screen needs firmware 0.56.0.
- **The power key on a player's card turns it off (#239).** On a media player's card, the power key in its top bar did
  nothing; the key on the tile worked. The screen needs this firmware.
- **A value on a tile's second line as Home Assistant writes it (#241).** A second line set to a value of the entity
  shows it as Home Assistant's own frontend does: a number with at most two decimals and its unit, so a humidity of
  61.60000000000001 shows as 61.6%, a lamp's brightness of 128 as 50%, a player's volume as 43% and a temperature
  with the system's unit; and a word or a yes or no in Home Assistant's own words ("Single" instead of single). The
  editor's preview shows exactly what the screen gets.
- **Tab5: twelve items in the top bar, and room for 256 tiles over 16 pages (#247).** The Tab5 has the PSRAM of the
  other ESP32-P4 screens but held six top bar items, 64 tiles and eight pages. The screen needs this firmware.
- **Tab5: the battery icon shows charging while it charges (#234).** The Tab5 showed its battery as charging while it
  ran from the pack, and as on battery while it charged: its battery monitor reads the charging current with the other
  sign. The screen needs this firmware.
- **A plugin tile keeps its entity of any domain (#254).** A plugin tile bound to an entity of a domain Tessera draws
  no tile for, such as a `plant.*` of Plant Monitor, now gets its entity id in `context.entity` too, so the plugin can
  ask Home Assistant about that entity. Before, it got the state and attributes but an empty entity id. A plugin's
  `tessera::action` works on such an entity too, as a `todo.add_item` on a to-do list.
- **A plugin added with a link stays on the screen after an update (#260).** Updating a plugin added with a link to a
  newer release built the screen without it, and its tiles showed "plugin missing" until it was removed and added
  again. The screen's build now takes the new release.

- **Waveshare P4 board audio and relays.** The relay-equipped 86 panel exposes its two outputs as Home Assistant
  switches, both off at boot. Extras adds microphone gain, automatic codec gain and live echo-cancellation on/off.
  Its AEC transport reuses the existing speaker, microphone and media-player interfaces; other boards keep their
  audio drivers. This is board support only: no assistant, AI provider or Ethernet support is added.
- **Extras and plugin settings update while open.** Changes made on the panel or in Home Assistant are pushed to the
  editor, including test-action status, without reopening the page or polling for settings.

## 0.4.88 (firmware 0.56.0)

- **A screen that runs well no longer shows an old failed update.** An update that failed (for instance because another
  build was running at that moment) no longer shows as an error with a red light once the screen runs the version it
  went for, installed another way or by a later update.
- **Editor: large screens get room.** A page of an 8- or 10-inch screen is drawn larger, as large as its glass up to
  what fits in the window, instead of the same size as a 4-inch one. A zoom in the corner below the pages makes every
  page larger or smaller (50 to 200 %; a click on the percentage goes back to 100 %), and the browser remembers it.
- **Editor: columns and rows are a screen setting.** The grid moved from the pages' toolbar to Screen settings, as the
  first card. A preview screen gets the Settings tab with just that card.
- **Editor on a phone: the sidebar is back.** A menu key on the overview, on a screen and on every other page opens the
  whole sidebar from the left: every screen with its details (update, rename, files, remove), Plugins, Alerts and
  Settings.
- **Editor on a phone: a page keeps its size.** Every page of a screen is now drawn at the full width of the phone.
  Before, a page took the width of what was on it, so one page stood a little wider or narrower than the next.
- **Editor: choose several tiles, and copy them to another page or screen.** ⌘ (or Ctrl) or Shift with a click adds
  a tile to the choice, and a band dragged with the mouse from beside the tiles chooses every tile it touches; ⌘A
  chooses the whole page. ⌘C copies the tiles with every setting, ⌘X cuts them and ⌘V pastes them on the chosen page
  (at the empty cell marked on it, if there is one), on this screen or another one. The group keeps its arrangement
  where it fits; what the page has no room for goes on new pages right after it, so tiles from a large screen spread
  over the pages of a smaller one, each in the largest size that screen has for it. Delete removes them all, and undo
  brings back a paste, a cut or a removal in one step.
- **Editor: dragging a tile works on Android.** In Chrome on Android (also in the Home Assistant app) a tile carried
  over another one went back to its place halfway, because the page began to scroll under the finger. Holding a tile
  also no longer selects text or opens the browser's menu.
- **Screens keep taking new layouts.** On a screen that keeps its pages (every board with PSRAM), a layout that added or
  took away a page left what the old cards had drawn behind in the memory inside the chip. After a few such changes a
  4-inch Guition refused new layouts until it was restarted, or lost Wi-Fi. That memory now comes back with every
  layout, and the points a card draws its lines through live in PSRAM.
- **Screens with plugin tiles stay up.** A plugin tile's options and data, and the buffers a picture is downloaded
  with, now live in the screen's PSRAM instead of the small memory inside the chip that Wi-Fi needs. On a 4-inch
  Guition with a few plugin tiles and pictures that memory could run out at a busy moment: the screen restarted, or lost
  Wi-Fi until it was restarted.
- **One line for every build: nothing is refused because something else builds.** The app builds one firmware at a
  time, and an update, a plugin build, New screen and Firmware & USB now all wait their turn in the same line. Update on
  a second screen while the first one updates waits its turn (before, it showed a 2 and fell back). Update all adds
  the screens that are not on their way yet. New screen, Firmware & USB and the YAML check go before the updates and
  plugin builds that wait, and say what they wait for. A plugin added while the screen's update waits comes with that
  update in one build. An update on a board with 4 MB keeps the line until all of its steps are done, so no other build
  starts while its screen restarts. Each build keeps how it ended and its log, so the editor says the right outcome
  also when the next build started at once.
- **The dev app says it is the dev app, and reinstalls every screen from dev in one go.** Added from the `#dev`
  repository, the app shows a small dev chip beside its name, Reinstall from dev stands in each screen's details under
  its firmware, and Settings, Updates has Reinstall all from dev, which builds every screen with the newest dev, one
  after the other.
- **Editor: a map tile grown to two rows saves at once.** Dragging a new map tile (or an energy card) from one row to
  two gave it a setting the app does not keep for it, and the save asked to adjust the tile's settings first.
- **Plugin API 0.10: pictures on a plugin's tile.** A plugin can lay out places for pictures on its tile and name an
  address for each (a film's poster beside its title), and the screen shows them the way it shows a camera tile or an
  album cover: the app fetches each picture once, from a host the plugin's manifest names or from Home Assistant's own
  pictures of the tile's entity, cuts or fits it to its place and sends all the places of a tile as one picture. The
  manifest says how many places a tile has (`pictures`). A board without the memory for pictures shows the tile
  without them. Also a label of several lines for a plugin's tile, and where a finger tapped a tile, so a list or a
  row of posters knows which one. The places of a tile may overlap, and a picture can be turned in perspective and
  get a reflection under it, drawn by the app, so a plugin can make a cover flow. The plugins repository's docs say how.
- **Live camera on the P4 boards: the panel keeps up, and a live tile never stays where its card was.** The PPA, which
  scales and turns every live picture and, on a turned glass, every flush of LVGL, moves in bursts of 64 bytes instead
  of 128, so the panel's own DMA gets its turn on the memory bus; a frame of blue (the panel's colour for no data, seen
  on the Guition 10.1-inch P4 while a camera streamed) is what it showed when it did not. The screen counts how often
  the panel ran dry and writes it in every stream report, so a log tells whether it still happens. LVGL and the streams
  take turns on the glass (LVGL for a whole refresh, a stream for a copy), so a tile's name no longer stands over its
  live picture after the camera full screen closes. A live tile whose card moved on the glass stops at once and asks
  again from where the card is.
- **Meters for sensors.** A sensor tile can show where its value stands as a ring, a tape or a bar of cells, on any size
  from one cell to the whole page, growing with the room it gets. The range comes from Home Assistant (0 to 100 for a
  percentage) or is the tile's own, and the colour is one, or two or three segments (green, orange and red by default)
  up to thresholds in the sensor's own unit, each colour and threshold yours to change. Choose Meter under Display. The
  screen needs this firmware.
- **Decimals the way Home Assistant does them.** A sensor's tile and its top bar item have Home Assistant's own Display
  precision: Default, or 0 to 6 decimals, each shown with the sensor's value now. It is Home Assistant's setting for the
  sensor, so choosing it in the editor changes it in Home Assistant too, and every tile, meter, top bar item and
  dashboard follows.
- **Durations in hours and minutes.** A duration sensor in minutes, hours or days shows as Home Assistant shows it:
  "1h 30m" instead of "1.50 h" and "12m" instead of "0.20 h", in the screen's language, on tiles, meters, cards and the
  top bar (wishlist 107).
- **An entity in the top bar opens its card.** A tap on an entity's item in the top bar opens the card that holding its
  tile opens, and does nothing else: a switch or a lamp there opens its card instead of switching, a sensor its
  history. It works whether or not the entity also has a tile, and the screen needs this firmware.
- **The colour card follows the light while it is open.** A light's colour, white shade or brightness changed elsewhere
  (in Home Assistant, by an automation, on another screen) now moves its sliders at once, and a colour or white shade
  you set shows on the light's tile straight away. The brightness slider sends what the tile's own slider sends. The
  screen needs this firmware.
- **More room on the CYD and the other 4 MB screens.** Their icons are stored with four shades of edge instead of
  sixteen, which frees about 80 KB of their firmware for plugins and later features. The icons look the same at the
  size these screens draw them. Larger screens keep the finer icons. The screen needs this firmware.
- **Plugins have pictures.** A plugin whose maker added one shows a picture across the top of its card on the Plugins
  page and large above its details: the plugin on a few screens, with its name and what it does. Makers make one with
  the plugins repository's new `tools/store_image.py`, from the real firmware of the bench.
- **A dark screen saves power.** In standby or Sleep at brightness 0 the screen stops drawing and lets its Wi-Fi doze
  between the router's beacons, so a screen on a battery lasts longer. It stays connected: Home Assistant still sees it
  and can wake it, alerts still arrive, and a tap wakes it as before. Waking fades the light in over 200 ms instead of
  switching it on at once. The screen needs this firmware.
- **A calendar card.** Put a Home Assistant calendar on a screen, or several calendars on one card in Home Assistant's
  own colours. The card shows more as it gets bigger: what is on now in one cell, the next event large on a bigger tile,
  then a list of what follows, and on a large screen the whole week. A tap opens the full screen with the day, the week,
  the month and every event's details, and on large screens the hours scroll. Filter by calendar, by place (one meeting
  room), by words in the title, all-day and tentative events, or show only Free, Starts soon and Busy with the titles
  hidden. "Status and booking" turns a card into a meeting room's sign: Free or Busy in large letters in green or red,
  until when, the room's day beside it on a large card, and keys that book the room now (15 min, 30 min, 1 h or until
  the next meeting) in a calendar that takes new events, with the place and title you choose. A week can start on
  Monday, show fixed hours (8 to 18) and the month its week numbers; the full screen shows or hides each calendar from
  its view key. The screen needs this firmware.
- **A new board, experimental: the Elecrow CrowPanel Advanced 10.1-inch ESP32-P4** (V1.1 and V1.2), 1024 x 600 glass
  with GT911 touch, a dimmable backlight, and its speaker and microphone as the screen's audio, so audio plugins such as
  a voice assistant fit it. Built from Elecrow's own ESPHome example and a configuration a community member ran on the
  board (#116). Choose it under New screen.
- **Plugin API 0.9: large digits and colours by meaning for plugins.** A plugin's tile can show its numbers in the large
  digits Tessera's own climate card uses for its setpoint, so a count or a reading fills a large tile. It costs no
  flash: the font is already on every screen, and a value with letters in it stays in the plugin's usual size. Bars and
  dots of a plugin take the same green, amber and red as Home Assistant, in light and dark, for a level that is good,
  moderate or bad. A plugin's one-line text now stays on one line and ends in dots on a narrow tile, instead of running
  under it. A plugin that uses the new parts needs this firmware.
- **Bluetooth for plugins on every ESP32-P4 screen.** The app now knows which screens can run Bluetooth beside the
  screen: every board with an ESP32-P4, whose ESP32-C6 does Wi-Fi and Bluetooth. A plugin that needs it, such as the
  new Bluetooth proxy plugin for Home Assistant, is offered only on those screens. ESP32-S3 screens with an RGB panel
  are left out: they lack the memory for it.
- **reTerminal D1001: touch works after a flat battery.** When the screen started from no power at all (an empty
  battery, or the first time it is switched on), it showed its pages but did not react to a finger until it was
  restarted. The touch now starts after the panel has its power. The screen needs this firmware.
- **reTerminal D1001: no false battery level while it charges.** Plugged in, the level jumped up by as much as 20 %,
  because a charging battery reads higher than it holds, and fell back after unplugging. Now the top bar shows only the
  charging bolt while it charges, without a number, and the level comes back two minutes after unplugging, once the
  battery has settled. On the battery it only goes down. On any screen, charging without a known level now shows the
  charging bolt instead of an unknown battery. The screen needs this firmware.
- **Going back.** A layout with a calendar card or a meter can't be read by an older app, so after this update go back
  to 0.4.87 only with a backup taken before it.
- Checked with every Python, C++, editor, translation and WASM preview check, the layout audit of every card on every
  board shape, and firmware builds of every board on ESPHome 2026.9.0 and, where the board allows it, 2026.6.2. The
  upgrade from 0.4.87 was tested on a CYD, a 4-inch Guition and a Waveshare 4.3-inch: main's app and firmware first, the
  new app with the old firmware, then each screen's own Update built from GitHub, and on the CYD the other order (the
  old app with the new firmware). Every layout came through byte for byte, and pages, taps, cards, settings, standby and
  the wake were checked on the glass. After the upgrade the screens got calendar cards, meters and a plugin with
  pictures, built through the one build line, and were checked on the glass again.
## 0.4.87 (firmware 0.55.0)

- **Plugins for everyone.** The Plugins page is now in every Tessera app, not only the dev app: add a tile, a top bar
  item or a function made by Tessera or the community to a screen, pick several and build once, and make your own.
  Plugins are pinned to the exact version you added, a build that fails changes nothing on the screen, and a screen
  without plugins builds and runs as before.
- **Two new boards, experimental.** The Guition JC8048W550C_I, a 5-inch ESP32-S3 with 800 x 480 RGB glass and GT911
  touch, by [@BSkando](https://github.com/BSkando) (#230), and the Guition JC4880P443, a 4.3-inch ESP32-P4 with
  MIPI-DSI glass and GT911 touch, by [@pmarki](https://github.com/pmarki) (#200). Both were tried on the glass by
  the people who added them, and both dim. Choose them under New screen.
- **Waveshare ESP32-P4 86 panel: no flicker, and readable at its lowest brightness.** The backlight runs at 200 Hz
  instead of 100, which took away a flicker in grey areas, and its lowest level is 15 %, where the glass is still
  readable; standby still turns it fully dark. Found and tried by [@arjanmels](https://github.com/arjanmels) (#209).
- **The screensaver no longer stands black over a cover that doesn't come.** When a player plays but its cover can't
  be fetched (an error from the address, or a picture of `none`), the screensaver shows its next step, the camera or
  the clock, instead of a black glass, and the music comes back as soon as the cover does or the next track starts. A
  change that the screen may have missed in a slow moment is sent again, so the clock no longer stays away after one
  (#229).
- **M5Stack Tab5: the speaker and the voice assistant.** The Tab5 turns on the output its speaker is connected to,
  so spoken answers, announcements and sounds can be heard; its microphones are amplified before the converter and
  read on the channel that working Tab5 voice setups use, and its speaker buffers half a second, so an answer plays
  without gaps.
- **A camera live, full screen, on the P4 boards.** On the reTerminal D1001, the M5Stack Tab5, the Waveshare ESP32-P4
  panel and the Guition P4 boards, a camera tapped open full screen plays live at the camera's own pace, instead of a
  new still every four seconds: 8 pictures a second from a camera's low-resolution stream, 15 from a 1080p one, about a
  tenth of a second behind the camera, with touch as quick as ever. The app takes the camera through Home Assistant's
  own WebRTC and sends the screen JPEGs no larger than the camera's own; the screen's hardware decodes, scales and turns
  them. A camera without a stream sends its snapshots as fast as it gives them. On a Raspberry Pi, give the tile the
  camera's low-resolution stream: decoding is what costs Home Assistant's host, and it costs what the resolution costs.
  Every other board keeps its stills.
- **Live camera tiles on the P4 boards.** A camera tile's picture has a new pace there, Live, which is its default: the
  tile plays the camera on the page, with its rounded corners and its name over the picture, as long as the page is on
  the glass and nothing lies over it. Opening such a camera full screen shows its first picture at once. Other screens
  keep their paces in seconds.
- **Camera sound on the P4 boards with a speaker.** The camera full screen plays the camera's sound, through the
  screen's speaker at the volume under Extras, with a key in its top bar that mutes it.
- **P4 boards download faster.** Camera pictures, album covers and maps come about three times as fast on the P4
  boards: their Wi-Fi goes through an ESP32-C6, and a larger network window keeps it busy.
- **Plugin cards and tiles.** A card a plugin opens shows everything it draws under its top bar, not only the first line
  (#226), and a plugin's tile grows to a tall size in Layout and saves (#224).
- **Plugins: one build for every change, and a failed build changes nothing.** Taking a plugin off goes into the same
  card in the corner as adding one, with what goes along with it, so a screen that gains one plugin and loses another
  builds once. A build that fails leaves the screen as it was: a new plugin stays listed as failed with the reason, out of
  the screen's YAML, and a failed update goes back to the version that worked and says which one did not build, so the
  screen's next update never fails on it. A change made while the screen builds is no longer lost, a screen the app
  cannot reach yet says so before anything changes, Build again on a test branch takes its newest commit at once, and a
  key a plugin asks for per screen is hidden as you type and shows when it is set. A plugin written for an older plugin
  API than the core's last change of a name now says so when it builds, instead of failing in the compiler.
- **The editor asks in its own look.** Before something that can't be taken back (leaving unsaved changes, replacing a
  layout, starting the calibration, clearing an override), for a new name on a phone, and for a text to copy by hand,
  the editor now asks in a dialog of its own, light or dark and at the bottom of a phone, instead of the browser's, in
  the same words. Its button says what it does (Discard and open, Replace layout, Start calibration, Clear override),
  in red where it throws something away. Cancel has the focus at first, so Enter alone never throws work away, and
  Escape cancels.
- **Your work survives a reload.** Unsaved changes in Layout are kept in this browser as you make them. Close the tab,
  reload or lose the browser, and opening the screen again says "Unsaved changes from 10:42" with Restore and Discard.
  Changes made before someone else saved the screen come back through the usual question (Reload saved or Keep mine),
  so a newer save is never written over unasked. Saving or discarding forgets them; preview screens need none of this.
- **A second tab knows.** When another tab of the same browser has unsaved changes to the screen you have open, Layout
  says so before anyone saves, with Take over here (its changes come to this tab, and Undo takes them back) and Keep
  mine. A tab that closes stops counting.
- **The connection is visible.** While ESP Screen Manager can't be reached (it restarts or updates), a calm line over
  the page says so and that your changes stay; when it is back the line says "Connection restored" and goes. The editor
  follows it again at once, and nothing is asked while the tab is hidden, the screen preview included.
- **A tile's name is easy to find.** A tile's settings start with "Name on the screen", Home Assistant's name in grey
  and a key back to it once you typed another. Click the tile's title in its settings, choose Rename in its menu, or
  double-click its name on the mockup to get there; a page's menu has Rename too, as does a double click on its title.
- **Undo says what it does.** Undo and Redo in Layout name the step they take back or do again ("Undo: Kitchen light
  moved to page 2"), and after an undo a short note says what came back, with Redo beside it, so a change on a page out
  of sight never goes unnoticed.
- **A favourite says what it plays in Layout.** Its card on the mockup names the kind of thing again (Playlist, Album,
  Podcast) before the speaker, as the screen does.
- **Seeed reTerminal D1001 (experimental).** The 8-inch ESP32-P4 panel with a battery, as a new board in New screen:
  touch, a dimmable backlight, Wi-Fi through its ESP32-C6, the battery in the top bar, the button on top for standby,
  the RGB LED, a clock that keeps the time while Home Assistant is away, its speaker and microphones, and its camera
  for the Screen camera plugin, which makes it a camera in Home Assistant. Its SD card and LTE are not configured yet.
- **A screen with a speaker is a media player in Home Assistant.** On a board whose speaker Tessera configures (the
  reTerminal D1001, the Waveshare ESP32-P4 86 panel and the M5Stack Tab5), Home Assistant's text to speech and
  announcements play on the screen, without a voice assistant. Its volume is under Extras, on the screen and in Screen
  settings, and no sound starts with a pop. On the Waveshare panel and the Tab5, whose microphone and speaker share one
  bus, the microphone pauses while something plays; the P4 audio plugin is no longer needed. The Tab5's camera works
  with the Screen camera plugin as well. Both are built but still to be tried on those boards.
- **Extras: settings a board has of its own.** A screen whose board has something the others do not shows it under
  Screen settings in an Extras card, on the screen's own settings page under Extras, and in Home Assistant, all the same
  switch. On the reTerminal D1001: Microphone, and Wake when moved, which wakes the screen from standby when someone picks
  it up or moves it.
- **Find plugins by what they are.** The Plugins page has tabs for tiles, functions for the whole screen, and hardware,
  with topics such as Time, Weather or On the move under them, and what fits none of your screens folded away. Give a
  plugin you use a heart, and see which plugins others like. A plugin that needs another one, or needs a speaker or a
  microphone, brings what it needs along in the same build, shown before you add it; removing a plugin another one needs
  asks first. Plugins are pinned to the exact commit they were added at, and a plugin from a fork never gets the key you
  filled in for the original. Plugin API 0.7.
- **Plugin items in the top bar in colour.** A plugin's item lights up when it matters: a microphone in blue while a
  voice assistant listens, amber while it thinks, a camera in red while it streams. Choose Show, Icon only, to keep the
  top bar to icons. A microphone joins the icons for tiles. Plugin API 0.8, which also knows a screen's camera, and
  lets a plugin play sounds of its own (Tap sound: a soft tick on every tap).

- **All of a plugin's settings in one place.** Open a plugin in a screen's Plugins tab and its settings are there, in
  three groups: what takes effect on this screen at once, what is filled in once for every screen, and what builds the
  screen again, with a "Save and build" key that lights up only when something changed. Plugins can now add a text
  field and a button that runs a test and shows how it went ("Heard: Okay Nabu"), and a setting keeps working when you
  rename its entity in Home Assistant. Screen settings links to each plugin's settings. Plugin API 0.6.

- **One top bar and one pager on every page.** Every page a tap opens (a card, a light's effects, a light group, the
  media library and its folders, the settings page, a plugin's card, a camera) now has the same top bar: the back key
  stands in the same place on all of them, at the corner of the glass, so it no longer moves a little each time you go a
  page deeper or back. Every list that takes more than one page (settings, a light group, the media library and its
  speaker menu, a select's options) now has the pager of the tile pages: a chevron in
  each half, the dots between them, always across the foot of the glass.
- **A new weather card.** A weather tile shows the coming week as day columns in a light grid: each day's name, its
  icon, the high and the low, and on a bigger tile the temperature as a line through the week and the rain as bars with
  the amount and the chance under them. The bigger the tile, the more it shows; a tile of one row keeps the weather now
  beside the days. A tap opens the card as Home Assistant's own dialog has it: the weather now with today's high and
  low and feels like, humidity, wind with its direction, air pressure and visibility, and the forecast with a Daily |
  Hourly key for the next 48 hours. Up to seven days instead of five; the words are Home Assistant's in every language.
- **The preview speaks your screens' language and follows Dark mode.** The live preview in the editor, on the home page
  and under Preview, now shows the firmware's own texts in the language chosen under Settings -> Language & region, and
  draws a screen that has Dark mode on in its dark look, as its glass does. Before, it was always English and light.
- **Holding a light with a colour opens its colour card in the preview too** (#201). The colour card was the last card
  built in the screen's YAML instead of the firmware's shared code, so the editor's preview could not show it: a hold
  on such a light did nothing there. It is now part of the shared code, with every card's top bar, and the preview opens
  it, its effects and a group's lamps as the screen does. On the screen it looks and works as before, and the CYD's
  firmware is 6.7 KB smaller.
- **The preview shows screens with more than eight pages.** A screen with more pages or tiles than the eight pages and
  64 tiles every screen once had, which a board with PSRAM takes, showed a drawing instead of its live preview. The
  preview now takes as many as the largest board.
- **Pick several plugins, build once.** Adding a plugin no longer builds the screen at once: the round + on a plugin card
  (or Add in its details) sets it aside in Ready to install, a card in the corner. Add more, on this screen or another,
  then press Install: each screen builds once with all of them. The card says what a plugin still needs, asks once to
  trust the makers of community plugins, and on a 4 MB screen shows the room they take together.
- **Make a plugin of your own.** The Plugins page explains it in three steps: start from the template, try it on your
  screen with a link to your repository, and list it in the community so it shows up for everyone, straight from your
  repository.
- **Plugins get a whole day of prices or a forecast.** A plugin tile of an entity now gets every value of a list, not
  the first 16: two days of electricity prices per quarter of an hour arrive whole. A plugin can take one list of
  numbers out of a list of objects (ENTSO-e, Frank Energie, Zonneplan, Octopus, Solcast, Amber) and out of the answer of
  an action (Nord Pool, EnergyZero, easyEnergy, Tibber, a weather forecast), and can ask that the entity list in the
  editor shows only the entities that have the attributes it needs, the price sensor instead of every sensor in the
  house. Plugin API 0.5.
- **Builds you can follow from anywhere.** A screen that builds shows a ring on its row in the sidebar and on its card
  in the overview that fills as it goes, and one ring at the top of the sidebar lists every build on its way with its
  step. When a build the page saw ends, whatever page is open says "Living room is ready", or that it failed, with the
  way to its log.
- **Tiles whose entity is gone are found.** The overview says calmly how many tiles show an entity Home Assistant no
  longer has, or one it has had no word from for more than a few minutes, and on which screens; the sidebar marks each
  screen and lists them. A click opens that tile with a list of entities ready to choose another, those of the same
  kind and with the closest names first. A tile's menu offers Show another entity for any tile.
- **⌘K can do everything.** The search finds a screen's settings on every screen with their value ("brightness" opens
  it on its screen and marks it), the tiles that show an entity on whichever screen they stand, the plugins (open one,
  add it to this screen), and identifies or updates a screen by its name; updating every screen asks first. What was
  chosen last comes first, the arrow keys walk the rows, and the row in focus says what Enter does.

## 0.4.86 (firmware 0.54.0)

A hotfix for 0.4.85: two fixes for screens that broke on firmware 0.53.0, nothing else.

- **Dark mode no longer restarts a screen with many tiles (GitHub #227).** Turning Dark mode on or off restyled every
  part of every card on every page, the pages kept off the glass included, and on a large grid with several pages that
  took longer than the screen's watchdog allows: the screen froze, started again and came back light. Only colours
  change, so the screen now fills in its new colours and draws itself again once. Tested on the 4-inch Guition, the
  Waveshare 4.3 and the CYD: a switch went from 2.9 to 0.3 seconds on the Guition with nine pages and from 1.8 to 0.3
  on the Waveshare, and the Guition after a switch matched, pixel for pixel, the same screen started in that look.
- **Room for tiles on the Waveshare 7B (GitHub #207).** Its drawing buffer took 154 KB of the memory inside the chip,
  which left about 17 KB for Wi-Fi, the connection to Home Assistant and the tiles: room for about four of them. The
  buffer now lives in PSRAM, as on the larger boards. With the buffer there, owners of this board measured more than
  150 KB free inside the chip.

## 0.4.85 (firmware 0.53.0)

- **Your screens build the firmware of the Tessera you have.** A screen now always gets the firmware that belongs to
  the Tessera app you installed, also when its update starts from Home Assistant's firmware update or from ESPHome
  Device Builder. Before, every build took the newest firmware on GitHub, so a screen could run firmware that an older
  app did not know. New firmware now comes with an update of the app: update Tessera first, then it offers each screen
  its Update. When it starts, Tessera writes its release into every screen's YAML in the ESPHome folder (the `ref:` of
  the display package and `GITHUB_REF`). A `ref:` other than main, dev or a Tessera release, one you chose yourself,
  stays as it is.
- **Choose a screen's columns and rows in the editor.** Beside the pages, the grid button shows the screen's columns and
  rows and changes them, from one by one up to as many as its glass holds, without a new build. The layout follows at
  once: tiles that no longer fit on a page move on to a new page right after it, and none is ever dropped. The screen
  gets its new grid with the next save, under its loading screen, and keeps it. A change made while the screen is offline
  waits for it. Needs this firmware on the screen; an Override YAML can widen the range (`GRID_MAX_ROWS` and more).
- **Stand a screen up or lay it down in the editor.** On a screen whose glass is not square, the grid button also offers
  Landscape and Portrait. The layout goes on that way's grid at once, and with the next save the screen turns, starts
  again once and comes back the other way round, without a new build.
- **New screen starts on the best grid.** A new screen gets the grid that suits its glass best, lying down. Under
  Advanced you can choose other columns and rows, and on glass that is not square standing up; the editor changes both
  later. The separate rows question on the 4-inch Guition, the Tab5 and the 10.1-inch Guition is gone.
- **A sidebar you can fold and resize.** Drag the sidebar's edge to make it wider or narrower (double-click resets it),
  or fold it to its icons with the button beside the logo; drag it very narrow and it folds by itself. Folded, every
  screen and button says what it is when you point at it, and a screen name that is cut short shows in full the same
  way. The editor remembers the width in this browser.
- **A save shows a loading screen, then the new layout.** When you save in the editor, the screen now covers itself
  with the loading screen while the new tiles arrive and its pages are prepared, and then shows the finished layout in
  one step. Before, the new tiles appeared one by one over the loading text and the page flickered.
- **Every build shows, wherever you look.** Whatever is building a screen, an update or an install from Firmware &
  USB, now turns in the list of screens and shows its progress in Settings, Updates, with the build log one
  click away. A build that failed keeps its log until the next one, so you can read why. Copying the installer's log
  no longer says an API key was copied.
- **Plugins, in the dev app only.** The dev app (the repository URL with `#dev`) now has a Plugins page: a plugin adds a
  tile or a feature to the screens you choose, and each screen builds once with it. The first ones are Public transport
  (NL) and a waste collection calendar, marked as examples, and the speaker and microphone of the Waveshare P4 86 panel,
  in beta. Plugins live in github.com/MaxGramser/tessera-plugins, with a template and docs to make your own. The stable
  app shows nothing of them while the plugin API is 0.x (docs/PLUGINS.md).
- **Bus and train icons** for any tile.
- **A screen that waits for its tiles to be adapted to a new grid says so.** The editor showed "Error: invalid
  message" for it, because its screensaver was sent before the screen had a layout; now the status keeps saying that
  the grid changed and the positions need a look.
- **Waveshare ESP32-P4-86-Panel-ETH-2RO (experimental).** The 4-inch 720 × 720 wall panel on an ESP32-P4, with GT911
  touch, a dimmable backlight and Wi-Fi through its ESP32-C6, as a new board in New screen. Its relays, Ethernet and
  audio are not configured. New screen now gives a board with another chip or resolution its own card, so this one
  stands apart from the Waveshare 4B. Thanks to @woozer, who made it work on the panel
  ([#142](https://github.com/MaxGramser/homeassistant_espscreen/pull/142)).
- **Room on the 4 MB boards.** The bedside clock on a Hosyond 4-inch draws its time with the large digits the screen
  already has, a little smaller than before, which frees about 40 KB of its nearly full flash. The CYD already did so.
- **The energy card adds up, and always shows the battery's charge.** What no device measures now has a grey circle
  of its own, Untracked, after the devices and Other, as Home Assistant's live power view shows it, so the
  devices add up to the house. A device that uses very little now counts in Other instead of disappearing. The battery's
  charge stands beside its icon, as in Home Assistant's own card, on every size of the card; before, only large cards
  showed it. The names stand centred under their circles, also at the sides of the card. Needs this firmware on the
  screen.
- **A calmer energy card, if you like.** The energy card's new Flow choice in the editor keeps the moving dots, or shows
  lines and arrows instead: a line grows thicker as more power flows and an arrow in its middle shows which way it
  goes, with nothing moving. Needs this firmware on the screen; until then the screen keeps the dots.
- **Going back.** A layout that uses the energy card's new Flow choice can't be read by an older app, so after this
  update go back to 0.4.84 only with a backup taken before it.
- Checked with every Python, C++, editor, translation and WASM preview check, and rendered from the real firmware on
  the CYD, the 4-inch Guition and the 10.1-inch Guition. Firmware builds of every board on ESPHome 2026.9.0 and, where
  the board allows it, 2026.6.2: the CYD uses 91.8 % of its slot (93.6 % on 2026.6.2), the Hosyond 4-inch 92.5 %
  (94.4 %). The upgrade from 0.4.84 was tested on a CYD, a 4-inch Guition built with four rows and a Waveshare 4.3-inch:
  the new app with the old firmware, then each screen's own Update, and on the CYD the other order (the old app
  installing the new firmware). Every layout came through unchanged, edits saved in between reached the screens, the
  four-row Guition kept its four rows, and pages, taps, cards and standby were checked on the glass. A build from a
  screen YAML pinned to a release tag made exactly that release's firmware.

## 0.4.84 (firmware 0.52.0)

- **Zoom and move a map full screen.** A map opened full screen has round + and - keys at the bottom right, like the
  volume keys, and four arrows at the bottom left that move it about a centimetre each. The map follows at once and
  sharpens when the new picture comes, with a small spinner at the top right while it is on its way. The keys are
  dark in the light look and light in the dark, and let the map show through a little. Behind a map that is still on
  its way is the page's own colour, not black.
- **Every page turns as quickly as the next.** A screen with PSRAM now keeps every page of its layout ready, not only
  seven, so paging through a long layout no longer feels quick on one page and slow on the next. Opening a new layout
  for the first time takes a little longer, while the screen prepares every page.
- **Every picture on a page at its tile's full size (GitHub #183).** A camera, an album cover, a favourite and a map
  each load their own picture now, at their own pace. Before, the pictures of a page came as one image, so on a large
  screen every picture of the page came smaller with a dark edge as soon as a player on that page started to play, and
  every new song sent all the cameras of the page again. Now a new song replaces only its cover, and a page with
  several cameras shows each one at the full size of its tile. A camera's picture is also newer: the app fetches it
  just before the screen loads it, so it is a fraction of a second old instead of up to twice the refresh time you
  chose. The 10-inch and the other screens with 32 MB of memory also show a camera over the whole page, the camera
  full screen and the screensaver at the glass's own pixels, no longer a little smaller in the middle.
- **Try dev before a release (GitHub #180).** Add the repository with `#dev` at the end of its URL and the store
  offers a second Tessera that builds every screen from dev, with a Reinstall from dev button for each screen.
  docs/RELEASING.md, "Testing dev", says how it works and how to go back. The stable app is unchanged.
- **A Spotify link makes a favourite.** Paste a link from the Spotify app (Share > Copy link) under the library in a
  favourite's picker and it becomes a favourite like any other, with its cover and name. That reaches what Home
  Assistant's library never lists, such as Discover Weekly, Release Radar and the Daily Mixes. It works on a Spotify
  player and on a speaker whose library lists your Spotify account, such as a Sonos.
- **A favourite sets its own shuffle and repeat.** Next to its speaker, a favourite can turn shuffle on or off and set
  repeat as it starts, or leave the player as it is. With shuffle on it skips once, because Spotify always begins a
  playlist or album at its first song, so the first song you hear is a shuffled one.
- **The ring of a favourite that plays sits on the tile.** It was a wider border, which moved the inside of the tile,
  so its picture slid a few pixels out past the ring and the tile looked to grow. The ring is now drawn over the
  tile's picture, and nothing moves.
- **Choosing what a favourite plays works again.** The editor refused every choice with "Invalid or unsupported page
  settings", so a new favourite could not be saved. It also no longer offers a small slider or a tap action on a
  favourite, which the app drops anyway.
- **A slider you can see on a lamp that is off.** An off light or fan shows only the grey track on its tile, so a
  finger dragging it moved nothing you could see until you let go. Now a faint fill and handle in the tile's colour
  follow the finger, and letting go turns the lamp on at that level as before.
- **A picture on a tile in the editor keeps its rounded bottom corners.** The shade under a camera or favourite name
  had an invalid corner rule, and some browsers let a picture overflow the tile's corners.
- **A new track without a flash on the media card** ([#177](https://github.com/MaxGramser/homeassistant_espscreen/issues/177)).
  The card changes its words and its bar at once, and its cover and colour together, in one go, once the new cover is
  here. Until then it keeps the cover and colour of the track before. Before, the card was drawn again on a black
  ground with an empty square, and once more when the new colour came, so the keys and the bar flashed and the cover
  was gone for a second or two. A media tile over a whole page keeps its cover the same way.
- **Live radio says Live.** A station plays without a length, so the card had no bar for it. Now the bar stays, empty,
  with "Live" where the time stands, as Music Assistant keeps its bar for a station. Between two tracks the bar stands
  at nought with 0:00 at both ends, where it went and came back.
- **Covers keep coming after many tracks.** Each track's cover stayed in the screen's picture memory, and after some
  sixteen of them there was no place left for a new picture: the media card stood on its empty square, and a camera or a
  library page could not keep its picture either. A cover the card or a tile has moved on from now goes, and when every
  place is taken the picture used longest ago that is not on the glass makes way.
- **One way for every picture.** The camera full screen, the screensaver, an alert's picture, the media card's cover,
  a player's library, the page's covers and cameras, and the covers fetched ahead for other pages now all go one way:
  each says what it wants to see, and one part of the screen decides what loads, in what order, and when to stop.
  What is on the glass loads first, an alert before everything; a picture nobody wants any more stops loading at
  once, so turning pages fast or closing a card before its picture came leaves nothing behind. Whether a picture is
  there is read from the screen's picture memory every time, so a picture that had to make room is fetched again
  right away instead of waited for. Pictures nobody will show again (the cover of a track that ended, the last frame
  of a closed camera) go once they are off the glass.
- **Air around the knobs.** The volume knob at 0 or 100 % no longer touches the volume keys beside it, and the knob of
  the track's bar keeps clear of the times.
- **The play key's triangle stands in the middle** of its key, where it sat a few pixels to the left.
- The card stands on one colour from its cover. The app has sent one colour since the bands of #135; the card's code
  for a colour at the top and another at the bottom is gone.
- **The energy card shows the grid on Home Assistant 2025.12 to 2026.2.** Those versions keep a grid's power sensor in
  a list of its own, which the card did not read, so the grid was missing (discussion #104). It now adds them up as
  Home Assistant's own live view did then.
- **A tap on solar or the grid with more than one sensor opens their sum** (#180). Two solar arrays or two grid
  connections had no single sensor to open. The card now opens the history of all of them added up, the way Home
  Assistant's Power sources graph shows them.
- **The energy card's dots run smoothly.** A dot's place was worked out from the time since the card started, so every
  new value made it jump, worse the longer the screen ran and most on a battery that reports often (discussion #104).
  A new value now changes how fast a dot runs, not where it is. Back on the card's page after another page, the dots
  stood still until the next value came in; they run again at once. A slow dot (a few W) now reaches the end of its
  line too: every new value used to send it back to the start.
- **A new value on the energy card no longer holds the screen.** At every value the card searched its whole layout
  again, about a third of a second in which the screen stood still. It now keeps its layout until its shape changes
  and draws only the numbers that changed, in a few milliseconds.
- Checked with every Python, C++, editor, translation and WASM preview check, and rendered from the real firmware on
  the CYD, the 4-inch Guition and the 10.1-inch Guition. Firmware builds on ESPHome 2026.9.0 for the CYD (91.5 % of
  its slot, 17.7 KB more than 0.51.0), the CYD 9342 (91.5 %), the Hosyond 4-inch (94.3 %), the 4-inch and 10.1-inch
  Guition, the Waveshare 7-inch and the bridge, and on 2026.6.2 for every board that allows it (the CYD 93.4 %, the
  Hosyond 4-inch 96.1 %). The upgrade from 0.4.83 was tested on a CYD, a 4-inch Guition and a Waveshare 4.3-inch.

## 0.4.83 (firmware 0.51.0)

- **A calmer Screensaver card.** In a screen's settings the Screensaver card is now a short list of its three steps,
  Music playing, Camera and Clock, in the order the screen tries them. Each has one line that says what it will show
  ("Apple TV, Speaker", "No camera yet", "Outside temperature") and its switch. On a wide window the card stands in a
  narrow column, where its player and weather fields pushed the rows wider than the card and the switches over the
  next card. The card has no fields now, so nothing sticks out.
- **A step opens in the drawer.** Click a step and it opens on the right, as a tile and the top bar do, or in a sheet
  from the bottom on a phone. Music playing lists its players numbered in the order they are tried: drag them into
  place, take one out with its cross, and add the next from a menu. Camera has its camera. Clock shows the clock as the
  screen draws it, in the screen's own shape, with the temperature and the entities beside it; a line too wide for the
  glass drops its last entities there as it does on the screen. An entity of the clock leads back to the clock.
- Drag the steps into their order in the card, with the mouse or a finger, or move the open step with the arrows at
  the bottom of its drawer. The temperature's first choice is now called Automatic.
- No screen gets new firmware: this release is the editor alone, and what Tessera stores stays the same.
- Tested: the editor's tests, with new ones for the card and the drawer, the type check, the build, the translations
  check and every Python, C++ and WASM preview check. In the editor of the bench Home Assistant, at a desktop and a
  phone width, light and dark: opened each step, added, dragged and removed players, dragged the steps, turned steps
  off, removed an entity of the clock, and read back the choice the editor sent.

## 0.4.82 (firmware 0.51.0)

- **No more "999 %" right after a screen starts** ([#169](https://github.com/MaxGramser/homeassistant_espscreen/issues/169)).
  A screen measures how much memory it has for tiles, and it used to take its first measurement the moment Tessera said
  hello, before its tiles were there. That minute is the busiest one: Home Assistant sends every state at once and the
  cards are built, so the screen has some 25 KB less than a minute later. The screen reports the lowest of its last five
  measurements, so on a board with little memory to spare that one bad minute read as no room at all for ten minutes, and
  a restart started it over. A screen now measures only once its tiles have been on it for a minute.
- **"Measuring" instead of a number.** Until that first measurement the screen says nothing about its room, and the
  editor shows "Measuring" beside the tile count and asks nothing when you add a tile. Tessera keeps the last room the
  screen measured for when it is offline.
- **"No room" in words.** A screen that really has no memory to spare for tiles, or a layout that needs ten times what it
  has, shows "No room" instead of a share such as 999 %, and the pop-up says the same in a sentence. It is still a
  warning: you can add the tile, and the screen protects itself if it runs short.
- An older app with this firmware shows no meter until the first measurement, instead of 999 %.
- **"Update in Tessera first"** on a CYD, a CYD with an ILI9342 or a Hosyond 4-inch that still has the flash layout
  it was first installed with. Since firmware 0.48.0 the firmware of these boards no longer fits that layout's update
  slot, so the screen turns down an update from ESPHome Device Builder before it writes anything. Tessera moves the screen
  to the new layout on the way (app 0.4.56). The screen's details in the sidebar now say so with an (i) that explains
  why, and open by themselves while an update waits; its card on the overview carries the same (i). The hint goes once
  the screen says it has the new layout.
- Tested on the bench with Home Assistant, this app and real screens. With an older app (0.4.77) a CYD and a Waveshare
  4.3-inch on this firmware showed no meter for about two minutes after a start and then their room (63 KB and 48 KB),
  steady after. With this app the meter read "Measuring" six seconds after the Waveshare restarted and 16 % two minutes
  later. A CYD flashed back to firmware 0.2.104 with ESPHome's own table carried "Update in Tessera first" on its card
  and in its details, and no other screen did. Earlier the same day an Update in Tessera took such a CYD from 0.2.104 to
  0.48.0 over the bridge in eleven minutes, with the new layout. Checked with every Python, C++, editor and WASM preview
  check. Firmware builds on ESPHome 2026.9.0 for the CYD (90.6 % of its slot), the 4-inch and 10.1-inch Guition, the
  Waveshare 7-inch and the bridge (34.9 % of the old slot), and on 2026.6.2 for the CYD (92.5 %). "No room" in words is
  covered by the editor's tests only: no bench screen is that full.

## 0.4.81 (firmware 0.50.0)

- **Entities on the screensaver clock.** Under the clock's weather choice, **Add an entity** puts up to four entities in
  the same line as the outside temperature, centred at the bottom with a dot between two, in white on black: anything
  the top bar can show. Pick them from the top bar's own list, and for each one choose its text, its icon or both. They
  look as they do in the top bar, and a moment such as "5 min ago" counts on. A screen on older firmware keeps showing
  the temperature alone.
- The top bar and the screensaver clock draw their entities with the same code, and the editor's top bar and screensaver
  share one entity list and one way to add, move and remove.
- Checked with every Python, C++, editor and WASM preview check, and the clock with its row rendered from the real
  firmware on the CYD, the 4-inch Guition and the 10.1-inch Guition. Firmware builds on ESPHome 2026.9.0 for the CYD
  (90.6 % of its slot, 2 KB more than 0.48.0), the Hosyond 4-inch (93.4 %), the 4-inch and 10.1-inch Guition and the
  Waveshare 7-inch, and on 2026.6.2 for the CYD (92.5 %). Not yet seen on a real screen.

## 0.4.80 (firmware 0.49.0)

- **Pictures no longer hold the screen still.** Opening a folder of album covers in a speaker's library, a camera full
  screen, an alert with a snapshot or a page of live camera tiles used to freeze the whole screen while the picture
  downloaded: a tap landed late or not at all, and a page of covers took two to three seconds on a 4-inch screen. The
  screen now downloads every picture in a task of its own beside its main loop, so you can tap Back, turn the page or
  switch folders at once, also while the covers are still on their way. The pictures also arrive sooner: a full-screen
  camera picture on the 4-inch Guition in one second instead of two. Every board with pictures gets the fix.

## 0.4.79 (firmware 0.48.0)

- **What you tap changes at once.** Play and pause, mute, shuffle and repeat on a speaker, a mode of a thermostat or a
  humidifier (on its card and on the mode bar of its tile), an option of a select (its card and the arrows of its tile),
  a remote's activity and every on and off switch now show the new value the moment your finger touches them, also
  while the speaker or the airco takes a few seconds. The progress bar stops the moment you pause.
- **Tap as fast as you like.** The first tap goes to Home Assistant the moment you touch the screen. Taps that follow
  while it is on its way only change what you want, and the last one goes out as soon as Home Assistant has taken the
  first, so a fast Home Assistant gets every tap and a slow speaker a burst as one action, without any waiting time
  built in. A second tap is no longer ignored while the first is on its way.
- **The screen squares it with Home Assistant**, the way Home Assistant's own switches and mode buttons do: a message
  that still carries the old value keeps your choice, Home Assistant's own word wins when it says something else (a
  fan that took its nearest speed), a refused action springs back with "Refused", and an action that worked but
  changed nothing springs back after two seconds. A device that takes more than a second says "Updating..." on its
  tile and card, as Apple's Home app does, and no busy sheet covers the tile any more.
- **Cards no longer rebuild themselves for every change.** A card is built once and then changes only what changed.
  A new state from Home Assistant used to rebuild the whole card, which took about 400 ms on a 4-inch screen and made
  the title of a song stutter and a tap wait; now a card follows in 2 to 11 ms, a tap reaches Home Assistant within
  20 ms and the title keeps rolling. Every card works this way (docs/CARD_PARTS.md). The lock and alarm cards keep
  being built anew on every change of their state, code or attempt, exactly as before, with their animations; only
  their status line follows in place.
- The - and + of a thermostat no longer grey out while the value is on its way, and a - or + at the end of the span
  stays faded instead of lighting up again a moment later.
- **The lamps of a light group, its effects and a vacuum's chips** work the same way: a lamp switched, dimmed or
  coloured on the group's lamp page, an effect or a setting of the light's device, a cleaning mode or suction, all
  show at once, spring back when Home Assistant refuses them, and no longer wait four seconds for a stale value.
- Under the hood this is one mechanism for every control, with its rules in docs/OPTIMISTIC.md, and one way for a
  card to follow a change, in docs/CARD_PARTS.md. A test in the editor's preview builds every card both ways, painted
  and built anew, on three screen sizes and wants them pixel for pixel the same.
- Every screen is offered this firmware, 0.48.0.
- Tested: on the bench, the 4-inch Guition and the CYD against the bench Home Assistant, tapped by hand: switches that
  work, refuse, do nothing and take four seconds, fast bursts on a lamp, a select, a thermostat's modes, fan and swing,
  its -/+, a player's play, pause, shuffle, repeat, mute and volume, a blind, a fan, the alarm with a wrong code and
  the right one, three locks (unlock asks a second tap), a timer, a vacuum, a remote's activity, a light group's lamp
  page (on, off, dim, colour), a light's effects, a sensor's graph and the weather card; the screen's log shows every
  tap leaving within 20 ms and Home Assistant's answer. A card follows a change in 2 to 11 ms where it took 430 ms on
  the Guition. Every Python, C++, editor and WASM preview check, with a new one that builds every card both ways on the
  CYD's, the Guition's and the 10.1-inch glass and wants the same pixels. Firmware builds on ESPHome 2026.9.0 for the
  CYD (90.5 % of its slot, 12 KB more than 0.47.0), the CYD 9342 (90.5 %), the Hosyond 4-inch (93.2 %), the 4-inch and
  10.1-inch Guition and the Waveshare 7-inch, and on 2026.6.2 for the CYD (92.3 %).

## 0.4.78 (firmware 0.47.0)

- **"Not quite" leads to a GitHub issue that is already filled in.** When you tell Tessera a screen doesn't work as you
  expect, the card no longer ends with a small link under the problem boxes. After you pick what goes wrong (or skip
  it), it asks whether you want it fixed and offers one button, Open a GitHub issue. The bug report opens with your
  board, the add-on and firmware versions, the problems you ticked and your note already in it, so only the dropdowns
  and a log are left. Nothing goes to GitHub until you post it yourself, under your own name, so you can be asked
  about it and hear when it is fixed.
- No screen gets new firmware: this release is the editor alone.
- Tested: the editor's tests, with new ones for the filled-in link with and without a note, the type check, the build
  and the translations check. On the bench Home Assistant, the card of a Waveshare 4.3-inch driven in a browser: Not
  quite, Touch and a note, then the button, whose link carries the title, the versions, the board, the problem and
  the note, while the answer itself reached the Tessera website.

## 0.4.77 (firmware 0.47.0)

- **The energy card.** A new card in the library, Energy, shows the power of your house right now the way Home
  Assistant's own live Energy view and power-flow-card-plus show it: solar, the grid and the battery around the house,
  a line for every flow with dots that run faster as more power flows, the house's ring coloured by where its power
  comes from, and the devices that draw the most, with Other for the rest. It reads the Energy settings you already
  have in Home Assistant (power sensors, the battery's charge, the devices), so there is nothing to set up, and it
  splits the moment exactly as Home Assistant does. A tap on a circle opens that sensor's history. It is in Home
  Assistant's energy colours, light and dark.
- It fits itself to every screen like the other cards: the largest of the board's fonts that fit, the arrows and the
  names only where there is room, and the diagram turned upright on a screen standing up. A long device name takes
  two lines before the card shows a device fewer. The editor offers the sizes the diagram fits:
  2 × 2 on most screens, two columns of the whole height on the Waveshare 4.3-inch, three rows on the CYD standing up
  and a page of its own on the CYD lying down.
- The card keeps more memory than a clock, and the memory meter in the editor counts it at its own price.
- Every screen is offered this firmware, 0.47.0, which the energy card needs.
- Tested: the card rendered from the real firmware on the CYD lying down and standing up, the 4-inch Guition and the
  Waveshare 4.3-inch, light and dark, with seven moments of a house read from a Home Assistant with a fake house in its
  Energy settings (noon, a car charging at night, selling at the peak, solar only, grid only, seven devices, no power
  sensors), and a tap on the solar circle opening its history. On the bench, the CYD, the Guition and the Waveshare
  4.3-inch run it with live data from the bench Home Assistant. Every Python, C++, editor and WASM preview check; the
  layout of the diagram is checked on every density and look a board has, from the least room the editor offers up.
  Firmware builds on ESPHome 2026.9.0 for the CYD (89.9 % of its slot, 39 KB more than 0.46.0, agreed for this
  card), the 4-inch Guition, the 10.1-inch Guition and the Waveshare 7-inch, and on 2026.6.2 for the CYD (91.7 %).

## 0.4.76 (firmware 0.46.0)

- **No empty album cover on a screen without pictures.** The CYD, the Waveshare 3.5-inch and the Hosyond 4-inch have
  no memory for pictures, so they never get an album cover, yet the media card and a media tile over the whole page
  kept a square for one, with the player's icon in it. People took it for a cover that failed to load. Those boards now
  have no square at all: the title, the artist, the bar and the keys stand together in the middle of the card and take
  its room, a hand's width at most. The bar is wider, shuffle and repeat fit beside the keys on the CYD's card, and a
  player at rest shows its whole line ("Tap a cover in the library to play") instead of a piece of it beside an empty
  Spotify square. Boards with pictures keep their cover as before. The layout follows the room, not the board: what
  does not fit still goes in the same order, the artist line first.
- **The times beside a media card's bar fit a track of an hour or more.** Their place was as wide as "12:34", so a
  podcast, an audiobook or a long mix showed "1:02:..." at both ends. The place is now as wide as the track's length
  in the screen's own font.
- The editor's live preview of a screen follows its board: a CYD's preview shows the media card without a cover's place,
  as its glass does.
- Every screen is offered this firmware, 0.46.0.
- Tested: the media card and a media tile over a whole page rendered from the real firmware on the CYD before and
  after (no square, the words and keys in its room), and on the 4-inch Guition after (the cover as before). The layout
  audit now checks the boards without pictures as shapes of their own, so every card on the CYD, the Waveshare
  3.5-inch and the Hosyond 4-inch is checked without a cover's place. Every Python, C++, editor and WASM preview
  check. Firmware builds on ESPHome 2026.9.0 for the CYD (87.9 % of its slot), the 4-inch Guition, the 10.1-inch
  Guition and the Waveshare 7-inch, and on 2026.6.2 for the CYD (89.7 %).

## 0.4.75 (firmware 0.45.0)

- **A Big number card's number stays inside its card in the editor** ([#167](https://github.com/MaxGramser/homeassistant_espscreen/issues/167)).
  The editor drew a page in sizes of its own: a frame of 10 pixels, gaps of 8 and a page bar of 24, on every board.
  On a 4-inch Guition with three rows and more than one page that left a card 65 pixels high where the screen's card,
  at the editor's scale, is 73, and a Big number card stacked its icon, its name and its number in sizes of its own
  too, so the number was cut off at its middle. The editor's page now has the glass's proportions: the top bar from
  the top of the glass down to where the tiles start, the board's margins and gaps, and its page bar once the layout
  has more than one page. A Big number card is laid out as the screen lays it out: the icon and the name above the
  number in the largest face that fits, its unit at the right, and in a cell too low for that the name small at the
  top and the number under it, without the icon. The board's top bar, page bar and gaps now come with its other
  sizes (`boards.json`), a preview screen made in the editor gets the board's fonts and sizes too, and a test
  compares the editor's card heights and Big number cards with the firmware's on every board, lying down and
  standing up, with and without a page bar. The screen itself draws as before.

## 0.4.74 (firmware 0.45.0)

- **A new screen asks for its first tiles.** Once a new screen was in Home Assistant, its starting screen said
  "Waiting for Tessera", while it was really waiting for someone to choose its tiles. Tessera now tells a screen that
  it has no tiles for it yet, and the screen says what to do in three short steps: open Tessera in Home Assistant, pick
  tiles for the screen, by its own name, and press Save & send. A small tile in one of the Tessera mark's colours
  stands before each step. The words take the largest of the screen's faces that leaves them air, with the Tessera
  lockup over them where the glass has room for both: large words without the lockup on the 2.8- to 4.3-inch screens,
  the lockup over them on the 10.1-inch. The tiles take their place as soon as they are saved.
- The starting screen's hint after half a minute without Home Assistant no longer asks whether the screen was added
  under Devices & services. Tessera adds it by itself since 0.4.73, so the hint says that, and that Home Assistant has
  to reach the screen at its address.
- A long hint on the 2.8-inch ran into the version number at the foot of the starting screen. The number now steps
  aside when the words need the room.
- Every screen is offered this firmware, 0.45.0.
- Tested: the starting screen rendered from the real firmware on the CYD lying down and standing up, the 4-inch
  Guition, the Waveshare 4.3-inch and the 10.1-inch Guition, light and dark, before and after. On the bench, a
  Waveshare 4.3-inch without tiles runs 0.45.0 with this app and got the hello that asks for its first tiles. Every
  Python, C++, editor and WASM preview check, the layout audit included. Firmware builds on ESPHome 2026.9.0 for the
  CYD (87.9 % of its slot), the 4-inch Guition, the 10.1-inch Guition and the Waveshare 7-inch, and on 2026.6.2 for the
  CYD (89.7 %). The steps on glass were not looked at yet.

## 0.4.73 (firmware 0.44.0)

- **A new screen joins Home Assistant by itself.** After flashing, there were two steps left in Home Assistant: add
  the discovered ESPHome device (pasting the screen's API key when asked) and turn on **Allow the device to perform
  Home Assistant actions**, without which a tap on a tile does nothing. Tessera now takes both, through the same
  config flow and options flow Home Assistant's own dialogs use, and keeps checking until they hold instead of
  trying once. It answers Home Assistant's discovery of the screen with the key it wrote into the screen's YAML; finds
  the screen by its name on the network when Home Assistant did not discover it, or the discovery was dismissed or
  ignored; offers the key again a little later when the screen still ran older firmware; gives Home Assistant the new
  key when New screen made new ones for a screen it already had; takes Home Assistant's own "migrate" when a new board
  takes over a screen's name; and turns the actions on for a new screen, checks them once for every screen it made,
  and turns them back on at once when Home Assistant reports that it ignored a tap. It only adds screens whose YAML,
  with its key, is in the ESPHome folder it reads. New screen now goes from flashing straight to choosing tiles; the
  way by hand only shows when Tessera could not do it, and the manual describes it for screens built elsewhere
  ([docs/EASY_SETUP.md](../docs/EASY_SETUP.md#adding-a-screen-by-hand)).
- **Allow actions** on a screen's page, for the rare case Tessera could not turn the switch on itself (a Docker install
  whose token is not an administrator's): one click instead of Home Assistant's Configure dialog.
- New screen said "on your Wi-Fi" only for a screen whose friendly name and device name were the same: Home Assistant
  titles a discovered device "Friendly name (device-name)", and Tessera compared the whole title. It now reads the
  device name inside it.
- No firmware for a screen that exists: every screen stays on 0.44.0 and is offered nothing new.
- The screen's own hint after half a minute without Home Assistant still asks whether it was added under Devices &
  services: that text is part of the firmware, which this release leaves alone.
- Tested: on a Home Assistant 2026.9.4 test install with a Waveshare 4.3-inch, the whole way a user goes. A screen made
  with New screen and flashed over USB was discovered by Home Assistant and added by Tessera, actions allowed, 12
  seconds later. Taken out of Home Assistant again with its discovery set to Ignore, Tessera added it back by its name
  on the network within half a minute. Allow actions through the app's own address on a second screen. The answers Home
  Assistant gave in that test and in its source drive the unit tests of the rest: an older key still on the screen,
  new keys after New screen, a board that takes over a name, a refused tap, a Configure form without the switch.
  Every Python, C++, editor and WASM preview check. Not tested: a tap Home Assistant refused on real glass.

## 0.4.72 (firmware 0.44.0)

- **The Waveshare ESP32-S3-Touch-LCD-5 as a board of its own** ([docs/WAVESHARE5.md](../docs/WAVESHARE5.md)). The
  5-inch with 800 x 480 glass is the board of the Waveshare 4.3-inch with a larger panel: the same pins, timings,
  GT911 touch and CH422G expander in Waveshare's own library, and a 5-inch built from the 4.3-inch package ran with
  picture, touch and connection working. As its own board it draws tiles, text and keys at their size in millimetres
  on the larger glass (186.6 dpi instead of 217), three by three lying down like the 4.3-inch and one column of five
  standing up. It starts as **new**, not experimental. Choose **Waveshare · 5 inch** in New screen; a 5-inch that runs
  the 4.3-inch package can switch to `packages/waveshare5.yaml` in its own YAML. Not the 5B (1024 x 600). Thanks to
  jlwinland, who ran it and reported it on the Tessera website.
- Its hardware comes from the new `packages/hardware/waveshare-esp32s3-43.yaml`, which only the 5-inch includes for
  now; the 4.3-inch's board file is untouched and moves onto it at the next shared release.
- No firmware for a screen that exists: every screen stays on 0.44.0 and is offered nothing new.
- Tested: the 5-inch's firmware builds on ESPHome 2026.9.0. Not rendered (the 4.3-inch renders stand for it: the
  same canvas) and not tried on glass with this package.

## 0.4.71 (firmware 0.44.0)

- **The simple dial stays inside its card.** The clock's Simple dial face reached into the card's padding on a card
  of one row, so its black disc stood against the card's edge, and on larger cards it filled the card to the padding.
  Now the dial always stays inside the padding, like the content of every other card, and on a card of more rows or a
  whole page it keeps an eighth of its size as air too. A card of more rows also puts the dial beside or above the time,
  whichever draws the time larger: a near-square card (two columns by three rows on the 10.1-inch) drew a dial as tall
  as the card with a small time squeezed beside it, and now shows the dial over a time in full size.
- **The layout audit gives the same answer on every computer.** It cut each screen's layouts into pieces by the
  number of processors and named two overlapping texts in the order the firmware made them, so the flip clock's date
  under its digits, which is how the card is drawn, failed on one computer and passed on another. The pieces are now
  the same everywhere and the texts are named in reading order. Nothing changed on the screen: the 0.4.70 notes called
  this a case 0.4.69 already failed, but the picture was the same all along.
- The touch calibration of the CYD and the other resistive boards is now compiled on its own. With this release the
  CYD's firmware had grown past what an Xtensa instruction can reach back for its constants, by about 0.6 KB; it now
  has 35 KB to spare. Nothing changes in how the calibration works.
- Every screen is offered this firmware, 0.44.0.
- Tested: the Simple dial rendered from the real firmware (the WASM preview) in every size on the CYD, the 4-inch
  Guition and the 10.1-inch Guition, before and after. Every Python, C++, editor and WASM preview check, the layout
  audit included, which now passes on the computer where it failed. Firmware builds on ESPHome 2026.9.0 for the CYD
  (87.8 % of its slot), the 4-inch Guition, the 10.1-inch Guition and the Waveshare 7-inch, and on 2026.6.2 for the
  CYD (89.6 %). Not tested on glass.

## 0.4.70 (firmware 0.43.0)

- **The weather card's full view keeps its own text sizes**
  ([#52](https://github.com/MaxGramser/homeassistant_espscreen/issues/52)). The card borrowed its small text from the
  first tile on the page, in whatever size that tile showed at the moment. With a large value there (a sensor shown as
  Large value), the hours, the conditions, the rain and the low temperatures came out twice as large as the rest of
  the card, the rain amounts ended in dots, and the lows stood larger than the highs. Where a large number had grown
  into the largest digits (on a large screen with tall cells), it was worse: those digits carry no letters, so the
  words turned into empty boxes. The card now always uses the screen's own small text, so it looks the same whatever
  the first tile shows. Every board had this.
- Every screen is offered this firmware, 0.43.0.
- Tested: the full view rendered from the real firmware (the WASM preview) on the 10.1-inch Guition with a light, a
  large number and a large word in the first tile now gives the same picture three times, and the picture with a light
  and every tile page are unchanged pixel for pixel. A new preview test checks this on the CYD, the 4-inch Guition and
  the 10.1-inch, and fails on the firmware before this one. Every Python, C++, editor and WASM preview check passes
  but one layout audit case that 0.4.69 already fails (the flip clock's date on the 10.1-inch with eight rows), which
  this change does not touch. Firmware builds on ESPHome 2026.9.0 for the CYD (87.6 % of its slot), the 4-inch
  Guition, the 10.1-inch Guition and the Waveshare 7-inch, and on 2026.6.2 for the CYD. Not tested on glass.

## 0.4.69 (firmware 0.42.0)

- **Humidifiers and dehumidifiers as tiles** ([#128](https://github.com/MaxGramser/homeassistant_espscreen/issues/128)).
  A `humidifier` entity is now in the library, a dehumidifier on a smart plug with Home Assistant's Generic hygrostat
  too. It works like a thermostat in percent, with Home Assistant's own words, icons and colour:
  - The tile says what it is doing and the humidity it measures ("Drying · 68%", "Humidifying · 38%", "Off · 52%"). When
    the word does not fit a small tile, the humidity stays readable. Blue while it is on, grey while it is off, with
    Home Assistant's crossed-out icon.
  - A tap opens its card: the power key, the humidity it measures, and the target humidity big in Home Assistant's ring
    between − and +. The ring fills up to the target for a humidifier and from the target up for a dehumidifier, and
    shows the part still to go while the device is working.
  - Its modes (normal, eco, away, boost, comfort, home, sleep, auto, baby) are round keys with Home Assistant's icons.
    A device with modes of its own gets them as a row of their names instead, since those have no icon.
  - A double-width tile takes the humidity − / +, a slider, the mode keys or an on/off switch; a tile of two rows
    takes − / + with the mode keys under it, and a tap on its circle turns it on or off.
- The editor shows humidifiers the same way and lists them under their own filter.
- Tested with the firmware's own drawing on the host (the CYD, the Guition 4-inch, the Waveshare 4.3-inch and the
  10.1-inch Guition, lying down and standing up, light and Dark mode), and every Python, C++, editor and WASM preview
  check. Not yet on a real humidifier.

## 0.4.68 (firmware 0.41.0)

- **A screen's battery in its top bar.** In the editor, click the top bar and choose Add, Battery: Home Assistant's
  battery icon at the level the screen has, with the lightning bolt while it charges, and the percentage beside it if
  you choose. Show it always, or only when the battery is at 20 % or less. The screen reads its battery itself, so the
  item stays right while Home Assistant is away. It is offered only on a screen that has a battery.
- **Any ESPHome battery sensor works.** The firmware finds the screen's sensor in Home Assistant's `battery` device
  class and its binary sensor in the `battery_charging` class, the way Home Assistant itself knows a battery. A fuel
  gauge, a power chip, a voltage on a pin with a formula or a curve of your own all work, also from a screen's
  Override YAML. Two packages turn a voltage into a level for a board: `battery-adc.yaml` reads a pin through a
  divider, and `battery-voltage.yaml` applies a formula you can replace. [docs/BATTERY.md](../docs/BATTERY.md) has the
  recipes, the pins that work next to Wi-Fi, and the Override YAML for a battery of your own.
- **The M5Stack Tab5 is the first board with it**: its level from the INA226 on the battery, and a new **Battery
  Charging** sensor in Home Assistant, on while more than 50 mA flows into the pack (the way M5Stack's own firmware
  reads that current), with **Battery Current** beside it.
- Every screen is offered this firmware, 0.41.0. A screen without a battery only gets the few new icons in its font.
- Tested: every Python, C++, editor and WASM preview check, with Home Assistant's battery icon rules as a test of their
  own. Firmware builds on ESPHome 2026.9.0 for the CYD (87.2 % of its slot), the 4-inch Guition, the 10.1-inch Guition,
  the Waveshare 7-inch and the Tab5, on 2026.6.2 for the CYD and on 2026.7.1 for the Tab5. The pin recipe compiles on a
  CYD (87.6 %), and the battery item was rendered from the real firmware in the top bar. Not tested on glass: the
  Tab5's charging current and its sign come from M5Stack's own firmware, and its owner is asked to try it.

## 0.4.67 (firmware 0.40.0)

- **A live camera tile keeps refreshing on a dimmed screen**
  ([#161](https://github.com/MaxGramser/homeassistant_espscreen/issues/161)). When Auto standby dimmed a screen and the
  screensaver had nothing to show (say only a music player is chosen and nothing plays), the dimmed tiles stayed on the
  glass, but their camera pictures stopped loading: the picture stood still and the camera looked broken. Now the
  pictures on the tiles keep loading as long as the tiles are seen: in standby without a screensaver over them, at a
  standby or night brightness of 5 % or more. A screensaver, the clock included, covers the tiles, and below 5 % nobody
  reads a picture, so then they wait until the screen wakes, as before. The same goes for a media card's album cover.
  Sleep pressed in Home Assistant follows the same rule.
- The backlight in standby and this rule take the level from one place in the firmware, so they always agree.
- Tested on the bench Guition 4-inch with a live camera tile: in standby at 40 % it kept loading every 15 seconds, at
  3 % it stopped and went on again at 40 %, the clock screensaver stopped it, and a touch brought it back. Every Python,
  C++, editor and WASM preview check, and the firmware of the sample boards on ESPHome 2026.9.0 and the CYD on 2026.6.2.
- Every screen is offered firmware 0.40.0, the Tab5 too: its own 0.39.1 is part of it.

## 0.4.66 (firmware 0.39.1 for tab5)

- **Wi-Fi on the M5Stack Tab5 after a cold start** ([#150](https://github.com/MaxGramser/homeassistant_espscreen/pull/150)).
  The Tab5's Wi-Fi is an ESP32-C6 beside the ESP32-P4, and it gets its power from an output of the board's second I/O
  expander (0x44). The firmware never switched that output on, so the C6 only had power when an earlier firmware had
  left it on, and after the battery was off the screen stopped at "esp_wifi_init failed: ESP_FAIL". The firmware now
  switches the C6 on at boot, together with the battery charger and its quick charge, the same three outputs M5Stack's
  own firmware and ESPHome's Tab5 configuration switch on. Thanks to @Heronimonimo for the report.
- Only the Tab5 is offered this firmware, 0.39.1. Every other screen keeps 0.39.0.
- Tested: every Python, C++, editor and WASM preview check, and the Tab5 firmware builds on ESPHome 2026.9.0 and on
  2026.7.1. Not tested on glass: there is no Tab5 here, and its owner is asked to try it.

## 0.4.65 (firmware 0.39.0)

- **A build on a machine with little memory finishes instead of being killed**
  ([#162](https://github.com/MaxGramser/homeassistant_espscreen/issues/162)). Compiling a screen's firmware takes well
  over a gigabyte for its largest file, and on a Raspberry Pi or a small virtual machine with Home Assistant beside it
  that is more than is free: Linux stopped a compiler ("Killed signal terminated program cc1plus") and the build failed
  with nothing wrong in the code. Now the app reads how much memory is free before a build and runs only as many
  compilers at once as fit. When a compiler is stopped all the same, the build runs again with one compiler at a time,
  from where it stopped, and the progress bar goes on from there. The installer shows a card that says what is
  happening and why it takes longer; Firmware & USB says the same under its status line. When even one compiler is
  more than the machine has, the card says how much is free and how much is needed, and what to do about it, instead
  of the compiler's own words; a nightly update that fails for the same reason says so in its result.
- **What counts as free memory** is Linux's own count (`MemAvailable`), and less when the app's container has a memory
  limit of its own (Docker's `--memory`, some NAS systems), which that count leaves out. A build counts as out of memory
  when a compiler says so and also when Linux stops ESPHome itself, which leaves no line in the log.
- Tested on a Home Assistant Yellow (4 cores, 8 GB): with all four compilers a build of the Guition peaks at 2.0 GB, with
  one at 1.6 GB, and a compiler that really runs out of memory is followed by a build with one compiler that finishes.
- No firmware change: every screen stays on 0.39.0. Update the app.

## 0.4.64 (firmware 0.39.0)

- **New board: the M5Stack Tab5** ([#79](https://github.com/MaxGramser/homeassistant_espscreen/issues/79), PR
  [#150](https://github.com/MaxGramser/homeassistant_espscreen/pull/150)), the 5-inch 1280 x 720 tablet with an ESP32-P4,
  in its ST7121 variant (the factory log says "Detected ST7121 touch controller"). Three rows of three tiles, or four
  rows when you choose that in New screen, camera tiles and pictures, the Wi-Fi hotspot with its QR code, and the
  battery's voltage and level as sensors in Home Assistant. Other Tab5 variants are not covered yet: check the factory
  log first ([docs/TAB5.md](docs/TAB5.md)). It needs ESPHome 2026.7 or newer, which the app has. Thanks to
  @Heronimonimo, who built and tested it on his own Tab5.
- **The Waveshare 4B dims over the whole range** ([#158](https://github.com/MaxGramser/homeassistant_espscreen/issues/158)).
  Everything under about 74 % brightness was dark, so night and standby brightness turned the screen off instead of
  dimming it. On this board GPIO4 is not a switch for the LEDs but the analog dim input of their driver (an AP3032),
  behind a filter, and the driver stops altogether once that level passes about 1.78 V. At the 5 kHz it ran (as
  Waveshare's own examples do), the ripple behind the filter crossed that line long before the average did. The pin now
  runs at 300 kHz, the dimmest step stays just inside the range where the driver runs steadily, a brightness of 0 is
  still dark, and the light no longer applies ESPHome's gamma, which pressed everything under 30 % onto the dimmest step.
  Thanks to @EythorE for the schematic reading and the measurements on a real panel.
- **A diabetes icon** for a tile or the top bar ([#156](https://github.com/MaxGramser/homeassistant_espscreen/issues/156),
  PR [#160](https://github.com/MaxGramser/homeassistant_espscreen/pull/160)), `mdi:diabetes`, under Other in the icon
  picker. Thanks to @Heronimonimo.
- **A power key on the media card, and volume keys** ([#146](https://github.com/MaxGramser/homeassistant_espscreen/issues/146)).
  A player that Home Assistant can turn off (a TV, an AV receiver, a speaker with a power switch) has its power key at
  the top right of the card, where every other card keeps its keys, and only then: Spotify and other players that
  cannot be turned off show none. A player whose state Home Assistant only assumes gets both power keys, as in Home
  Assistant's own dialog, and the power keys use its icon. The row at the bottom of the card is new: volume down, a
  shorter slider and volume up, round keys like the screensaver's, and after them the player's inputs and its
  library, which moved down from the top bar. Every tap on volume down or up is a step, also when you tap fast. Hold
  volume down to mute, and the next tap on either key takes the mute off. A media tile over a whole page has the same
  row, without the percentage it showed.
- **A player's card is plain black while nothing plays**, without the grey to black gradient it still had. A cover's
  own colours still colour the card while it plays.
- A camera picture on an alert stays within the screen's own full-screen picture, also on a large glass.
- Every screen is offered this firmware, 0.39.0.
- Tested: every Python, C++, editor and WASM preview check, and the layout audit of every card on every board shape.
  Firmware builds on ESPHome 2026.9.0 for the CYD (87.0 % of its slot), the Guition, the 10.1-inch Guition, the
  Waveshare 7-inch, the Waveshare 4B and the Tab5. The media card, its power key, the new volume row and the tile over
  a whole page were rendered from the firmware on the CYD, the Guition, the Waveshare 4.3 and the 10.1-inch Guition.
  Not tested on glass in this release: the Tab5 was tested by its contributor, the 4B dimming by its reporter's
  measurements, and the volume keys and power key only in renders.

## 0.4.63 (firmware 0.38.0)

- **The starting screen says what it is doing, step by step** ([#130](https://github.com/MaxGramser/homeassistant_espscreen/issues/130)).
  Connecting to Wi-Fi and the network's name, getting an address, waiting for Home Assistant, waiting for Tessera,
  loading tiles 12/40, preparing pages. Under each step stands what the screen knows of it: the network, its signal in
  dBm and the address, and how long the step has taken once it takes more than a few seconds. Everything comes from
  ESPHome itself (the network it tries, the signal, the address, its Wi-Fi scan), so nothing new runs on the screen.
- **When the Wi-Fi does not work, the screen says why**: the network is not found, the password is not accepted, or
  the signal is too weak. The reason is the one ESP-IDF gives when the access point turns the screen away, which ESPHome
  only writes to its log. After a minute, or once the hotspot is up, the Wi-Fi problem screen also names the network and
  the reason.
- **The hotspot of a screen that lost its network says which screen it is**, "Tessera Living room" instead of
  "living-room Setup", so a house full of screens after a new router shows which hotspot is which. A screen made before
  gets the new name with its next update. Under the hotspot's name and password stands a **QR code**: point a phone's
  camera at it and the phone joins the hotspot, where ESPHome's page lets you pick the new network. Only on boards with a
  hotspot; the CYD and the other 4 MB boards have none and build no QR code.
- **A step that takes long says what usually fixes it.** After 30 seconds without Home Assistant: is this screen added
  under Settings → Devices & services → ESPHome? After 30 seconds without Tessera: is the app running? And at once, when
  Home Assistant (or anything else) tried to connect with a key that is not this screen's, which address that was and to
  enter this screen's key in the ESPHome integration (ESPHome's own `on_client_disconnected`: a client that leaves
  before it names itself never got through the encrypted handshake).
- **A firmware update shows how far it is.** The screen wakes, closes the screensaver and says "Updating firmware 45%"
  over everything, then "Update complete, restarting". Before, the screen looked frozen for a minute. ESPHome's own OTA
  listener reports the progress, whatever OTA platform the screen's YAML has.
- **New top bar items from the screen itself**: the Wi-Fi signal, the familiar icon with four bars down to one and
  struck through without a network, as an icon alone or with a percentage or dBm beside it, always or only when weak; and
  a connection warning that appears only while Home Assistant or Tessera is away. Both stay in the bar when Home
  Assistant is gone, when every other item has left it. Tap either and "This screen" opens on the settings page. A
  screen gets them once its firmware takes them (its hello says so); an older one shows the rest of its bar as before.
- **"This screen" on the settings page** now also shows the Wi-Fi network with its signal and whether Tessera is
  connected, and tells them again every two seconds while it is open. Thanks to @woozer, whose screenshots in #130
  showed these rows first.
- **A tap Home Assistant ignores explains itself.** Home Assistant ignores a screen's actions until "Allow the device to
  perform Home Assistant actions" is on, and answers nothing. Such a tap now says "No answer" on its tile, and the first
  one after a start opens a card: no answer from Home Assistant, and where to turn actions on. It is the screen's own
  card, so it sends no `esphome.screen_alert` event when it closes. The editor shows the same fix on the screen's page
  as soon as Home Assistant has raised its own repair issue for it.
- **The progress bar of a new screen's build moves while it builds.** ninja writes its count over one line again and
  again, and the app kept only the start of that line, so the bar stood near 0 % for the whole build and then jumped.
  The app now keeps what a terminal shows, the bar follows the build itself (not the bootloader beside it, nor the size
  report after it, which put it back to 0 % at the end), and getting ready moves too: reading the configuration,
  generating the code, checking ESP-IDF and configuring CMake each take the bar a little further.
- The fourth Wi-Fi bar, the struck-through one and the other three cost five glyphs in one small font of their own.
  The CYD's firmware is at 86.9 % of its slot (1,764,544 bytes), up from 86.3 %.
- Every screen is offered this firmware, 0.38.0.
- Tested: the add-on, editor and firmware checks, new tests for the Wi-Fi diagnosis, the top bar items, the hotspot name
  and its rename on older screens, and the editor preview rebuilt from this firmware. On the bench CYD, 4-inch Guition and
  Waveshare 4.3: the Wi-Fi item and "This screen", an update from standby showing its progress on the Guition and the CYD,
  a wrong Wi-Fi password saying "Password not accepted" on both and then the problem screen (USB on the CYD, the hotspot
  with its QR code on the Guition), the Guition joined to the right network again through that QR code, a CYD with a key
  Home Assistant does not have, and the Guition with actions turned off (the tile, the card, the repair issue read by the
  app, and no event when the card closed).

## 0.4.62 (firmware 0.37.0)

- **A tile on a Hue room no longer jumps back after a tap** ([#159](https://github.com/MaxGramser/homeassistant_espscreen/issues/159)).
  Tap a Hue room off and its tile went off, on and off again within a second. The Hue bridge reports the room's lamps
  at once and the room itself about a second later. Each lamp made the app send the room's tile again, still saying
  "on", and the screen took that as the answer to the tap. Now the tile works like the switch on Home Assistant's own
  tile card: it stays where the tap put it until the on or off really changes. A state that still says what the tile
  said before the tap no longer counts as the answer.
- If Home Assistant said the action worked but no new state follows, the old stand comes back two seconds later, as
  Home Assistant's own toggle does. A refused action still shows the old stand at once.
- Every screen is offered this firmware, 0.37.0.
- Tested: the add-on and editor checks, a new test in the firmware's own tap path (the editor's preview, rebuilt from this
  firmware) with a room whose old state arrives first and the new one later, and the firmware built for the CYD, the
  4-inch Guition, the 10.1-inch Guition and the 7-inch Waveshare, and for the CYD on the oldest ESPHome the packages
  support. Not yet seen on a Hue room on a real screen.

## 0.4.61 (firmware 0.36.0)

- **The memory budget is a warning, no longer a rule** ([#157](https://github.com/MaxGramser/homeassistant_espscreen/issues/157)).
  Since 0.4.58 the app refused a layout that needed more memory than the screen said it had for tiles. One CYD measured
  far less room than the screens the budget was worked out on, so even a working layout of 23 tiles, and in the end any
  tile at all, was refused. Now a save always goes through. The meter beside the tile count stays, and adding a tile that
  takes the layout past nine tenths of the room, or past all of it, asks first in a pop-up: answer yes and the tile goes
  on, from a click or a drag in the library alike. The library no longer greys out tiles for their memory.
- A screen still protects itself when it runs short, as since firmware 0.34.0: tiles off the glass show less until there
  is room again, and a layout the screen can't take whole it turns down, staying reachable, so you can go back.
- No new firmware: screens keep 0.36.0.
- Tested: the add-on and editor checks, with new tests for the pop-up (no adds nothing, yes adds the tile, and it asks
  once per line) and for a save past the budget going through.

## 0.4.60 (firmware 0.36.0)

- **Every character on your keyboard shows on the screen** ([#147](https://github.com/MaxGramser/homeassistant_espscreen/issues/147)).
  The screens drew letters in every European language but missed a few plain ones, so an artist called "bbno$" lost its
  dollar sign on the media card. Every text on the screen (card titles, tile names, values, the top bar, the media card)
  now also draws ``# $ * = ^ ~ | ` [ ] { } \`` and `– × © ® ™ ¢ ¥ §`.
- **Hearts.** ♡, ♥ and ❤ show as hearts, also the red-heart emoji in a song title: the invisible character an emoji
  carries after the heart no longer leaves a box behind it. The hearts come from Noto Sans Symbols 2
  (SIL Open Font License), cut down to just these three, as Roboto has none.
- It costs 8 KB of flash on the CYD (now 86.3 % of its slot) and 10 to 15 KB on the larger screens, measured against
  0.4.59.
- Every screen is offered this firmware, 0.36.0.
- Tested: the add-on and editor checks, the editor's preview rebuilt from this firmware with the layout check of every
  card on every board, and the firmware built for the CYD, the 4-inch Guition, the 10.1-inch Guition and the 7-inch
  Waveshare, and for the CYD on the oldest ESPHome the packages support. Not yet seen on a real screen.

## 0.4.59 (firmware 0.35.0)

- **Five to eight rows on the 10.1-inch Guition**, thanks to Jeroen Peters
  ([@Heronimonimo](https://github.com/Heronimonimo), [#151](https://github.com/MaxGramser/homeassistant_espscreen/pull/151),
  GitHub #125). New screen asks how many rows a page has when you build any of the three JC8012P4A1 variants: five, as
  before, or six, seven or eight, for up to forty tiles on a page instead of twenty-five. The tiles get lower with every
  row, from 23.5 mm high with five rows to 14.0 mm with eight, and every card still fits. A screen you already have
  keeps its five rows; it gets more by adding `GRID_ROWS: "6"` (or 7, or 8) to its own YAML and installing it again,
  and its saved layout moves along by itself, every tile on its own page, row and column. Standing up keeps five by five.
- **A card that fills the page keeps its large keys whatever the grid under it.** Its keys followed the height of one
  cell, so with eight rows the whole page got the small ones, a slider of 5 mm. They now follow the room the card has
  on the glass: large keys once it runs 56 mm along its longer side. Every board keeps what it had, with one exception:
  the Hosyond 4-inch lying down now gets the large keys on a full-page card as well, as it does standing up.
- **A big value keeps its icon on a low cell.** A tile showing its value big (the watch display) dropped its icon and
  pushed the number against the name when the cell was too low for icon, name and big number, as on the Waveshare
  4.3-inch with three rows and the 4-inch Guition with four. It now takes the largest number that fits under the icon
  and the name; only a cell too low even for the smaller number shows the number alone, below the name, never against it.
- **A small analog clock keeps its numerals apart.** On a dial too small for the 12, 3, 6 and 9 to stand clear of each
  other (the 4-inch Guition with four rows) the clock shows strokes instead, as the compact look does.
- Every screen is offered this firmware, 0.35.0.
- The layout check that lays out every card on every board now does so for every number of rows a board offers too
  (the 4-inch Guition's four rows, the 10.1-inch's six to eight).
- The README and docs/JC8012P4A1.md show a living room with six, seven and eight rows, rendered from the firmware.
- Tested: the firmware of the 10.1-inch built and rendered on this computer with six, seven and eight rows, a full page
  of cards each, light and dark, and the cards the layout check names at each; six rows on a real screen by the
  contributor.

## 0.4.58 (firmware 0.34.0)

- **More than 100 tiles on a screen that has the memory for them.** A screen now says how many tiles, pages and top bar
  items it takes. Boards with PSRAM (the ESP32-S3 boards) take 128 tiles on up to 24 pages, the ESP32-P4 boards 256
  tiles on up to 16 pages, and both up to 12 items in each page's top bar. The boards with 4 MB of flash and no PSRAM
  (the CYD, the CYD with an ILI9342 and the Hosyond 4-inch) keep 64 tiles on 8 pages and 6 items.
- **A memory budget in the editor.** What a tile keeps in the memory inside the screen's chip depends on its type: a
  forecast or a media player takes ten times what a light takes. Every type in the tile catalogue now has a price, and
  the screen reports how much room it has. The editor shows the share in use beside the number of tiles, turns amber
  close to full, and greys out the tiles in the library that would not fit. docs/TILE_MEMORY.md explains the numbers.
- **A layout that does not fit is refused before it is saved**, with how much it needs and how much the screen has. A
  screen that runs out of memory halfway anyway (an older app sends a layout without asking) stops taking it, lets go
  of what it took and stays reachable, and the app says the layout needs more memory than the screen has. Before, a
  screen could lose its Wi-Fi link until someone restarted it.
- **Lighter in the memory inside the chip.** The extra details of a tile (a forecast, a media player's titles, a
  thermostat's modes) now live in PSRAM on a board that has it, about a kilobyte per tile less in the scarce memory.
- **A top bar item can show its icon alone** (GitHub #144), coloured with its state, so more of them fit beside the
  name. Items that do not fit leave from the front, as before, and the editor marks them.
- **Past eight pages the page bar shows the page number** ("3 / 20") instead of a row of dots.
- **Screens update when you choose.** An app on this version works with screens on older firmware: they keep 64 tiles
  on 8 pages, and the editor shows no memory bar for them until they run firmware 0.34.0.
- The CYD, the CYD with an ILI9342 and the Hosyond 4-inch join the shared firmware again (0.33.1 becomes 0.34.0). The
  CYD's firmware takes 85.9 % of its update slot.
- Tested: on an ESP32-S3 4-inch (Guition), an ESP32-S3 4.3-inch (Waveshare) and a CYD on USB, with a bench Home
  Assistant. 120 tiles on 20 pages with 12 top bar items on the 4-inch, checked on the glass; 128 tiles on the
  4.3-inch; each screen filled to its whole budget with the heaviest tiles (45 on the 4.3-inch, 40 on the CYD) held for
  a quarter of an hour without a restart, where the CYD stopped before at 48. Too heavy a layout was refused with its
  numbers. A CYD on firmware 0.33.1 with this app kept its old limits and showed no memory bar. The prices were
  measured on the screens: on the PSRAM boards they count about a tenth more than the tiles take, on the CYD about 80
  bytes a tile less, inside the reserve the budget keeps.

## 0.4.57 (firmware 0.33.0)

- **Support Tessera every month.** The card on the editor's overview now offers a monthly membership first, with a
  one-time coffee next to it. Tessera stays free; a small monthly contribution pays for the time that goes into new
  cards and new boards. The README and the add-on's page link the same way.

## 0.4.56 (firmware 0.33.1 for cyd, cyd9342, hosyond40)

- **More room for firmware on a screen with 4 MB of flash** (the CYD, the CYD with an ILI9342 and the Hosyond
  4-inch). Their firmware had filled its update slot. These boards now have a partition table of their own with
  update slots of 2,031,616 bytes where ESPHome's own table has 1,835,008, about a tenth more. The room comes from
  the area for settings, which was 448 KB and almost empty: the settings now have 16 KB in a place that was unused,
  and they fill about a quarter of it.
- **A screen you already have moves by itself.** Update the screen as you always do. After the update Tessera sends
  it the new table and the screen restarts once more. Everything it kept comes along: the touch calibration, the
  settings of the settings page, which way it hangs. The screen copies all of it to the new place first and compares
  the copy both ways, and it asks for the table only when the copy is exact and ESPHome has confirmed the new
  firmware, a minute after the update. That makes this one update a few minutes longer.
- **An install over USB keeps the settings too.** It writes the new table at once, and the screen fetches its
  settings from the old place the first time it starts.
- **A firmware that outgrows the old slot still reaches a screen with the old table.** Tessera then installs a small
  firmware in between that can take the table, sends the table, and installs the screen's own firmware. The glass is
  dark for a minute or two while it does. Nothing needs this yet: today's firmware fits both tables.
- A new diagnostic sensor on these boards, **Screen flash**, says which table a screen has: `wide` when it has the
  new one.
- No other board changes: their firmware stays 0.33.0 and they are offered no update.
- One thing to know: the table itself is written in a fraction of a second, and a screen that loses its power in
  exactly that moment needs an install over USB afterwards. docs/FLASH_LAYOUT.md has the whole story.
- Tested: on a CYD (ESP32-2432S028R) on USB. Sixteen starting states, among them today's firmware with ESPHome's
  table, this firmware in either slot, a setting changed just before the table, random bytes and another firmware's
  settings in the unused 16 KB, a table that is not ESPHome's, an erased board, installs over USB onto both of the
  first two, the small firmware in between, and a restart in the first minute after it; 186 checks in all. After
  each step the flash was read back over USB and every kept value compared with a copy from before (the screen's
  settings, the radio's calibration and ESP-IDF's own), and a setting was changed and read again after a restart.
  Twenty-four resets at chosen moments around the write of the table: outside a window of about 40 milliseconds the
  board came back every time with everything in place; inside it seven of ten did not start, and an install over USB
  brought each back with its settings. Then the app's own updater against the board with the real ESPHome commands,
  with a firmware that fits and with one that does not. Then the app itself in a Home Assistant on the bench, from
  the Update button: ten and a half minutes of which six were the build, and six and a half over the small firmware
  in between with the screen away for two; Home Assistant's entity registry kept every entity and only gained the
  new sensor. The three boards and the small firmware build with ESPHome 2026.9.0 and 2026.6.2 (the CYD with an
  ILI9342 asks for 2026.7), and the firmware built with 2026.6.2 walked the same way on the board. Not tested on a
  Hosyond or a CYD with an ILI9342 themselves: the same chip and the same table, but no such board on the bench.

## 0.4.55 (firmware 0.33.0)

- **Keys on the screensaver.** Over a cover three round keys stand in the bottom right corner: play or pause at the
  bottom, volume down over it and volume up at the top. A tap on one of them works for the player on the screen and
  the screen stays in standby; a tap anywhere else wakes it, as before. A player without a volume in Home Assistant
  has the play key alone. A long title ends before the keys: it takes its second line and then its dots.
- **Mute.** Hold volume down for a second and a half and the player is muted; the key shows a muted speaker. The next
  tap on either volume key takes the mute off, and after that the two are the volume again.
- **A paused player still shows.** A player that plays goes first, in the order of your list; when none plays, the
  first paused one shows, with a play key. The player you pause on the screen keeps the screen for two minutes, so
  its play key stays where your finger is. Ten minutes after a pause the screensaver moves on to the camera or the
  clock, since a speaker stays paused in Home Assistant for days. A screen on older firmware shows what it showed.
- **The players are a list you drag.** In a screen's screensaver settings each player has a grip: drag them into
  their order with the mouse, with a finger on a phone, or with the arrow keys. The steps drag from their grip under
  a finger the same way.
- Tested: on a Guition 4848S040 with Home Assistant on the bench, by hand on the glass: volume up and down, pause
  and play on the same player while another one played, mute after holding volume down and the mute taken off by the
  next tap, each with the screen staying in standby, and a tap beside the keys woke it. A paused player kept the screen
  for two minutes and then gave way to the one that played. The real firmware on a computer with a finger made in
  software did the same on the Guition and the 10.1-inch board, with a long title and a player without a volume. The
  list of players was dragged in the editor with the mouse, the arrow keys and a finger on a phone-sized window in
  Chrome, not on a real phone. The CYD, both Guitions and the Waveshare 7 build with ESPHome 2026.9.0 (the CYD image is
  94.4 % of its slot), and the CYD with 2026.6.2 (96.4 %). The CYD 9342 and the Hosyond 4-inch were not built; the
  Hosyond was over its flash budget before this release. Not looked at on a 7 or 10-inch glass, and not with a real
  speaker and television.

## 0.4.54 (firmware 0.32.0)

- **The screensaver takes more than one player.** Under Music playing in a screen's screensaver settings an empty row
  now stands under the player you chose: pick a second one there, and a third and a fourth if you like. The screen
  shows the first of them that plays with a cover, in the order of the rows. Made for a speaker that also plays the
  television's sound: with the speaker first and the television's player second you see the cover while the speaker
  plays music, and the poster of the series while it plays the television, since it has no cover of its own then. Set
  a row back to its first line to take that player out. The screens need no update for it.
- Tested: on a Guition 4848S040 (firmware 0.32.0) with Home Assistant on the bench, two players and a camera: with
  both playing the screensaver showed the first player's cover, with the first paused the second one's poster, with
  both paused the camera, and it came back the same way. Added and removed players in the editor by hand. No firmware
  changed, so nothing was built for a screen.

## 0.4.53 (firmware 0.32.0)

- **The screensaver keeps its cover until the next one is there.** When the music went to the next track, the
  screensaver closed and opened again, and the glass stood black for as long as the new cover took to load. Now the
  last cover and its title stay, and the new cover and title take their place together the moment it has loaded. The
  same goes for a switch between the music and the camera.
- Tested: on a Guition 4848S040 with Home Assistant on the bench, the screensaver on a playing player: a new track kept
  the last cover and title until the new cover had loaded (one load per track), two tracks a second apart ended on the
  second, and a player that stopped handed over to the camera the same way. The CYD, both Guitions and the Waveshare 7
  build with ESPHome 2026.9.0, the CYD and the Hosyond 4-inch with 2026.6.2; the Hosyond stays over its flash budget as
  before. Not looked at on long glass (7 and 10-inch), where the cover's colour beside it loads a second time.

## 0.4.52 (firmware 0.31.0)

- **The screensaver's clock is white on black.** It stood in the screen's own colours, a lit white glass in the light
  look. Now it is black with white digits whatever the look, so a screen in standby gives as little light as it can.
- **AM or PM on the screensaver's clock** when the screen shows 12 hours, after the time as on the clock card.
- **The outside temperature under the clock**, small in the middle at the bottom: whole degrees from Home Assistant's
  own forecast for your home (the one it sets up with Met.no), in the unit Home Assistant is set to (Celsius or
  Fahrenheit). Under the clock in the editor's screensaver settings you can choose another weather entity, or none.
  Without a weather entity there is none.
- Tested: on a Guition 4848S040 with Home Assistant on the bench, set to 12 hours and Fahrenheit: in Auto standby the
  clock stood white on black with PM after the time and the home forecast's 66° under the date. Sleep from Home
  Assistant still turns the glass dark without a screensaver. The CYD, both Guitions and the Waveshare 7 build with
  ESPHome 2026.9.0 (the CYD image is 94.2 % of its slot). The Hosyond 4-inch builds but stays over its flash budget, as
  it was before this release (99.2 % with ESPHome 2026.6.2). Not looked at on a CYD's glass.

## 0.4.51 (firmware 0.30.0)

- **A map stays on its tile** (discussion #105). A page with only maps on it could lose them: when ESP Screens could
  not hand over a picture once, the screen never asked again and showed the plain Home or Away tiles until you turned
  the page. From firmware 0.30.0 the screen asks again, after ten seconds and then a little later each time, and keeps
  the last map on the card meanwhile.
- **No empty moment when someone moves.** A map keeps the picture it shows until the next one has loaded, where the
  card could fall back to the plain tile in between.
- **The app keeps its address for pictures.** ESP Screens asks Home Assistant every ten minutes where screens reach
  it. When Home Assistant did not answer that once, pictures went out without a link; now the address from before
  stands. This part works on every firmware.
- A map that follows someone no longer fills the screen's picture memory: the pictures from before each move are let
  go once the new one is on the card.
- **Screensaver: a long title takes two lines.** A title too long for one line wrapped over the line under it. It now
  stands on two lines above that line, and one that needs still more ends in dots.
- Tested: on a Guition 4848S040 with Home Assistant on the bench. With ESP Screens made to answer without a picture,
  the maps stayed on their tiles, the screen asked again after 10, 20, 40 and 80 seconds, and the new map came by
  itself once pictures were back, without a page turn; firmware 0.29.0 showed the plain tiles for six minutes until
  the page was turned. Six moves in a row each loaded in two seconds and left one picture in memory. The screensaver
  was looked at with a short title, one of two lines and one longer still. The CYD, both Guitions and the Waveshare 7
  build with ESPHome 2026.9.0 (the CYD image is 94.2 % of its slot), the CYD and the Waveshare 3.5 with 2026.6.2. Not
  tested on a 10-inch screen or with cameras on the page.

## 0.4.50 (firmware 0.29.1 for waveshare35)

- **Waveshare 3.5 inch: the right colours** (GitHub #127, by @noisemaker00). Every colour showed as its complement,
  orange as blue and purple as green. The panel is now driven inverted, as it needs, confirmed on a real unit.
- **Its 8 MB of PSRAM is switched on**, in octal mode at 80MHz, also confirmed on a real unit. Nothing looks different
  yet: it is the memory that pictures (covers, cameras) need, which this board does not draw so far.
- Only Waveshare 3.5 inch screens are offered this update. Every other screen stays as it is.

## 0.4.49 (firmware 0.29.0)

- **A screen's first build is quicker.** Every night and with every release, GitHub builds each board ahead and
  publishes what it compiled. Before a build the app fetches that for your board (about 40 MB) and only compiles what
  is your own screen's: its name, keys, Wi-Fi and language. A CYD's build went from 93 to 58 seconds on a Mac, and a
  slower machine such as a Raspberry Pi saves more.
- Nothing to set and nothing to choose. Without a published cache for your board, without internet or when the
  download takes longer than five minutes, the app builds exactly as before. The firmware is the same either way.
- Building in the ESPHome Device Builder works as before, without this speed-up.
- Nothing changes on the screens.

## 0.4.48 (firmware 0.29.0)

- **A screensaver in standby.** When Auto standby dims a screen, it can show something calm instead of the dimmed
  tiles: the cover of the music that plays, a camera, or a large clock with the date. Choose a player and a camera in
  **Settings → Screensaver** and drag the three into the order you want: the screen shows the first one that is there
  right now, such as the cover while music plays, the camera when it stops and the clock when the camera is away.
- The cover and the camera fill the whole glass, a little darker so the title or the camera's name reads over it. On a
  screen much wider or taller than square the cover takes the full height or width, beside its own colour.
- Nothing on the screensaver can be pressed: a tap wakes the screen, as it always did. It keeps your Standby
  brightness and, at night, your Night brightness. The CYD and the other screens without memory for pictures show the
  clock.
- **The CYD dims evenly** (GitHub #42, #20). Its backlight was full at 100 % and nearly dark at 95 %, with little
  change below. It now runs at the frequency its backlight follows, so every level from 5 to 100 % steps evenly. The
  Hosyond 4-inch had the same and gets the same.

## 0.4.47 (firmware 0.28.0)

- **Swipe up from the bottom edge goes home from anywhere.** Over an open card, a camera, a player's library or the
  settings page, a swipe up from the bottom edge of the glass closes it all and shows the home page, as on a phone.
  Until now it only worked over the tiles. A swipe that starts on a slider stays that slider's.
- **Swipe down from the top edge opens the settings page** (GitHub #133). Holding the top bar still works too.
- On the CYD and the Hosyond both swipes start in a band along the top and the bottom edge; turning pages stays a flick
  anywhere over the tiles.

## 0.4.46 (firmware 0.27.0)

- **Every Sonos has its plus on the Spotify tile.** The speakers of Spotify's library showed a plus only once music
  already played on one of them, so there was nothing to tap to start a group. Now every speaker that groups has its
  plus at once: the first one starts what plays (or the next playlist you tap) on that speaker, and the next ones join
  it.
- **The speaker's name stays whole.** With the input key and the library key both at the top, the pill with the
  speaker's name was cut short ("Sla..."). It now takes the room between the back key and those two keys.
- **More speakers on a page.** A speaker's volume line in the menu is a little lower, so the Guition shows a group of
  three and the fourth speaker on one page. Its slider still reacts across a finger's height.
- **A coffee card on the overview.** The editor's home overview shows a small card at the bottom right with a link to
  support the project. It waits two days after your first visit, never shows while you edit a screen, and stays away
  for good once you say you already donated. Only your browser remembers the choice.

## 0.4.45 (firmware 0.26.0)

- **Play your speakers together.** The speaker menu on a player's card now groups, the way Home Assistant's own join
  dialog does: a player that reports grouping (Sonos and others) lists the players of its own integration that do too.
  A speaker in the group has a filled tick and its own volume under its name, the others a plus; the plus adds one at
  once, the tick takes it out, and the pill at the top names the group ("Living room + 1"). A tap on the name of a
  speaker already in the group does nothing, so a finger that misses its volume never breaks the group. More speakers
  than the glass holds go on pages, as the rest of the screen does.
- **Spotify on a Sonos.** Spotify Connect rarely lists a Sonos, but Home Assistant's Sonos integration lists your
  Spotify account in every Sonos's library once Spotify is linked in the Sonos app. The Spotify tile now offers those
  speakers next to its Spotify Connect devices: pick one and what plays moves there, a playlist or album from the
  library plays there, and the card follows that speaker (its cover, its keys, its volume) until Spotify plays on its own
  again. The speakers in that group join and leave as above. A favourite can have such a speaker as its own.
- **Inputs behind their own key.** Home Assistant's `source` is a player's input, so a Sonos's TV input and favourites,
  or a TV's ports, showed up as speakers in the pill. They now sit behind an input key at the top of the card, with
  Home Assistant's own icon for it, and the pill keeps the speakers. Spotify's sources stay speakers, since they are
  the Spotify Connect devices. A screen on older firmware keeps the menu it had.
- **Credit.** Playing speakers together, a volume per speaker and Spotify on a Sonos follow the media player work of
  @woozer in [#87](https://github.com/MaxGramser/homeassistant_espscreen/pull/87). Thank you!

## 0.4.44 (firmware 0.25.0)

- **A heat/cool range on the thermostat card, as a band.** A thermostat set to a range (heat/cool, with a low and a high
  target) showed its two targets as two small numbers above one "Target", and one pair of -/+ keys that moved whichever
  end was last tapped, which only a fainter shade told apart. The card now shows one big number and, under it, the
  device's whole span as a band with the degrees along it: the heat colour runs from the minimum up to the low target,
  the cool colour from the high target up to the maximum, and the bare track lies between them, as Home Assistant's own
  thermostat draws it. A knob stands on each end; tap one and the number, the -/+ keys and the knob take that side's
  colour, so what a key moves is always in sight. While the room is colder than the low target or warmer than the high
  one, the part the device has to cover is drawn in full with a mark at the room's temperature. A thermostat with one
  target draws exactly as before. The band is LVGL's scale, new in every board's firmware; the CYD stays within its
  flash budget.

## 0.4.43 (firmware 0.24.0)

- **The media card sits on one dark colour from its cover** instead of a gradient (#135). Screens draw 16-bit colour, and
  a gradient between two dark colours has only a few steps in it, so it showed as broad bands across the card, on the
  CYD and on the large screens alike. The ground is now one dark shade of the cover's leading colour: no bands, and the
  rounded corners of the cover match the ground behind them, where a square edge showed before. It comes from the app,
  so screens on firmware 0.24.0 get it without an update.

## 0.4.42 (firmware 0.24.0)

- **The media card plays on the colours of its cover.** The card of a media player sits on a ground taken from the
  cover that plays, with the speaker it plays on at the top: tap it to move the music to another one. Shuffle, repeat
  and a bar you drag through the track are under the title, where the player has them.
- **Your library on the screen.** The library key on the card opens what Home Assistant can browse on that player,
  folder by folder (playlists, artists, albums and the rest), down to a page of covers with page dots for up to 48 of
  them. A tap on a cover plays it on the speaker the card shows. Nothing is made for one service: it is the player and
  its library as Home Assistant reports them.
- **Favourite tiles.** A media player tile can be a favourite now (Display → Favourite): choose a playlist, album or
  artist from the player's library in the editor and, if you like, the speaker it plays on. A tap starts it; the
  favourite shows its cover behind its name, a play key, and a ring while it plays. Its picture waits with the same
  spinner as every picture card.
- **Spotify at rest keeps its card** (#88). A Spotify player that plays nothing still offers its library and its
  speakers, so you choose a speaker and start from the screen, where the card used to have no keys at all.
- **Cover is the default for a new media tile** on a screen that shows pictures. Tiles you already have stay as they
  are; on the CYD and the other screens without pictures nothing changes.
- The covers and the library need a screen with the memory for pictures. The CYD keeps the card on its cover colours,
  the speakers and the favourites, drawn with icons.
- Tested: on a Guition and a CYD on the bench with Spotify through Home Assistant: the card, the speakers, the
  library, favourites, an alert camera and a camera full screen while covers load, and on the CYD 47 tiles through
  restarts and resets. The CYD image is 92.9 % of its slot, 25 KB more than firmware 0.23.0.
- **Credit.** Seeking through a track, the speaker at the top of the card and the cover-led player follow the media
  player work of @woozer in [#87](https://github.com/MaxGramser/homeassistant_espscreen/pull/87). Thank you!

## 0.4.41 (firmware 0.23.0)

- **The editor draws what the screen draws, to the pixel.** A new check compares the editor's sizes and colours with
  the firmware's own code on every board, and it found five places where the editor was slightly off:
  - a lamp's colour on its tile, by one step in a few thousand colours;
  - a battery without a charge, which the editor showed red at 0 % where the screen shows no charge;
  - the widths of cards on a five-column screen such as the 10.1-inch Guition, where a column could be a pixel wider;
  - the home mark in the top bar of the 7-inch Waveshare, Waveshare 7B and Sunton screens;
  - a tall tile offered on a grid too small to hold it.
- **Firmware 0.23.0 tidies the code, with nothing new on the glass.** The alarm panel, the lock and a light's effects
  page now read Home Assistant's feature flags by their names from the tile catalogue, as the rest of the firmware
  already did. Update when it suits you.
- For contributors: the documentation now describes the project as it is built today, with an index in docs/README.md
  and a list per recipe of every place a change touches. New checks keep the editor and the firmware in step, test
  every tile type on every board, keep the flash of every 4 MB board within budget, and compare the tile catalogue with
  each new Home Assistant release every week. On the oldest ESPHome the packages support, a change for every board now
  builds one board instead of four.
- Tested: the CYD, both Guitions and the Waveshare 7 build with ESPHome 2026.9.0 (the CYD image is 1,678,864 B, 91.5 %
  of its slot, the same as firmware 0.22.0), and the CYD, the Guition 4848S040 and the Waveshare 7 with 2026.6.2.

## 0.4.40 (firmware 0.22.0)

- **The editor on a phone is about your screen now.** On a phone the editor opens on the screen as it stands on the
  glass, one page at a time, with one button under your thumb: **Add tile**. Swipe for the next page; tap the page's
  name under the screen for the list of pages, to go to one, move it by its handle or add one.
- **Adding a tile** opens a sheet that says where the tile goes, with the search and the kinds of entity as chips. One
  tap adds it: the sheet closes, the new tile lights up for a moment and Undo is beside the message. A tap on an empty
  place adds the next tile right there. Once something changed, the button at the bottom is **Save & send**.
- **A tile's settings** open as a sheet over the lower half, so the screen above it shows every change: its name, icon
  and colour first, then **Move** to another page and **Remove**. **More settings** opens every other setting, as on a
  computer.
- **Everything else is in the screen's ··· menu**: preview, undo and redo, add a page, pages and order, the top bar,
  screen settings and rename, and what the menu held already. The overview's ··· holds search, alerts, settings and a
  new screen.
- **Full editor** in that menu brings back the editor of a computer on that phone, and **Simple view** returns. The
  phone remembers the choice. A computer and a tablet keep the editor exactly as it was.
- Nothing changes on the screens.

## 0.4.39

- **New licence.** From this release Tessera is licensed under the GNU Affero General Public License v3.0 instead of
  the MIT License. Using, changing and sharing it stays free, also commercially, but whoever passes on a changed version,
  on a device or as an online service, shares its source under the same licence. Releases up to and including 0.4.38
  stay under the MIT License. NOTICE lists the third-party code and its licences.
- Nothing changes on the screens or in the editor.

## 0.4.38 (firmware 0.22.0)

- **Remotes in the library** (#117). A remote (`remote.*`, such as a Harmony hub, an Android TV, or a Broadlink or other
  IR blaster) is a tile now, with Home Assistant's icons and colours: amber while on, the crossed-out remote while off.
  A tap opens its card, as Home Assistant's tile card opens its dialog: the power key in the top bar, where the light's
  and the thermostat's have theirs, and the remote's activities where it has them (Harmony, Android TV Remote), each of
  which turns it on with that activity. The tile names the activity it runs. Set the tap to **On / off** to switch it
  with a tap instead; a wide tile carries the switch.
- **A remote you hold in your hand, on the glass.** For a remote whose commands Home Assistant's source names (Apple TV,
  Android TV, Roku, Sky, DirecTV, LG, Panasonic, Vizio, Xbox, Kaleidescape, JVC, Lyngdorf) the card is a keypad: a
  ring of four arrows round OK, and Back, Home and Play/Pause with the volume beside or under it. Each key sends the
  command that integration takes for it, and only the keys it has are drawn: a Sky box gets no volume keys, a projector
  Back and Menu. Every screen keeps one arrangement for every remote, from what its glass holds: a column on each side,
  a row under the ring, or two rows on narrow glass standing up. Keys go out at once, also several in a row.
- **A key of a remote is a tile of its own**: set its tap to **Perform action**, choose **Send command** and pick the
  command, with the device for a Broadlink. Give each key its own name and icon.
- **The commands each remote takes, from Home Assistant's source.** For thirteen integrations (Android TV Remote, Android
  TV, Apple TV, Roku, Sky, DirecTV, LG Netcast, Panasonic Viera, Vizio, Xbox, Kaleidescape, JVC, Lyngdorf) the command
  field lists what the remote takes, filtered as you type. The lists are read from Home Assistant and the exact library
  version each integration pins (`tools/read_remote_commands.py`), so they follow Home Assistant when it updates. Where
  only the hub, the learned codes or your own configuration know the names (Harmony, Broadlink, Bravia) or any text goes
  (Samsung, Philips), you type the command; a typed command always goes as typed.
- A remote's "on" says the remote may send, not that the device behind it runs: a Broadlink that is off drops every
  command. Name the tile after the remote, and power the player with a command tile of its own.
- Needs firmware 0.22.0: a screen with a remote tile is offered the update before its layout goes out. CYD image is
  1,678,864 B, 91.5 % of its slot, 10.2 KB more (the keypad and its icons). Built: CYD, Guition 4848S040, JC8012P4A1,
  Waveshare 7.

## 0.4.37 (firmware 0.21.0)

- **The editor on a phone** (#124). On a narrow window the library stood in the middle of the page with the pages
  running on underneath it, out of reach. Now the page scrolls as a whole and the library stays along the bottom of
  the window, folded to its head or opened over the last few rows, and the pages scroll clear above it. Its kinds and
  rooms, hidden on a phone until now, are a row of chips above the list that you swipe sideways. No screen update
  needed.

## 0.4.36 (firmware 0.21.0)

The map grows up: a map tile of its own, a tap that opens it over the whole screen, people's photos, and many ways to make
it yours.

- **Tap a map to open it over the whole screen**, as a camera tile opens: drawn as large as the board takes a camera
  picture, with the back key and the name at the top. A small 1 x 1 map you glance at becomes a full map with a tap.
- **Tap someone on the full map** to focus on them, as Home Assistant's map does: they stay exactly on their place in the
  middle, closer in, with a card over the bottom in the style of the light's effects page: their state with Home
  Assistant's icon and since when, the battery where they report one, and the day's changes with their times. A tap
  beside them, or Back, shows everyone again.
- **A person tile opens where they are**: a tap shows the map focused on them with that card; holding the tile opens
  its card with the history, as before. On a screen without pictures a tap still opens the card.
- **The map tile**: **Map** under the screen's own cards in the library. It follows **everyone** Home Assistant knows the
  place of, as Home Assistant's own map card does, or only whom you choose: just the two of you, or only your devices.
- **Photos in the markers**, as Home Assistant shows them: a person with a picture in Home Assistant has it in their
  marker, everyone else their initials (the first letter of each word of their name, as Home Assistant writes them).
- **As Home Assistant places people**: someone without GPS who is in a zone stands in the middle of that zone, a tracker a
  person already follows is not shown twice, and everyone has the same colour as on Home Assistant's own maps, in the
  order they were made. A faint circle shows a GPS accuracy wider than the marker.
- **More choices** in the tile's new **Map** section: markers with photos or initials, names beside them where there is
  room or always or never, zones on or off, streets or a plain ground, and a look of its own (as the screen, light or dark).

## 0.4.35 (firmware 0.20.0)

- **A phone, a car or a tag on the map.** **Also on the map** now offers Home Assistant's device trackers that report a
  place, beside people: the car on the drive, a phone without a person, a tag on a bag. Each gets its own colour and
  marker, and the map is drawn again when it moves. A tracker that only knows home or away has no place and is not
  offered. No screen update needed (firmware 0.20.0).

## 0.4.34 (firmware 0.20.0)

- ESP Screens 0.4.33 did not start: the map card looked for its font outside the app. The app now carries the font
  itself. The screens' firmware is unchanged (0.20.0).

## 0.4.33 (firmware 0.20.0)

A map of where everyone is, drawn in your screen's own colours.

- **A person tile can be a map.** Set its display to **Map** and it shows the streets around them, your zones, and a
  marker with each person's initials in their own colour. **Show** frames everyone on the card, the area around home, or
  the area around that person; with the last two, **Distance** picks street, neighborhood, town or region, and someone
  outside the view is a small marker on the edge, pointing the way. **Also on the map** adds up to seven more people.
  It works on every tile size, from one cell to the whole page, on every screen that draws pictures.
- **Calm, and in your screen's colours.** The streets come from Home Assistant's own map (its `map_tiles` integration,
  from OpenStreetMap) as plain data, and ESP Screens draws them itself: quiet greys and white streets, water and green in
  soft tints, and strong colour only for the people. A screen in Dark mode gets a dark map, and each screen gets the look
  it is in, also when two screens show the same card in different looks.
- **Only when someone moves.** A map is drawn again when someone on it moves more than about 25 meters, changes state or a
  zone changes, never on a clock. The screen gets a picture and never a location. docs/MAP.md has the details.
- Thanks to @stevenhorner for the idea and the first version of a map card (discussion #105), which showed how it could
  work: the framings, the people riding along and the movement mark come from it.

## 0.4.32 (firmware 0.19.0)

The editor, calmer and quicker to use, and a screen that says what is wrong when it cannot reach its Wi-Fi.

- **A screen without its Wi-Fi says so on its glass** (firmware 0.19.0). Once its fallback hotspot is up, the loading
  screen reads "Wi-Fi connection problem" with the hotspot's name and password to join from a phone and pick the right
  network. A board without a hotspot (the CYD and the other boards with 4 MB of flash) says it after a minute, with the
  way back: check the Wi-Fi name and password and install the screen again over USB. When the Wi-Fi is back, so are
  the pages.
- **New screen follows the screen onto your Wi-Fi.** After the firmware is on it, the page waits for Home Assistant to
  find the screen on the network and says when it did. After three minutes without it, it says the Wi-Fi is the likely
  cause and what fixes it, with the right network and the installation again in one form.
- **Another network**: when Wi-Fi is already set up, New screen can still take another name and password. They go into
  ESPHome's secrets.yaml, so screens you already have take them at their next update.
- A long device name no longer makes a hotspot name ESPHome refuses (over 32 characters).
- **A screen that never got its firmware can be removed** (GitHub #114): when New screen's build was cancelled or failed, the
  screen waiting in the list has Remove, which takes its profile and what it built out of the ESPHome folder.

- **The library is a drawer along the bottom.** Folded it is one line with the search. Start typing anywhere on the
  page and it glides open on what you typed; the arrow keys walk the results, Enter adds the one in focus, Escape
  clears the search and then folds the drawer. Drag its top edge to make it taller; the editor remembers both.
- **Entities stand under their room**, with the screen's own cards last. The kinds and the rooms are one column on the
  left, each with how many it holds. A search ranks what it finds, names that start with your words first.
- **Shorter names**: an entity no longer repeats its device's name. "Bedroom screen Night mode" reads "Night mode", with
  "Bedroom screen" under it, as on the device's card in Home Assistant.
- **The settings of what you select have a column of their own on the right**, gliding in and out. They never cover
  the pages or the library.
- **A choice shows on the tile before you pick it.** Rest the pointer on a display, a second line, a control, an icon or
  a colour and the tile in the page draws it.
- **Each setting is one row**: what it is on the left, the current choice on the right. A label with more to say is
  underlined with dots; point at it to read it. What holding the tile does stands under the tap choice.
- **A tile's settings no longer ask which page it is on**: drag it there, as you would anyway.
- **The tile's name is edited in the title** of its settings. Read current data and Remove moved into the ··· menu,
  and Delete or Backspace removes the selected tile (Undo brings it back).
- **You see at once what is open**: the head of the settings is black for a tile, blue for a page and white for the top
  bar, with its word over the title, and the ring around it in the pages follows.
- **A tile is sized with its handles, to any rectangle** (firmware 0.19.0). Drag its right or bottom edge: besides
  the sizes there were, it takes 3 x 2, 2 x 3 and every other rectangle smaller than the page, and the whole page
  too. The size choice left the tile's settings. A screen says which rectangles its grid takes, so an older screen
  keeps the five sizes it knows until it is updated.
- **A calmer sidebar.** Each screen is one line, its name in full. The update's button is a small icon on its row
  (its version in the tooltip), and a screen that is away says Offline there. The details fold out from the chevron:
  the room, firmware and board, what's new as a few headlines, then Rename, Download screen files and Remove as the
  rows of a menu. New screen is the + beside Screens; Refresh comes beside it under the pointer. Search is a row like
  the others.
- **New screen is a setup assistant in three steps.** Screen: every board drawn as it hangs and to scale against the
  others, found by brand, size or what is printed on it, or narrowed by size. Set up: the name appears on the drawing
  of your screen as you type it, beside which way it hangs and the board's own choices; the device name and what the
  board can do are under Advanced. Install: USB on Home Assistant (a port it found has a green light), this
  computer, a file, or later. A preview screen is one link on the first step.
- **The installation shows how far it is.** Getting ready, building the firmware, putting it on the screen and
  starting up, each with its percentage from ESPHome's own count, one bar for all of it and the time so far, while
  the drawing of the screen fills in tile by tile. Show details opens ESPHome's log in a terminal with a copy button.
  When it is done, what comes next; when it fails, the step it stopped in in red and Retry.
- Escape closes only the innermost thing open: a list of choices closes and the settings under it stay.
- A preview screen saved in the browser by an older app, that this one cannot read, is left out with a word about it,
  and no longer keeps the editor or the other preview screens from loading.
- Calmer greys, thinner lines and smaller corners throughout.
- **An automation or assistant can ask for any size too**: `esp_screens_add_tile` takes `size: 1x3` and the like. A
  rectangle a name already says becomes that name (`2x3` on a screen two by three is the whole page), and a size the
  screen does not take is refused with the sizes it does take, where it used to say the page was full.
- A screen that is not ready for a tile size now says "Update the screen to use these tile sizes", not "taller tiles".
- New screen's hint under USB on Home Assistant points to "From this computer", as the card is now called.
- The drawing of the new screen ends a long name with dots, as the screen does, instead of cutting it off.
- The screen's log says when it shows the Wi-Fi message and when the pages come back (firmware 0.19.0).
- **A thermostat that keeps the room between two temperatures works** (firmware 0.19.0), such as one in Heat/Cool. Its
  tile no longer shows the raw `heat_cool`: as on Home Assistant's own tile it says its state and the room's
  temperature, "Heat/Cool · 22°". Between its - and + stands the end they move: its temperature, as large as a single
  temperature stands there, with a flame for the heating's end or a snowflake for the cooling's before it where there
  is room, or on its own in that end's colour. A tap on it switches ends, and both ends go to Home Assistant together.
  The number is sized by the widest temperature the thermostat can reach, so it keeps its size from one tap to the
  next. Its card shows
  both ends side by side, as Home Assistant's thermostat card does: tap one and - and + move it. A thermostat with a
  single temperature is unchanged; one that has both follows Home Assistant and uses the single one when it reports
  it. A screen that is not updated yet leaves the - and + off such a thermostat, instead of sending a single
  temperature it cannot take.
- A thermostat's temperatures read as Home Assistant writes them: 22° and 21.5°, no longer 22.0°. One that names no
  step moves as Home Assistant's own controls move it, a whole degree in Fahrenheit and half a degree otherwise.
- A thermostat in a mode without a temperature to reach, such as dry or fan only, says that mode and the room's
  temperature instead of the raw state.
- **The editor draws a tile's controls at the screen's own size**: the - and + with the number or the chip between
  them, measured by the board's own fonts, and a wide tile's keys as the screen draws them for that entity, only the
  modes a thermostat has and only the keys a vacuum or a blind can use, in place of a fixed row of three.
- A click on a page between its tiles, or on the line above it with its name ("Page 3"), opens the page's settings.
- **A thermostat's modes are one bar** (firmware 0.19.0): "Mode" on its own is the same bar as under the - and + of
  "Temperature and mode", on every size. It holds as many modes as the card's width fits, heat and cool first and the
  mode it is in always among them, and "…" opens the card for the rest. Off is the tile's circle, as on Home
  Assistant's own tile. It used to show two modes and "…" whatever the room.
- The editor draws the mode bar and a range's temperature at the screen's own sizes, worked out from the board's
  spacing, so it shows as many modes as the screen does.
- The editor's toolbar stays where it is while you scroll along the pages, and dragging the edge of the library no
  longer selects text on the page.
- Tested: tools/check.sh (with the new layout audit and the tile catalogue's checks), the firmware of the CYD, the 4-inch
  Guition and the 7-inch Waveshare with ESPHome 2026.9.0 and 2026.6.2, and of the 10.1-inch Guition with 2026.9.0 and
  2026.8.0, the oldest it takes (CYD 90.6 %, 7.5 KB more than 0.4.31). The update as it reaches people, on a Guition
  and a CYD with a Home Assistant of their own: app 0.4.31 with firmware 0.18 and eight pages of thermostats and tiles
  with their options, then this app (both layouts unchanged to the byte, both screens in sync, the firmware update
  offered, the same 77 entities in Home Assistant, the editor without an error), then this firmware (the same layouts
  back, the new sizes offered, every setting kept). Earlier the same route over the air, spans saved from the editor's
  handles and through the tile events, 40 saves in a row, saves to both screens at once, and the app, both screens and
  Home Assistant restarted during a delivery, each ending with the last layout on the glass. A wrong Wi-Fi password on
  both: the CYD says so after a minute, the Guition when its hotspot opens, neither restarts.
  Thermostats on the Guition's glass (a range-only one, one with both, one with a single temperature) and a range set
  through the firmware preview's card: the high end up two and the low end down one reached Home Assistant as both ends.
  Both mode controls and the range's temperature laid out on every board and size by the layout audit, and rendered on
  the Guition's and the CYD's glass through the firmware preview beside the editor's mockup, which matched.
- For developers: **what a tile of each entity type can do is written once**, in `catalogue/`, one file per type,
  and the add-on, the editor and the firmware read it (docs/CATALOGUE.md). What Home Assistant's devices support, the
  feature flags and which action needs which flag, is read from Home Assistant's own source code
  (`tools/read_ha_source.py`), never copied by hand. A type exists only where it has a file, and a new one says from
  which firmware a screen draws it. Every tile app 0.4.31 could save, about 16,000 of them, is checked against what
  that release stored and sent, so an update keeps every layout as it was.
- For developers: tests/test_layout_audit.py lays out every kind of card at every size on every board's glass, lying
  down and standing up, with the firmware's own code (the WebAssembly preview) and checks the geometry without a
  picture: nothing leaves its card, no text runs over another or is cut without dots or a marquee, texts keep a margin
  from the edge, and full pages of cards never overlap. About 3,100 layouts in under a minute, part of tools/check.sh.

## 0.4.31 (firmware 0.18.1 for guition)

- **Four rows on the 4-inch Guition, as a choice.** New screen asks how many tiles go on a page: two columns of three,
  as before, or of four with smaller tiles, for a screen with many switches. Every card works in every size on four
  rows too. The choice is one line in the screen's own YAML (`GRID_ROWS: "4"`), and a screen already built with three
  rows gets four by adding that line and installing it again: its saved layout moves on to four rows by itself.
- An offline screen built with four rows keeps its own grid in the editor; the app reads it from the screen's YAML.
- Only the Guition gets new firmware (0.18.1), which is the same as before for a screen with three rows. Other screens
  get nothing new.
- Tested: tools/check.sh with new tests (the choice in New screen, the line in the screen's YAML, the eight cards the
  board takes on four rows, the grid of an offline screen), the Guition built with three and with four rows on ESPHome
  2026.9.0 and 2026.6.2, and rendered with four rows. Not yet seen on the glass of a Guition with four rows.

## 0.4.30 (firmware 0.18.0)

- **Every screen has eight pages, and a page need not be full.** A screen holds 64 tiles over up to eight pages, on
  every board. Before, a bigger grid had fewer pages: as many as 64 tiles fill, so three on the 10.1-inch Guition and
  seven on the Waveshare 4.3-inch. A page with a few tiles is fine now. A screen on older firmware keeps its old limit
  until it is updated, and the editor offers it no more pages than it takes.
- **The 10.1-inch Guition is five by five**, lying down and standing up (all three: JC8012P4A1, V2 and V3). Before it
  was five by four lying down and four by five standing up.
- **A saved layout moves on to a bigger grid by itself.** When a screen reports more rows or columns than its layout
  was made for, ESP Screen Manager moves the layout to the new grid: every tile keeps its page, its row and its
  column, and the new cells stay empty. Before, the screen waited for someone to review the change in the editor. A
  grid that gets smaller still asks for that review.
- Tested: tools/check.sh with new tests (the page limit per firmware in the add-on, the editor and the firmware, a grid
  that grows, delivery to firmware that does not take the pages yet), the firmware of every board on ESPHome 2026.9.0
  and 2026.6.2, and the 10.1-inch Guition rendered lying down and standing up. Not yet seen on the glass of a
  10.1-inch screen.

## 0.4.29 (firmware 0.17.0)

A new board, experimental: the Guition JC8012P4A1 V2 (GitHub #92).

- **Guition JC8012P4A1 V2** in New screen, as **Guition · 10.1 inch** (JC8012P4A1 V2): the 10.1-inch Guition with the
  first build's early ESP32-P4 and the newer LCD of the V3 (a label saying V2, a case number of 2628 or higher). On the
  first build's firmware this LCD showed a washed-out picture with a coloured line across it, and the V3's firmware does
  not start on this chip. The V2 runs the V3's LCD table and touch driver on the first build's chip, with ESPHome's own
  display driver. docs/JC8012P4A1.md says how to tell the three builds apart and what to report.
- Nothing changes for a screen you have: no firmware update.
- Tested: the board builds with ESPHome 2026.9 (2,672,528 B, 32.9 % of its 8 MB slot) and with 2026.8.0, the oldest it
  asks for, and its render check passes lying down and standing up. Not yet seen on the glass of a V2.

## 0.4.28 (firmware 0.17.0)

A new board, experimental: the Sunton ESP32-8048S070 (GitHub #94).

- **Sunton 8048S070** in New screen, as **Sunton · 7 inch** (ESP32-8048S070): 800 x 480, four by four tiles lying down
  and two by seven standing up, at the tile size of the 7-inch Waveshare. Its backlight dims, so brightness, standby and
  night mode are all there. docs/SUNTON8048S070.md has the details and what to report.
- Nothing changes for a screen you have: no firmware update.
- Tested: the board builds with ESPHome 2026.9 (2,138,128 B, 26.3 % of its 8 MB slot) and with 2026.6.2, and its render
  check passes lying down and standing up. Not yet seen on the glass of this board by the project: the panel is
  ESPHome's own ESP32-8048S070 model, the touch bus and backlight pin follow a configuration a board owner ran.

## 0.4.27 (firmware 0.17.0)

- **A lamp, a switch, a script or a scene two cells high is one big key.** On a tile of 2 x 2 or 1 x 2 cells the card
  shows a large circle, the name and the state, like the tile over a whole page, and the whole card is what you tap. A
  tile with a control on it (a dimmer, the volume, a vacuum's keys) keeps its controls as before.
- **The flip clock fills a wide card.** On a card as wide as the page and two rows high, or a whole page, the two blocks
  share the width and the day and AM or PM stand on one line under them: a bedside clock of your own, with tiles under it.
- **The bedside clock** (GitHub #93):
  - AM or PM stands under the end of the time. Beside it, a time from 10:00 to 12:59 ran off the glass.
  - The keys under the clock open their own settings and drag to another place or to an empty cell. A click on a key or
    an empty place opened the clock instead, and dragging a key dragged the whole clock.
  - **Name under the key** can be turned off per key; the circle then stands alone.
- **A screen can do without a title.** Leave the screen title empty and the top bar shows only the logo. Pages with a
  title of their own still show it.
- **Download screen files.** A screen's details in the sidebar download its ESPHome YAML, its Override YAML and a
  `secrets.yaml` with only the secrets they use, to build the screen with ESPHome on your own computer.
- A tile's new background shows on the screen straight away. A change of background alone waited for the entity's next
  state, so an idle timer, or any tile whose state stood still, kept its old colour.
- Dragging a tile that fills a page shows where it can go: a page that has tiles says it has no room, and a drop tells
  you so, instead of nothing happening.
- **One fixed set of font sizes.** Every board renders the same short list of text, digit and icon steps, and a new card
  takes the largest step that fits instead of bringing a size of its own. The flip clock and the bedside clock share the
  large digits, so the bedside digits are a little smaller on the 4-inch Guition (164 to 153 px) and the CYD (81 to 73
  px); larger screens keep theirs. A tile name with room on the CYD is no longer bold. The CYD firmware is 19.5 KB
  smaller (90.1 % of its slot).
- The editor's mockup draws all of this as the screen does, a script tile says "Never run" and "Running" in the screen's
  language instead of a text key, and a change to a key under the bedside clock keeps its panel open.
- Tested: tools/check.sh with new tests (the font set, the big key, the flip and bedside layouts, key names in the add-on
  and the editor, the empty title, the screen files, the paint repaint, dragging a key). Every design rendered from the
  firmware's own code on eight boards before it was built; on a Guition 4848S040 and a CYD ESP32-2432S028R with firmware
  0.17.0 and a Home Assistant OS bench: a timer's new background, the empty title, the flip clock and the big key on the
  glass, and the screen files built with ESPHome on a Mac.

## 0.4.26 (firmware 0.16.0)

- **One entity on several tiles** (GitHub #83). A light can now be a small tile on page 1 and a tile with its slider on
  page 3, a camera can be on two pages, and a whole page can be copied with its tiles. Every copy has its own name,
  icon, colour, size and tap. The library keeps offering an entity that is already on the screen and marks it with a
  check, or with how often it is there. Only the bedside clock is on a screen once. It needs firmware 0.16.0; an older
  screen asks for its update first.
- On firmware 0.16.0 a lock's "tap again to unlock" counts only on the tile you tapped, an alarm going off opens its
  card once, and each copy of a camera on a page gets its own picture and its own fit.
- A lock or alarm panel no longer keeps a pulsing ring after it settled while its page was out of view. The ring stayed
  with the place on the screen instead of the tile, so a page that came back could show the old animation.
- `esp_screens_add_tile` now always puts a new tile on the screen, also when the entity is there already. To change a
  tile through an event, remove it and add it again. On firmware older than 0.16.0 it works as before.
- Tested: tools/check.sh with new tests for copies (validation, tile events, delivery to old and new firmware, live
  pictures by tile, page copies, the editor's library and page menu). On a Guition 4848S040 with firmware 0.16.0 and a
  Home Assistant OS bench: a lamp, a lock, an alarm panel and a camera on several pages, a whole page copied in the
  editor, and a page with the same camera twice. A lamp switched in Home Assistant changed on every copy, also on a page
  that was not on screen; tapping one lock copy and then another did not unlock, and each copy kept its own "unlock
  never" setting; the alarm going off opened its card once; each camera copy and each album cover copy showed its own
  fit, name and tile colour. A screen put back on firmware 0.13.0 was asked to update first and got nothing, then took
  the layout with copies once it ran 0.16.0 again. Checked by hand on the Guition and on a CYD ESP32-2432S028R: lamp
  copies switch together, a lock opens only on two taps on the same copy, the card and the effects page of a copy carry
  its name, and an alarm going off opens its card once on each screen. Every board builds; the CYD firmware is 16 bytes smaller
  than 0.4.25's (91.2 % of its slot).

## 0.4.25 (firmware 0.15.0)

- **The top bar lines up with its logo, and its text no longer touches the tiles** (GitHub #90). Since 0.4.23 the
  page's name and the items on the right stood on the logo's bottom line, so they looked low next to it, and on the
  compact look (the CYD and the Hosyond 4.0) the tail of a g, p or y touched the first row of tiles. Now the name, the
  words and icons on the right and the analog clock all share the logo's middle line, and the tiles start one row gap
  below the lowest a title can reach, never closer than 1.5 mm. The room follows from the fonts, so it is the same on
  every page, in every language and on every board. The tiles keep all their height on the larger screens compared
  with 0.4.22 and before; on the compact look they give back about 2 pixels of what 0.4.23 took from under the text.
- Tested: tools/check.sh, and the host renders of the Hosyond 4.0, the CYD, the Guition 4848S040 and the Waveshare 4.3
  with a temperature, the date and the clock in the top bar: every self test passes, the name, the clock and the
  icons sit within 1.5 pixels of the logo's middle, and 9 to 14 pixels stay free under the tail of a g. A Guition
  4848S040 runs it with its own layout. The CYD firmware is 336 bytes smaller than 0.4.23's.

## 0.4.24 (firmware 0.14.0)

- **Album covers, station logos and camera pictures follow the app's port** (GitHub #84). Home Assistant OS lets you
  publish the app's picture port 8098 under another number in its network settings, for example when another app
  already uses 8098. The screens were still sent links on 8098, so they asked the other app for their pictures and
  showed none. The app now asks the Supervisor which port it published and puts that one in the links. Docker keeps
  `SCREEN_CAMERA_PORT` and `SCREEN_CAMERA_URL` as before.
- Tested: tools/check.sh, with new tests for a port published as 8099, a Supervisor that answers nothing usable
  (8098 as before) and Docker's own setting. On a Home Assistant OS bench with the port published as 8099 (8098
  closed), a camera alert on a Guition 4848S040 showed its picture.

## 0.4.23 (firmware 0.14.0)

- **Taller tiles on every screen.** Less of the glass goes to space around the tiles, and more to the tiles
  themselves. The bar with the page arrows and dots is now at most 7 mm high, enough for a finger, where it was about
  9 mm. The tiles start right under the top bar, one gap below it. A Guition 4848S040 gets about 8 pixels more height
  per tile, a Waveshare 4.3 about 13, the 10.1-inch Guition about 6, and no tile on any board gets smaller, lying
  down or standing up.
- **One line for the whole page.** The top bar, the tiles and the page arrows now keep the same distance from the edge
  of the glass, and the top bar keeps it from the top as well. The margin and the gaps between the tiles keep their size
  in millimetres on every screen, but never take more pixels than before.
- Tested: tools/check.sh, and the host renders of the Guition 4848S040, the CYD, the Waveshare 4.3, the Waveshare 7 and
  the 10.1-inch Guition: every self test passes, and the top bar, the tiles and the page arrows line up on each. A
  Guition 4848S040 runs it and draws its pages; the lower page bar has not been tried by hand yet. The CYD firmware grows
  by 752 bytes.

## 0.4.22 (firmware 0.13.0)

- **A camera on full screen stays whole when Home Assistant or ESP Screens restarts.** A picture that broke off halfway
  through its download made the screen let go of the picture it was showing. The old picture stayed on the glass, but
  every part of it drawn again after that came out black: when the tiles below went unavailable, their icons and
  states showed through the camera as black blocks. The full screen now draws a copy of its own, as album covers and
  live camera tiles already did, so a broken download leaves the last picture as it was until the next one arrives.
  While the camera is open this costs one more picture in PSRAM (from 300 KB on a Guition JC3248W535 to 1.25 MB on
  the 10-inch), which is freed again when it closes; the memory inside the chip is not touched.
- Tested: tools/check.sh, and every board built on ESPHome 2026.9.0 and on the oldest ESPHome it asks for (the CYD
  stays at 91.2 % of its flash). On a Guition 4848S040 with a Home Assistant bench, the add-on was stopped halfway
  through a picture of an open camera: with the camera alone, over a page with a live camera tile and an album cover,
  and over a camera alert. Each time the picture stayed, only the download's own memory was freed, and new pictures
  came once the add-on was back. A camera alert over an open camera closes it and frees its memory, and ten opens and
  closes in a row started from the same free PSRAM within 20 bytes.

## 0.4.21 (firmware 0.12.0)

- **The top bar sits as far from the top as from the sides.** There was more room above the top bar than beside it
  (24 against 16 pixels on a Guition 4848S040, 13 against 11 on a CYD). The bar now keeps the same margin all round,
  and the tiles start that much higher, so every tile gets a little taller. This holds on every board, whatever its
  density.
- Tested: tools/check.sh, and the host renders of the Guition 4848S040, the CYD, the Waveshare 4.3 and the Waveshare 7:
  every self test passes and the top bar's margin above equals the one at the sides (16, 11, 20 and 13 pixels).

## 0.4.20 (firmware 0.11.0)

- **Preview fits its screen again.** The Preview dialog took a style meant for another part of the editor, so on a
  tall window it stretched to the full height with empty space between its parts and the close button next to the
  title. It now sizes to the screen it shows. Nothing changes on a screen.
- Tested: tools/check.sh, and the add-on on a Home Assistant bench: Preview opened on a Guition 4848S040 at a tall
  window size.

## 0.4.19 (firmware 0.11.0)

See your screens as they really are: the editor runs the screen's own firmware in the browser (GitHub #74 and #81,
thanks @woozer).

- **Your screens, drawn by their firmware.** The home page of the editor shows every screen's home page as its own
  firmware draws it: the real cards, fonts, icons, top bar and page dots, with live states from Home Assistant. It is a
  picture, not a remote control: a click still opens the screen in the editor. A board the preview does not know yet
  keeps the drawn mockup.
- **Preview runs the firmware.** **Preview** in the layout editor opens the layout you are editing in the firmware
  itself, so you can tap, hold and swipe through pages, detail views and album art exactly as on the glass, before
  saving anything. Taps stay in the preview until you switch on **Taps control devices**; then a tile does what it
  does on the screen.
- **Virtual screens.** **New screen → Virtual preview** designs a screen for a board you don't have yet, kept in your
  browser, with the same editor and the same preview.
- How it works: the shared firmware and LVGL are compiled to WebAssembly and ship with the add-on, fed the same packets
  a screen gets. Built by [@woozer](https://github.com/woozer) in
  [#74](https://github.com/MaxGramser/homeassistant_espscreen/pull/74) (virtual screens and the browser firmware) and
  [#81](https://github.com/MaxGramser/homeassistant_espscreen/pull/81) (album art and live updates); this release
  brings it up to firmware 0.11.0 (the Tessera logo in the top bar now shows in the preview too), onto the home page and
  into Preview, and in Hungarian.
- New firmware number for every board, but nothing changes on a screen: the firmware's files were only rearranged so the
  browser can build them. Updating a screen is optional.
- For developers: GitHub rebuilds the browser firmware by itself whenever the firmware changes
  (`.github/workflows/preview.yml`, docs/RELEASING.md). The renders no longer run in CI; `tools/check.sh --render` runs
  them locally.
- Tested: tools/check.sh (891 Python tests, 33 C++ tests, 384 editor tests, the WebAssembly firmware's own tests, types
  and build). Every board built on ESPHome 2026.9.0 and on the oldest ESPHome it asks for; the CYD stays at 91.2 % of its
  flash. The preview workflow rebuilt the browser firmware for 0.11.0 and the editor built from it matches a local
  build. On a Home Assistant bench with a Guition 4848S040: the home page drawn by the firmware, Preview with swipes
  between pages, and a tap with device control off that sent nothing to Home Assistant. Not looked at on other boards
  in the browser.

## 0.4.18 (firmware 0.10.0)

The home button in the top bar is the Tessera logo, and the starting screen says which firmware a screen runs.

- **The Tessera logo takes you home.** The key at the far left of the top bar is now the Tessera logo in its own
  colours instead of a house, the way a start button or the logo in a website's header takes you home. It is as tall
  as the house was, stands on the baseline of the page title and goes to the Home page as before. The page title gets
  a few pixels more room, and on a detail page Back takes the same place at the same height.
- **The editor shows it everywhere the screen does**: the page mockups, the preview, the home pages on **Your screens**,
  the top bar settings and **Add page**. The texts that spoke of a house now say home button, in every language.
- **Firmware number on the starting screen.** Small and centred at the foot of the page with the Tessera logo, under
  whatever it says: connecting, waiting for tiles, preparing pages or a message that the app and the screen don't match.
- **The editor says what holding a tile does** (GitHub #67). Under **On tap**, a tile whose tap does something else now
  names its hold: brightness and colour for a light, speed for a fan, history for a switch, cancel for a timer, the card
  for the rest. **Open control** on a light, fan or switch says the tap no longer switches it.
- The screens no longer carry a font for the house alone; with the logo in its place the firmware grows by 928 bytes on
  the CYD (91.1 % of its flash, as before).
- New firmware for every board: update the app, then press **Update** on each screen. Until then a screen keeps its
  house; **Show home button** in **Screen settings** still switches it off.
- Tested: tools/check.sh (883 Python tests, 33 C++ tests, 367 editor tests, types and build). Every board built on
  ESPHome 2026.9.0 and on the oldest ESPHome it asks for (2026.6.2, 2026.7.1 or 2026.8.0). Nine boards and shapes ran as
  host programs (tools/render/run.py: CYD lying and standing, Guition, Waveshare 3.5, 4.3 lying and standing and 7 inch,
  Hosyond 4 inch, JC8012P4A1): every self test passed, the logo stands in the top bar in light and dark, a tap on it goes
  home, and Back is as tall as the logo within a pixel. The editor was clicked through on a demo home. With the firmware
  number added, tools/check.sh passed again and the Guition built and ran as a host program, its starting screen showing
  v0.10.0 at the foot. Not yet looked at on a physical screen.

## 0.4.17 (firmware 0.9.0)

ESP Screens speaks Hungarian (GitHub #69, thanks @webguruadam).

- **Magyar.** The screens, the editor and the app's messages in Hungarian, translated by hand by
  [@webguruadam](https://github.com/webguruadam) in [#69](https://github.com/MaxGramser/homeassistant_espscreen/pull/69):
  all texts, with the terms of Home Assistant's own Hungarian and the calendar and numbers as Hungary writes them
  (`szept. 27., V`, `12 345,6`). The words for states (on, off, heating, the weather) are Home Assistant's own, and the
  thirteen texts added after the pull request was made (automation tiles, the bedside clock, reporting a problem) were
  drafted by Claude and wait for a Hungarian speaker to check them.
- The fonts already carry every Hungarian letter, ő and ű included, on every board.
- A Home Assistant in Hungarian picks it up by itself, or choose **Magyar** under **Settings → Language & region**. The
  editor shows it at once; each screen is offered an update that brings its texts in Hungarian. Screens in another
  language get nothing new.
- A new language is no firmware for the screens you have: `tools/affected_boards.py` now says so, as it does for a new
  board.
- Tested: tools/check.sh (883 Python tests, 33 C++ tests, the editor) and `tools/i18n.py check` with no problems. On a
  Guition 4848S040 with Home Assistant 2026.9.4: the app lists Magyar and choosing it offered the screen its language
  update; built from the packages in Hungarian, the screen came back on firmware 0.9.1 reporting Hungarian. Five pages of lights, locks, climate, covers,
  a vacuum, an alarm panel, media and the weather were looked at on the glass, every letter drawn.

## 0.4.16 (firmware 0.9.1 for guition)

Touch on the Guition 4 inch lands where you tap on every panel (GitHub #78, thanks @andrewradin).

- **Fixed: touches drifting towards the top left corner.** Some Guition ESP32-S3-4848S040 panels come with a touch chip
  that names a resolution of 1024 x 600 instead of 480 x 480. The firmware took that at its word, so the further a tap was
  from the top left corner, the further from your finger it landed. The Guition's firmware now sets the range itself.
  Nothing changes on a panel that already worked, and a `touchscreen:` calibration in an override YAML can go.
- New firmware for the Guition 4 inch only: update the app, then press **Update** on each Guition screen. Every other
  screen gets nothing new.
- Tested: the Guition builds with ESPHome 2026.9 (2,208,800 B, 27.2 % of its slot) and 2026.6.2, and its build sets
  the touch range to 0 to 480. The same range in an override YAML fixed the reporter's panel. Not yet seen on the
  glass of a Guition with this firmware.

## 0.4.15 (firmware 0.9.0)

Safer album covers (GitHub #77, thanks @EmanueleBenedettini).

- **Home Assistant's token goes to one address only.** ESP Screen Manager fetches a media player's cover with Home
  Assistant's token only from Home Assistant's own proxy for that same player. Any other address on Home Assistant,
  such as a camera's proxy or a path that walks out of the player's proxy, is refused. Until now a media player whose
  state named such an address could have the app fetch it with the token. Contributed by
  [@EmanueleBenedettini](https://github.com/EmanueleBenedettini) in
  [#77](https://github.com/MaxGramser/homeassistant_espscreen/pull/77).
- **Covers come through Home Assistant.** A player whose picture lies on the internet or on a server in the house
  (Cast, HEOS or WiiM, for example) hands out Home Assistant's proxy beside the picture's own address, and the app now
  takes the proxy: Home Assistant fetches the picture itself, and the app only talks to Home Assistant. A universal
  media player keeps its cover the same way.
- **A picture address without a proxy** is fetched from the internet only: an address in the house, on the add-on's
  own machine or link-local is refused, and a redirect is not followed (#77). No media player built into Home
  Assistant hands out such an address; a custom integration that does shows the player's icon instead of its cover.
  The name in such an address is looked up without holding up the app.
- Nothing changes for a screen you have: no firmware update.
- Tested: tools/check.sh (882 Python tests, 33 C++ tests, the editor). With the add-on on Home Assistant 2026.9.4, the
  editor's cover of a demo player, of a universal media player over it, of a player whose picture lies on a server in
  the house and of one behind a redirect all came through Home Assistant's proxy. Against a stand-in Home Assistant
  over real HTTP, a camera's proxy, a path out of the player's proxy, a proxy path behind another host and a picture in
  the house without a proxy were refused, and a name lookup that took 1.5 s held up the app for 22 ms instead of 1.5 s.
  Not looked at on a screen's glass: a screen asks for its cover through the same fetch as the editor.

## 0.4.14 (firmware 0.9.0)

A new board, experimental: the Waveshare ESP32-S3-Touch-LCD-7B (GitHub #25).

- **Waveshare 7B** in New screen, as **Waveshare · 7 inch** (ESP32-S3-Touch-LCD-7B): 1024 x 600, four by four tiles
  lying down and two by seven standing up, at the tile size of the 4-inch Guition. Its backlight dims, so brightness,
  standby and night mode are all there. It needs ESPHome 2026.7.0 or newer, which ESP Screen Manager already builds
  with. docs/WAVESHARE7B.md has the details and what to report.
- Nothing changes for a screen you have: no firmware update.
- Tested: the board builds with ESPHome 2026.9 (2,345,616 B, 28.9 % of its 8 MB slot) and with 2026.7.1, and its
  render check passes lying down and standing up. Not yet seen on the glass of a 7B: the pins, the timings and the
  backlight follow Waveshare's pin table and demo and ESPHome's component for the board's expander.

## 0.4.13 (firmware 0.9.0)

Camera pictures on large screens (GitHub #68, thanks @ivanfmartinez).

- **One cap for every picture.** No picture a screen gets is larger than 1024 pixels either way or 1.25 MB once
  decoded, whatever the size of its glass. A picture over that comes smaller and sits in the middle of its place, on a
  card that turns dark around it so the camera's name stays readable. This touches only the 10-inch screens (1280x800)
  today: a camera full screen there is 1024x640, and a page of large camera tiles gets its pictures a little smaller. Every smaller screen keeps its pictures exactly as they were.
- **Fixed: three large camera tiles on one page showed no picture at all.** On a 10-inch screen, three 2x2 cameras came
  to one picture of 1.7 MB, more than the screen keeps for later, and then no tile drew anything. Such a page now fits
  the cap, and a picture the screen has no room to keep is shown straight from the download.
- **Feedback:** when you answer "Not quite", the card now points to a bug report on GitHub. The board, the versions and
  a log there are what it takes to fix a problem.
- New firmware for every board: update the app, then press **Update** on each screen.
- Tested: every board builds with ESPHome 2026.9 (the CYD image is 1,671,632 B, 91.1 % of its slot, 704 B more). On a
  Guition 4 inch with Home Assistant 2026.9, three test cameras as live tiles: with the cap scaled down to that glass
  and the store made too small on purpose, every page showed its pictures smaller, centred and readable in the light
  and the dark look, through ten quick page turns without a restart; with the real cap the 4 inch looks exactly as on
  firmware 0.8.0. Not yet seen on a 10-inch screen.

## 0.4.12 (firmware 0.8.0)

A bedside clock: the time as large as the page allows, with up to three round keys under it.

- **Bedside clock** in the library: a tile that always takes a whole page, digits as large as the glass allows on
  every screen, lying down and standing up. Under the time are up to three round places for what you reach for at
  night: drag a lamp, a temperature or a lock onto one. A key is a tile in its round form, so it does what its tile
  does: a tap switches or opens, holding it opens the card, a lock asks for a second tap, and its colour follows the
  state. Tap a key in the editor to set it up like any tile. The clock starts without a card, so with Dark mode and
  the night hours the page is black at night. docs/BEDSIDE.md has the details.
- New firmware for every board: update the app, then press **Update** on each screen. A layout with a bedside clock
  waits for firmware 0.8.0.
- For contributors: a tile can hold other tiles without a cell of their own (`in` and `key` in the compiled tiles,
  `children` in the page document), and the render check draws the bedside clock on every board.
- Tested: every board builds with ESPHome 2026.9 (the CYD image is 1,670,928 B, 91.1 % of its slot, 16.8 KB more:
  13.5 KB for the bedside digits and the rest for the clock and its keys; the Hosyond 4 inch is at 93.0 % for its
  larger digits; both accepted by the owner). The keys were driven
  by a virtual finger on the host firmware, and a Guition 4 inch and a CYD showed a bedside clock with a lamp, a lock and
  an alarm panel as keys on a Home Assistant 2026.9. docs/TEST_RESULTS_0412.md has the details.

## 0.4.11 (firmware 0.7.0)

Automations on every screen (GitHub #62, thanks @Crazyraf87).

- **Automations.** An `automation` entity is now a tile, in Home Assistant's colours and icons: amber with a robot
  while it is on, grey with a crossed-out robot while it is off. A tap turns it on or off. Holding the tile runs its
  actions right away, the way **Run actions** does in Home Assistant (`automation.trigger`, conditions skipped).
- **Run automation actions.** For an automation you mostly start by hand, choose **On tap: Run automation actions**.
  A tap then runs it and holding the tile turns it on or off. That tile looks like a script's button: grey at rest
  with when it last ran, amber with "Running..." while its actions run, and Off while nothing starts it on its own
  (a tap still runs it then). A double-width tile carries the on/off switch or a Run key beside the name.
- The top bar can show an automation too, amber while it is on.
- New firmware for every board: update the app, then press **Update** on each screen. A layout with an automation
  waits for firmware 0.7.0. The own fixes of the Guition JC8012P4A1 V3 (0.6.2) and the
  Waveshare 4B (0.6.1) are in it.
- Tested: every board builds with ESPHome 2026.9 (the CYD image is 1,653,680 B, 90.1 % of its slot, 3.7 KB more for
  the automations and their robot icons). The firmware's own tap and hold routes on every kind of automation tile, drawn and driven by a virtual finger
  on the Guition, the CYD and the Waveshare 4.3 (lying down and standing up). On a Guition 4 inch with a Home
  Assistant 2026.9: tap switches, hold runs, a run button runs also while the automation is off, holding it switches,
  and "Running..." shows for as long as the actions run.
