## 0.2.134 (firmware 0.2.104)

Docker: Home Assistant on https with a self-signed certificate, and Home Assistant on another machine.

- With `HA_API` on https and a self-signed certificate, the log repeated `Home Assistant temporarily unavailable (ClientConnectorCertificateError)` and the screens stayed on *Waiting for ESP Screens*. `HA_CA_FILE` trusts that certificate for Home Assistant; `HA_VERIFY_SSL: "0"` is the last resort when the certificate doesn't name the address in `HA_API`. Only requests to Home Assistant use them, and the log now says what to set.
- `SCREEN_INGRESS_FROM`: when Home Assistant runs on another machine than the container, such as in a virtual machine, its sidebar panel can open the page over the network, for that address only.
- docs/DOCKER.md explains both, and when the SSH tunnel is needed at all.
- Nothing changes on Home Assistant OS, and nothing to do for your screens: the firmware is unchanged at 0.2.104.

## 0.2.133 (firmware 0.2.104)

An alert with a camera picture on one screen (GitHub #35).

- The `esp_screens_show_alert` event takes `screen`: only the screens it names get the alert. That is how one screen gets a camera picture or a button that runs an action, which the screen's own `show_alert` action cannot take, because Home Assistant makes every field of a device's action required. Without `screen` the event goes to every screen, as before.
- Fill in the screen's device name, the name Home Assistant shows, or a room, which reaches every screen in it. Case, spaces, dashes and underscores don't matter, and a list reaches several screens. A name that matches no screen sends nothing, and the log then names the screens it knows. `esp_screens_dismiss_alert` takes `screen` too.
- **Alerts** in ESP Screens has a new **One screen** part: for every screen what to fill in after `screen:`, ready to copy, and the example for the screen you choose. **Your screens** shows the same value next to the actions.
- Nothing to do for your screens: the firmware is unchanged at 0.2.104.

## 0.2.132 (firmware 0.2.104)

Copy API key works when Home Assistant is opened over plain http, and stays available after pairing.

- **Copy API key** on the *not yet in Home Assistant* card said it copied, but left the clipboard empty when Home Assistant was opened over http (for example `http://homeassistant.local:8123`), because the browser keeps its clipboard for secure pages there (GitHub #33). It copies now, and so do the copy buttons on the Alerts page. When even that fails, the key shows in a box, selected and ready to copy.
- A paired screen offers **Copy API key** too: open it in the sidebar. Home Assistant asks for the key again when the screen is removed and added back, or paired with another Home Assistant.
- Nothing to do for your screens: the firmware is unchanged at 0.2.104.

## 0.2.131 (firmware 0.2.104)

Sleep and Wake from Home Assistant on a Waveshare with a dimmable backlight.

- A Waveshare whose backlight was modded to dim (docs/WAVESHARE7.md) and whose override says `CAN_STANDBY: "true"` now also shows **Wake**, **Sleep** and the standby and night settings in Home Assistant. Until now standby worked on the screen itself, but those entities stayed hidden from the ESPHome integration.
- Press **Update firmware** once on such a screen. Every other screen builds the same firmware as before.

## 0.2.130 (firmware 0.2.104)

For contributors: every change is now checked the way a finger and Home Assistant use a screen. Nothing changes on your screens.

- The check that builds every board on a computer changes pages with a finger from the edge of the glass, through the screen's own touch handling, and reads the page title back in the moment after the swipe, so a title that stands in dots for a second is caught. It reads the alert card back as it opens, before its picture and right after it.
- docs/TESTING.md describes the levels of testing, from the fast checks to the whole chain through a real Home Assistant, and docs/TEST_RESULTS_02130.md what was tested for these releases.

## 0.2.129 (firmware 0.2.104)

New screen is drawn from one board catalog, and a CYD can be built for its other display controller.

- Every board New screen offers comes from `boards.yaml` and the board's own files: its name and size in inches, what is printed on it, its glass with the tiles of one page, its touch controller, and what it can do (camera pictures, dimming, standby, a touch calibration on the first start). A new board appears there without a change to the editor or its translations.
- A board that is new or experimental says so, with what it can and cannot do.
- A CYD asks which display controller it has: the ILI9341 most have, or the ST7789V some carry (GitHub #6). The choice is written into the screen's own YAML, so the Override YAML is no longer needed for it. The override editor refuses a substitution the screen's own YAML already sets, because that one would win.
- The screen list names every board from the same catalog.
- The CYD runs the same backlight and self-test code as every other board. Going into standby it now dims over one and a half seconds like the others, and the blinks of an alert fade for a moment instead of switching hard.
- The sun card keeps the sun's glow inside the card at sunrise and sunset; it stood a pixel over the edge.
- An alert text longer than a screen keeps (160 bytes of subtitle on a CYD, 240 on the others) ends in "..." instead of stopping in the middle of a word.
- Every board, lying down and standing up, is built and checked on every change: its own self test has to pass, and what it draws is compared with the version before, so a board nobody here owns is checked too.
- The Claude skill names the boards and grids ESP Screens knows, and every screen's Rotation choice (0° and 180°; a square screen also 90° and 270°).
- Adding a board is one command: `tools/new_board.py` writes the board file, its catalog entry, both entry files and an override case, and the entry files are generated from the catalog from now on.
- For a build from a clone of this repository, the six board entries moved from the root to `checkout/<board>.yaml`, next to their own `secrets.yaml` (checkout/README.md). Screens installed from ESP Screens or ESPHome Device Builder build from `packages/<board>.yaml` as before and need nothing.
- Firmware 0.2.104: press **Update** on each screen after the add-on updates.

## 0.2.128 (firmware 0.2.103)

The alert fits every screen, lying down and standing up, and its picture takes the shape of the camera.

- The alert card is laid out on the glass it lands on. Its size, its words and its button keep their size in millimetres on every board, the card never runs off a narrow screen, and nothing about it is written in a board file any more.
- An alert with a camera picture makes room for that picture in the camera's own proportions. A wide camera goes across the top of the card; a square or standing doorbell camera goes on the left of the words where the glass is wide and low, with the button on the right as always. The picture keeps one size in millimetres on every board, about as large as it has always been on the 4-inch Guition, so a big screen shows it tidily instead of filling the glass. Until the picture arrives the card shows a camera icon in its place.
- The picture reaches each screen at exactly the size of the frame it draws: ESP Screens fetches the snapshot once, measures it, and scales it once per frame size, all sizes at the same time, so a wall of different screens gets one moment without waiting on each other. A screen whose Override YAML changes its density gets the frame it really draws. At most about 430 KB goes to a screen.
- On the 4.3-inch Waveshare the button no longer covers the title of an alert with a picture, and standing up the picture is no longer cut off at the side.
- A long subtitle shows whole lines and ends in "…" instead of a line cut in half. The title is exactly one line of its font on every board, so a long title always ends in "…".
- Firmware 0.2.103: press **Update** on each screen after the add-on updates. A screen on older firmware keeps its alert as it was and gets its picture as before.

## 0.2.127 (firmware 0.2.102)

A screen's files are built from shared parts now, so a change reaches every board at once and a new board is a short file. The firmware every board builds is the same as before.

- A board file is its hardware, the facts of its glass and its grid, and the list of what it has. Its sizes come from its look (`packages/looks/`), worked out by ESPHome for the board's density, so a tile, a letter and a key keep their size in millimetres. What a board can do comes from shared features (`packages/features/`: capacitive or resistive touch, the backlight, camera images, the self test, the screen snapshot), and hardware several boards share from `packages/hardware/`. The board files went from 550 to 720 lines to 60 to 310.
- For the hardware changes people asked about most, a board now offers a substitution, so an override is one line: `DISPLAY_MODEL`, `DISPLAY_DATA_RATE` and `DISPLAY_INVERT_COLORS` on the CYD (GitHub #6, #12, #15), and `BACKLIGHT_FREQUENCY` on the boards with a PWM backlight (GitHub #5). docs/EASY_SETUP.md has the table.
- Overrides you already have keep working: every part they name stays where it is, and the overrides shared in GitHub issues are now checked on every board before a release.
- For contributors: `tools/new_board.py` writes a short board file instead of copying and scaling a whole one, and `tools/check_packages.py` refuses a block two boards copy from each other, or a line that only repeats a default. docs/PROFILES.md and docs/ADDING_A_BOARD.md describe the new layout.
- Nothing to do for existing screens: the shared firmware is unchanged at 0.2.102. The next build of a screen comes from the new files and is the same firmware.

## 0.2.126 (firmware 0.2.102)

Experimental support for the Waveshare ESP32-S3-Touch-LCD-4B.

- Choose **Waveshare 4B · 4 inch (experimental)** in **New screen** for the 480 x 480 ST7701S panel with GT911 touch and 8 MB PSRAM. The older ESP32-S3-Touch-LCD-4 without the "B" is a different board.
- The glass matches the 4-inch Guition, so the screen does too: two columns of three cells, the same tiles, a quarter turn as well as a half. Camera tiles, snapshots and camera alerts use the shared implementation.
- Unlike the 4.3-inch and 7-inch Waveshares, the backlight sits on a PWM pin: brightness, standby, night mode, Sleep and Wake are all on. The battery charger, audio and motion sensor on the board stay unused.
- The pins and timings follow a community ESPHome configuration for this board. Nobody has seen this profile on the glass yet; docs/WAVESHARE4B.md lists what to check and report.
- Existing screens need nothing: the shared firmware is unchanged at 0.2.102.

## 0.2.125 (firmware 0.2.102)

The new page's name stands there in the same frame as its tiles.

- 0.2.124 stopped a shortened name from staying shortened, and this is the other half of GitHub #27: the moment itself. A page change hands the top bar the next page's name while the label still has the width of the page before it, so a longer name was drawn in dots until the next pass over the screen measured the bar again, up to a second later. On the bench that showed as a page whose name was three dots and nothing else.
- The bar is measured again in the same frame now, next to the tiles of the page you swiped to, the way the rest of the page is drawn. The name that belongs to a page arrives with it, whole.
- Seen on the glass of a 4-inch Guition: page 2 says "Hal", page 1 says "Woonkamer beneden achter", and turning the page no longer leaves dots behind.
- Firmware 0.2.102: press **Update** on each screen after the add-on updates.

## 0.2.124 (firmware 0.2.101)

The name in the top bar stops shrinking to a letter and three dots.

- A name too long for the bar ends in dots, and LVGL writes those dots into the label's own text: it saves the letters they cover and puts "..." in their place, so the label answers "M..." when asked what it says. The bar measured the label to decide how much room the name may have, so a name that had been too narrow for a single frame was measured as its own dots from then on and stayed pinned at that width. Every page change is such a frame, because the label is handed the next page's title while it still carries the width of the page before it, and a page whose title is longer than the one before it, going back to page 1 most of all, left the name as one letter and three dots. The next change could shave another letter off it. Reported on GitHub (#27).
- The bar keeps its own copy of the name now and measures that. Dots stay what they were meant to be, a way of drawing a name that does not fit, and they no longer pass for the name itself. Nothing else about the bar changed.
- Checked on a computer with the firmware's own drawing code and the LVGL the screens run: the same five page changes that left "M...", "Ki..." and a name pinned at 48 pixels now keep every name whole, at its own width.
- Firmware 0.2.101: press **Update** on each screen after the add-on updates.

## 0.2.123 (firmware 0.2.100)

A page keeps its name wherever it stands, a page leaves with its tiles, and no two screens carry one name.

- **A title belongs to its page, page 1 included.** Dragging the first page away used to cost the name of the page that slid into its place, without a word: page 1 always said the screen's own title, so whatever name landed there was dropped. Every page now carries its own title and takes it along wherever in the row it lands, so reordering costs nothing, and the message about a lost title is gone with the loss.
- The bar of page 1 asks two things instead of one: the **Screen title**, which every page without a title of its own says, and the **Title above page 1**, which belongs to that page. A screen with one page asks only for the screen's title, as before. The firmware has fallen back to the screen's title per page since 0.2.90, so no screen needs a new build for this.
- **Remove page stands beside the cell count of every page**, not only under an empty one. People kept looking for a way to take a page out of the middle and found none: a page with tiles on it offered nothing, and emptying it by hand is six to twenty drags. The page now leaves with the tiles in its cells and with the **Go to page** tiles that led to it, so nothing is left opening a page nobody has; the pages after it move up with their titles, and the message says how many tiles went, with **Undo** beside it.
- **New screen refuses a name another screen already carries.** Home Assistant names a device's actions after the ESPHome name (`esphome.<screen>_screen_message`, the one this app hands a layout to) and the start of its entity ids after the name the device carries (`switch.<screen>_show_home_button`, the one an automation types). It cannot tell two devices of one name apart: the second screen's entities get numbered, so automations point at the wrong screen, and one of the two takes the other's actions. Only the profile file was checked until now, so a name already carried by a screen paired from somewhere else went through. The form says it under the name while it is typed, and the add-on refuses it as well.

## 0.2.122 (firmware 0.2.100)

Back to page 1 in one tap, or one swipe up, and every swipe says it landed.

- People kept asking for a quick way home, on GitHub too (#9: "a swipe down from the top to return to the home screen, or tap the name at the top left"). Every page now carries a house at the far left of the top bar, the way a website's header carries its logo: one tap and the screen is back on page 1, from wherever it stands.
- The house stands on the baseline of the page title and is a third taller than the bar's own icons. Drawn at the size of those icons it has the same ink box as the capitals beside it, but the top third of a house is the point of the roof and carries almost no ink, so it read as smaller than the name; measured on the render, only 37 % of its height carries real ink against the capital's even mass. It is one glyph in a font of its own, under a kilobyte, so every board has it, the CYD included.
- The page title moves behind the key with the same air between them as between the key and the edge of the glass, and the clock and the values on the right keep every pixel they had: only the title gives room.
- **Show home button** in **Screen settings**, on the screen's own settings page and as `switch.<screen>_show_home_button` in Home Assistant takes it away again. On by default.
- **Swiping up from the bottom edge also goes back to page 1.** It is the same gesture the sides already use, only along the bottom: from the bottom band, far enough up, more up than sideways, once per touch. On a screen that turns its pages with a flick instead of an edge swipe, a flick up does it.
- **Every swipe that is taken lights up the edge it came from**: a white haze, an oval half off the glass, that holds its light for 90 ms and then takes 420 ms to go. It answers the gesture before the new page is drawn. One object with one property fading, so nothing else on the page is drawn again.
- The editor's mockup draws the house the way the screen does, and leaves it out for a screen whose setting is off or whose firmware is older.

## 0.2.121 (firmware 0.2.99)

A whole page moves to another place in the row, by dragging it.

- Pages could only stand in the order they were made in. Putting the kitchen page before the bedroom one meant dragging every tile across by hand, and a full page is six to twenty drags, each one pushing another tile aside. Asked for on GitHub (#24).
- A page has a handle now: the label above it, with the grip the rows of the top bar already have. Drag it left or right and the row reorders under your hand, so you drop the page exactly where you see it. A drop away from the row changes nothing.
- Everything that belongs to the page comes along. Its tiles keep their own cells, empty cells included, and so do the double-width and full-page cards. Its own title travels with it. A **Go to page** tile keeps opening the page it means, under that page's new number, so the way through a screen still works after a reorder.
- Page 1 always says the screen's own title. A page carrying a title of its own that lands there lets that title go, which the message says, with **Undo** beside it.
- A finger does the same: hold the label for a moment, then drag. Without that hold the row of pages still scrolls sideways, as before. Left and right move a page one place along while its label has focus, for anyone who cannot drag.
- **Remove page** now takes the pages after it up with their titles and with the tiles that lead to them. Their titles used to stay behind on the number they had, so a page could end up under the title of another one.
- No firmware change: screens stay on 0.2.99.

## 0.2.120 (firmware 0.2.99)

A screen says for itself what it can do, and the 7-inch guide has the backlight mod.

- ESP Screens read two facts from a table it keeps per board: whether the backlight takes levels, and whether the screen can go dark at all. That is right until a board is changed. A Waveshare 7-inch whose backlight is rewired to a PWM pin really does dim, and the table kept saying it could not, so the brightness row stayed hidden in **Screen settings** while the screen's own settings page showed it (GitHub #22).
- A screen now reports what it can do in a **Screen features** sensor, one word per ability, and its own word wins. The table is still there for firmware from before this release, and for a screen that is offline and reports nothing. Adding an ability later is one line in the firmware and one row in the app, and a word the app does not know is skipped, so a newer screen may report something an older app has never heard of.
- The 7-inch guide now carries the backlight mod: the wire, the two pins people use for it, the Override YAML that turns the backlight into a real dimmer, and `min_power` for a driver that stays dark below roughly 40 % duty. Measured on a revision 1.1 board by @Cjdavidson.

## 0.2.119 (firmware 0.2.98)

A lamp that is on now says so in colour, not in brightness.

- A tile takes the lamp's own colour while it is on, straight from Home Assistant, and a bulb running near white sent something near white: the icon went from grey to almost white and the circle behind it from dark to pale. Across a room that reads as "a bit brighter", not as "on" (GitHub #22).
- Home Assistant does not hand its own tiles the raw colour either. Anything under 40 % saturation is lifted to 40 % first (`hui-tile-card`), so a pale warm bulb shows as a real peach instead of cream. The screens now do the same.
- Under 10 % saturation there is nothing left to lift, and Home Assistant only dims that white a shade. A white icon on a dark card, or on a card with a colour of its own, says the same as the grey of something off, so a bulb that is white now keeps the amber that every other lamp on a tile has.
- A bulb with a colour of its own is untouched: a warm white at 2700 K, a red, a green all still show their own colour, and so does the lamp's slider.

## 0.2.118 (firmware 0.2.97)

The calibration wizard measures each tap at one instant instead of two.

- A tap gave the wizard two halves from two moments: where the screen put your finger when it went down, and what the panel was sending when it came up. A finger rolls a little in between, which is what a finger does, so those two halves could describe different places.
- None of the guards caught it. Three taps a cross and their median only see the spread between taps, not the roll inside one, and the rule that all five crosses have to land back within 12 pixels holds the shifted chain against the shifted points, which agree. A finger that rolled the same way on every cross was accepted every time and moved the whole screen: measured on the fit itself, 100 counts of roll came out as 9.8 pixels off, 200 counts as 19.5.
- Both halves are now kept together on every reading while the finger is down, and the tap keeps the last of them. Taken together a pair is exact however noisy that instant is: the screen point is derived from the same filtered reading the panel sent, so noise sits in both halves and cancels where the wizard works out what the chain from panel to glass does. A tap that never reported a reading is asked for again, like one that was too short.
- The middle of the three taps on a cross is now one tap, not a mix. The median used to be taken per axis and again per half, so the reading could come from one tap and the point the screen made of it from another, which is the same pairs pulled apart a level up. A single wild tap is still thrown away: it is the one furthest from the middle, so it is never the one picked.
- Nothing changes on the glass: the same five crosses, the same three taps, the same spread check, and the correction still covers offset, scale and skew with the turn and any mirroring read from the taps themselves. A calibration already stored stays as it is, and is only replaced when you measure again.

## 0.2.117 (firmware 0.2.96)

A screen whose touch needs measuring can be sent back to its crosses, without waiting for its first boot.

- **Calibrate touch** is a row on the screen's own settings page, under **This screen** beside Restart, and a button in **Screen settings** in the app. Both start the same wizard the screen runs the first time it is switched on: five crosses, each tapped three times.
- Only a screen that has something to measure shows it. A resistive panel reads a voltage off the film and has to be told what that voltage means in pixels; a capacitive panel reports the point it was touched on, so it has no row, no button and no card. The app reads that from the screen's own Calibrate touch button in Home Assistant, so a board that gets a wizard later needs no change here.
- The row asks once, in place, before it starts, as Restart does, and the button in the app asks too: the screen goes to the crosses and stays on them until someone standing in front of it has tapped all five.
- Firmware 0.2.96. On a 320x240 screen This screen now has six rows, so it gets the same pager the other groups have: the facts on the first page, Calibrate touch and Restart on the second.

## 0.2.116 (firmware 0.2.95)

The filter chips in the library are all within reach of an ordinary mouse, and they follow what you are searching for.

- **Fifteen of the nineteen domain chips could not be reached at all with a mouse.** The strip scrolled sideways with its scrollbar hidden, and nothing let you drag it: a trackpad swipes such a strip, so it looked fine on a laptop, but with a plain mouse there was no bar to grab and the wheel scrolled the page instead. The strip was 1817 pixels wide in a panel of 271. Reported by a user.
- **The chips wrap now** instead of scrolling, so nothing is ever out of sight. A long strip keeps the head short: the first seven stand there and **More** opens the rest in place, **Fewer** folds them back. The chosen one always stays on show, even when it is one of the folded ones.
- **They follow the results.** Only domains that something in the list belongs to get a chip, so searching narrows the chips the way it narrows the list: type "temperature" and Climate stands next to Sensors instead of third of nineteen. A domain with nothing behind it in your home never gets a chip at all. Picking one leaves the others standing, so a domain is never a dead end.
- No firmware change: screens stay on 0.2.95.

## 0.2.114 (firmware 0.2.95)

A screen you no longer use can be removed, the way it was added.

- **Remove screen** sits in the sidebar, in the details of the screen it belongs to, under everything else. New screen adds one, this takes one away.
- Deleting only the YAML in ESPHome left the screen in the list, because the list is Home Assistant's: its device and entities stayed, and what is gone in the ESPHome folder cannot be removed there any more. Remove screen removes Home Assistant's ESPHome integration for that screen, with its device and its entities, exactly as the Delete in Home Assistant's own integration page does.
- It takes the rest with it: the screen's own YAML profile and its `.local.yaml` leave the ESPHome folder, together with what the app built from them, and the tiles, screen settings and update history kept here are forgotten. A screen this app never installed has no profile of its own, and nothing else in the ESPHome folder is touched.
- The page names all three before it asks, and warns that a screen that is still running and on Wi-Fi announces itself to Home Assistant again. Home Assistant goes first: while it refuses, nothing here is lost, and a profile that could not be removed is named instead of silently staying behind.
- No firmware change: screens stay on 0.2.95.

## 0.2.113 (firmware 0.2.95)

The container says it is healthy, because now it is asked something it can answer. Reported in issue #23.

- **`docker ps` read `(unhealthy)`** next to the app while everything worked. The image is built on the official ESPHome image, which brings a health check of its own: it asks the ESPHome dashboard on port 6052 for its version. This app runs its own server instead and never starts that dashboard, so the check could never pass, on every install since the first one.
- **The image now brings its own check**: `curl` on `127.0.0.1:8099/health` inside the container, every 30 seconds after a minute of grace. The app answers that one address with `ok` and nothing else, from inside the container as well as through Home Assistant; every other address still only answers Home Assistant's ingress proxy, so nothing of your home is reachable that was not before. Verified by building the image both ways and letting Docker judge: the old one turns unhealthy after about a minute, the new one healthy after thirty seconds.
- The Docker route's `compose.yaml` asks for `/health` too, for a container built from an older image.
- No firmware change: screens stay on 0.2.95.

## 0.2.112 (firmware 0.2.95)

Texts that still said two boards now say what is supported.

- **The app's own description** in the App store named the CYD and the Guition; it names the range instead: touch screens from 2.8 to 10.1 inch.
- **Cameras are not a Guition thing any more.** The hint under the camera field of an alert, and the line in the Alerts cheatsheet, said "Guition, firmware 0.2.57+". Every board but the CYD has carried pictures since the 4.3-inch Waveshare, so both now say every screen but the CYD, in all nine languages.
- **New screen** offered "Waveshare · 4.3 inch" and "Guition · 10.1 inch" in English in every other language; they read in that language's own words now, with its decimal comma.
- The README shows the five supported screens side by side at their real size difference, and the setup and camera guides list all five.
- No firmware change: screens stay on 0.2.95.

## 0.2.111 (firmware 0.2.95)

A card answers a finger with a press you can see.

- **The press is darker, and it fades.** A card under a finger went 45 % transparent, a shade lighter that was easy to miss, and snapped back the moment the finger lifted. It now darkens the moment the finger lands, an eighth of the way towards black in the light look and towards white in the dark look, so the press reads on a white card, on a pastel one and on graphite alike; a card without a background darkens the page under it. When the finger lifts, the card fades back over 200 ms. The fade is LVGL's own style transition on the card's background: no extra object, no layer, one small animation that redraws the card alone, so the CYD's memory and the frame rate of both boards are untouched. The busy sheet with the spinner is as it was: it only appears when Home Assistant takes longer than 400 ms to answer.
- Needs firmware 0.2.95: press **Update** on the screen. Includes everything from 0.2.110. CYD firmware: 1,623,872 bytes, 88.5 % of the update slot, built with the ESPHome this add-on ships (2026.9.0); 208 bytes less than 0.2.110.

## 0.2.110 (firmware 0.2.94)

Experimental support for the Waveshare ESP32-S3-Touch-LCD-7, requested in issue #22.

- Select **Waveshare 7 inch (experimental)** in **New screen** for the 800 x 480 RGB panel with GT911 touch and 8 MB PSRAM. The 7B and 7C are different boards.
- The standard layout has 4 x 4 cells lying down or 2 x 7 standing up. Camera tiles, full-screen snapshots and camera alerts use the shared implementation. Non-square pixels are not compensated.
- The backlight stays on. Dimming is unavailable on unmodified hardware; standby, night mode and alert backlight flashes remain disabled until physical wake tests confirm reliable operation.
- The profile uses an 8 MB flash layout, which also fits the 16 MB variant. Hardware acceptance is pending. See docs/WAVESHARE7.md for the test checklist and limitations.
- Storage, protocol and existing device keys are unchanged. Existing screens keep their board configuration.

- Validation: 580 Python tests, 24 C++ programs, 123 editor tests, all five firmware builds and host layout checks in both orientations. CYD remains at 1,624,080 bytes (88.5%, no growth). See docs/TEST_RESULTS_02110.md.

## 0.2.109 (firmware 0.2.93)

A page switch lands in one piece.

- **The next page arrives whole.** Since 0.2.42 a page switch put the new page's cards on the glass as empty frames in the very first refresh and filled them two at a time over the refreshes that followed, so that the screen kept answering a finger while the page was drawn. The drawing has become two to three times cheaper since then, and what was left of that fill read as a page being built up in front of you: frames first, then the cards, in steps. The screen now draws every card of the new page before it shows any of it. The page you were on stays until the new one is complete, and the complete page replaces it in one frame, about a tenth of a second after the swipe on the Guition and on the CYD. The chevrons and the dots under the page answer the tap as they did. No fade and no slide: every frame of a screen-wide animation is a full redraw in software on these boards, 50 to 110 ms each, so a slide or a fade would run at 10 to 16 frames per second and look worse than a clean cut. The measurements are in docs/SWIPE_PROFILE.md.
- Needs firmware 0.2.93: press **Update** on the screen. Includes everything from 0.2.108. CYD firmware: 1,624,080 bytes, 88.5 % of the update slot, built with the ESPHome this add-on ships (2026.9.0); 579 bytes less than 0.2.107, the last firmware before it.

## 0.2.108 (firmware 0.2.92)

The list of screens in the editor goes quiet: a name, an icon and a light, and the rest when you ask for it.

- **A screen is its name and a light.** Each screen in the sidebar is a row with its board's icon in a small tile, the screen's name, and a light on the tile's corner: green when all is well, amber when an update waits or runs, red when the screen is away. The light sends out a ring every few seconds, the way a sonar does; a red one keeps still. Nothing else, unless there is something to say: one line under the name names the update ("Update 0.2.92", "New language: Nederlands"), says Offline, or gives the reason an update failed. Choose a screen and its details open under it: the room, the firmware with the version an update brings, the board, the Update button, What's new, the address a screen without one asks for, and the progress of an update that runs. Choose it again and they fold away. The version, the room and "Online" that every screen used to spell out are gone from the list; the light and the details carry them.
- **Nothing to report is nothing on the page.** "Home Assistant connected" under the logo and "Sent to Home Assistant · Synced" above the pages said, most of the time, that all was well. They appear only when something is not: the management page unreachable or reconnecting, a layout saved but not yet on the screen, a screen that says it needs the layout again, a screen that is offline. The manager now tells the editor, per screen, whether the layout is out and held.
- **A screen standing up is drawn as large as it is.** The mockup of a page kept every screen the same height, so a 480 × 800 screen standing up came out 180 px wide, smaller than the square 4-inch Guition though it has more glass. Every mockup now has the same shorter side: a screen lying down is as wide as it was, and the same glass standing up is that wide and taller, 300 × 500 for the Waveshare and 300 × 480 for the 10.1-inch Guition.
- **The icon follows the screen.** A panel with tiles on it for a board ESP Screens knows, a phone for a screen standing up, a monitor for a board it does not know. Three icons for the editor's own font only; the screens' fonts are untouched.
- No firmware change: a screen keeps firmware 0.2.92 and has nothing to update. Includes everything from 0.2.107.

## 0.2.107 (firmware 0.2.92)

Every screen that is not square can be built lying down or standing up, and you choose which when you add it.

- **A screen standing up.** Pick a board in **New screen** and, if its glass is not square, pick how it will hang: lying down or standing up. A CYD standing up is one column of four cards, a Waveshare 4.3-inch the same, a 10.1-inch Guition four columns of five. That is the whole difference in the build: one line in the screen's profile, the same line the language uses, so a screen standing up is not another board and gets every card, every setting and every update the others get. The screens that are square, like the 4-inch Guition, are not asked the question, because square glass looks the same either way. Changing your mind later means building the screen again, which the dialog says where you choose.
- **A board says its two grids, and the screen picks one.** A board file now states the cells of a page for each way its glass can hang, and the screen reads its canvas at boot and takes the matching one. Everything that used to be a number in the board file, and was really the canvas in disguise, is now measured on the glass: the tile area, the cells, the page keys, the strip you hold to open the settings, the crosses of the touch test, the card of an alert. That is why the second way round costs nothing, and it is how the next board will be added.
- **The calibration wizard follows the glass.** The five crosses a CYD asks you to tap were written for a screen lying down: three of them fell outside a screen standing up. They now stand on the canvas the person is looking at, and the words under them wrap on narrow glass. The maths behind them changed too, and for a better reason: it used to work out, from the angle the board is turned by, which way round the panel's axes run under the picture, and that answer has to agree with what ESPHome's touchscreen, the board's own mirror and LVGL's turn do together. Now it works nothing out. Every tap hands the wizard two numbers, what the panel sent and where the screen put that touch, and five taps say exactly what the whole chain does, whichever way the glass hangs. A correction made standing up was within ten pixels lying down when we measured it, because it describes the panel and not the picture on it. Only a resistive panel is calibrated, so this is the CYD; the boards with capacitive glass report absolute coordinates and never ask.
- **Turning in the settings is unchanged.** A half turn (180 degrees) on any screen, the quarter turns on square glass. A quarter turn on other glass would be the other grid, and a layout made for six cells does not fit four, so that is a build and not a setting.
- Needs firmware 0.2.92: press **Update** on the screen. Includes everything from 0.2.106. Screens that are already lying down are untouched: every page, every card and the settings of all three shipping boards render pixel for pixel as they did, checked image by image (`tools/compare_renders.py`). CYD firmware: 1,624,659 bytes, 88.5 % of the update slot, built with the ESPHome this add-on ships (2026.9.0); 2,451 bytes more than 0.2.106.

## 0.2.106 (firmware 0.2.91)

A board says whether its screen can go dark at all, and the Waveshare says no.

- **A screen that cannot go dark has no standby and no night.** The Waveshare's backlight line also enables the boost converter behind its LEDs, and switching that on from a dark screen pulls the board's 3.3 V rail under its brownout level. Measured on the bench: every wake from a dark standby ended in a reset ("Brownout detector was triggered"), or the ESP survived and the I2C expander and the touch chip did not, which left the screen lit with nothing to tap. Drawing the page before lighting the panel, waiting a while, doing it with the screen idle - none of it changes what a boost converter draws when it starts. So, next to the flag that says whether a backlight takes levels, a board file now says whether its screen can go dark at all (`CAN_STANDBY`), and that one fact reaches everything: the standby time, Standby brightness, Screen on in standby, Night mode with its hours and brightness, Back to page 1 on standby, and the Wake and Sleep buttons are not on that screen's settings page, not among its entities in Home Assistant and not in ESP Screens' Settings (the Night group goes as a whole; night is standby with a clock). The backlight line of the Waveshare goes high once, at boot, and never low again, whatever asks: a setting the app pushes, an alert's blink, a YAML of your own. The three boards that dim keep everything they had. If you want a Waveshare that does go dark, the community's answer is a 470 µF capacitor on the 3V3 pins of its Sensor/AD connector; the firmware will not try it for you.
- Needs firmware 0.2.91: press **Update** on the screen. Includes everything from 0.2.105. CYD firmware: 1,622,208 bytes, 88.4 % of the update slot, built with the ESPHome this add-on ships (2026.9.0); 112 bytes more than 0.2.105.

## 0.2.105 (firmware 0.2.90)

The line under a tile's name is yours, a page can be called something of its own, and a board that cannot dim stops asking for a percentage.

- **A tile's second line says what you choose.** Under the name a tile writes a brightness, a temperature, when a script last ran, "Page 3" - the line the screen works out itself. You can now pick that line per tile, and every tile keeps saying exactly what it said before unless you change it. Four ways to fill it: the line the screen works out, nothing at all, words of your own, or a value of the entity. The values on offer are Home Assistant's own: its frontend names the attributes a person may see, in the screens' language, so a script offers Last triggered, Run mode and Running automations, a player offers Artist, Album and Volume, and a scene - which Home Assistant names no attribute of - offers none, which is what words of your own are for. A moment in time travels as seconds and the screen says it in its own words and its own clock, the way it already says when a script last ran. A line you chose beats every word the screen would work out, including a built-in card's, but never the two that say the screen cannot answer: an unavailable entity and a refused tap still say so.
- **A page can say something else at the top than the screen does.** The title at the top is the screen's, on every page, which is what most screens want. Give a page a title of its own and that page says it; leave it empty and the page hands the bar back to the screen's title. In the editor you click a page's top bar and answer one question - "Title above page 2" - and that page's bar in the mockup follows it while you type. One field, because two fields that fill the same line are two words for one thing: on page 1 that field is the screen's own title, the words every other page falls back to, and a later page shows page 1's words as its placeholder until it says something else. Renaming a screen there breaks nothing, since its actions and its sensors carry its device name and not its title. On a screen where nobody set one, nothing changes and nothing is paid for the possibility.
- **A tile's keys grey while a command is out, never because of what a device is doing.** A robot that was already cleaning but still said "docked" had its Stop and its Dock greyed out, exactly when they were wanted; the same trick closed a timer's Cancel whenever it was idle. Late news is not a fact. A key greys for one reason now - a command of this tile is on its way to Home Assistant and has not been answered - which is the wait the busy sheet and the cards already follow, with the same 400 ms grace before anything greys and the same cap. What a state may still decide is which key a key is: the first vacuum key is Pause while it cleans and Play otherwise. And a fact that cannot be late still closes a key: a blind at its end stop cannot open further, which is what Home Assistant's own cover card shows, and a select with fewer than two options has no next one.
- **No brightness percentage on a board whose backlight is only lit or dark.** The Waveshare's backlight is one line on an I2C expander: anything above a hair lights the panel and 0 turns it off. It was offered as three percentages anyway, two of which could only mean lit or dark and one of which did nothing. A board now says once, in its own file, whether its backlight takes levels, and that one fact reaches the firmware, the screen's own settings page and the add-on's Settings. Where it cannot dim the normal brightness is gone and standby and night are the switch they really are. Underneath it is the same setting with the same key, 0 or 100, so Home Assistant, the app and the screen keep reading one number, and a board that can dim shows the percentage it always did.
- **A tile's name stands in the middle when it has no second line.** A tile whose line says nothing had its name sitting high with empty room under it: the one rule that places a card's head counted a value line that was not there. It counts it only when there is one, on every board and every cell size. Words of your own also kept the space you may have typed in front of them, so one line looked indented while the rest did not; they are trimmed now.
- Needs firmware 0.2.90: press **Update** on the screen. Includes everything from 0.2.104. CYD firmware: 1,622,096 bytes, 88.4 % of the update slot, built with the ESPHome this add-on ships (2026.9.0); 2,208 bytes more than 0.2.104.

## 0.2.104 (firmware 0.2.89)

A graph and a big value grow into the room a ten-inch cell gives them.

- **A single graph tile draws a tall graph.** A cell on the 10.1-inch Guition is 162 px where the look was drawn for 108, and a sensor tile with its graph on put the name and the value in the middle of that room, above a graph a few pixels thin. The head and the strip were drawn for the look's cell; a taller cell has surplus, and the graph, which is the card's picture and not a control, now takes all of it: the name and the value keep the look's place at the top and the graph runs under them to the bottom of the card. A wide graph tile already took the right half of its card and does what it did. A cell of the look's height is laid out exactly as before, so on the CYD, the 4-inch Guition and the Waveshare every page is what it was, pixel for pixel (checked with renders of every page and card); with **Page buttons** off the rows share the room down to the bottom edge, and there a single graph tile now gives that surplus to its graph too instead of to the air around its name. A slider keeps its thumb-thick strip everywhere.
- **A big value that is big.** The same cell showed a **Big value** tile's number at the size the 4-inch Guition draws it, floating in the middle of a card twice its height, with the unit parked against the far edge. When the cell has the room, the number now takes the setpoint's digits, the largest face every board already carries (the climate card's), as long as they fit under the icon and the name and beside the unit and the value is a number: that face has digits, a sign, a point, a comma and a degree, and a word such as Home keeps the value's own face. On the ten-inch "1,249 W" grows from 33 to 56 px and the unit stands beside it; a 4-inch Guition has no such room and keeps its face. No new font, so no board grows in flash.
- Needs firmware 0.2.89: press **Update** on the screen. Includes everything from 0.2.102. CYD firmware: 1,619,888 bytes, 88.3 % of the update slot (+272 bytes against 0.2.102), built with the ESPHome this add-on ships (2026.9.0).


## 0.2.102 (firmware 0.2.87)

Home Assistant can open a page on a screen, the way it can show an alert.

- **`esphome.<screen>_show_page`.** Every screen has the action, with one field, `page`: the number the editor shows, 1 for the first page, and a number past the last page opens the last page. It puts that page of tiles in front the way a **Go to page** tile does when someone taps it: the screen wakes if it was in standby, an open card or the settings page closes, and the page is shown. An alert that is showing stays in front. Put a full-page player on page 4 and let an automation call the action when the player starts an album, or open the page with the camera tile when the doorbell rings. Like a touch, it starts **Back to page 1** counting from that moment, so the screen goes back to page 1 on its own time unless that switch is off; call the action again to keep the page up. Nothing is saved on the screen, so an automation may call it as often as it likes.
- **In the skill and the guide.** The Claude skill under Settings → Claude has a section for it beside the alerts (install it again to get the new text), and the extended README explains it under "Open a page from an automation".
- Needs firmware 0.2.87: press **Update** on the screen. Includes everything from 0.2.101. CYD firmware: 1,619,616 bytes, 88.3 % of the update slot, built with the ESPHome this add-on ships (2026.9.0).

## 0.2.101 (firmware 0.2.86)

A light that only switches stops pretending it can be dimmed, and a screen stops offering an update it cannot install.

- **No brightness slider on a light that has none.** Home Assistant lists `onoff` and nothing else for a light that is really a relay - a ceiling lamp on a wall switch - and its own dialog shows no brightness for it. Ours drew the slider anyway: it stood empty while the light was on, jumped to where your finger left it, and fell back to empty the moment the light answered without a brightness, because every drag sent one the light throws away. The card now shows the light's icon on a round field where the slider would be, in the same two colours the slider's track has, and the power key in the top bar does the work. A light that dims, and every fan, are unchanged.
- **A screen ESP Screens did not install no longer advertises an update.** Without a YAML in the ESPHome folder there is nothing to build from, so the button did nothing at all when pressed. The screen now says why, with the sentence the add-on already had for it. The nightly round always passed such a screen by; only the button was wrong.
- **The build log is quiet.** The eighteen `-Wdangling-reference` warnings left in the message parser are gone, with the reason written where they were: GCC cannot tell that the array ArduinoJson hands back points into the document rather than into the temporary it was asked on, and the warning stays on everywhere else. With 0.2.99's casts, a real ESP build goes from 79 warnings to none.
- Needs firmware 0.2.86. Press **Update** on the screen. Includes everything from 0.2.99.

## 0.2.99 (firmware 0.2.84)

What a finger does on a ten-inch screen, and what a card does with glass that wide.

- **A page swipe starts at the edge again.** On the 10.1-inch Guition a drag anywhere past two fifths of the screen turned a page, and nothing turned back. The firmware worked out where the edges were from the size the board declares, which is the picture after LVGL turns it, while a touch panel reports in its own pixels: on a portrait panel drawn in landscape that put the right-hand band 480 px too far in. ESPHome's own call turns a touch now, the same one that places the pointer, so the band is a band of the glass on any panel and in any rotation. The CYD, the 4-inch Guition and the Waveshare read the same points as before.
- **The finger readout on a graph follows the finger.** A card that does not fill the glass stands in the middle of it, and the graph compared the finger's place on the screen with its own place on the card: on a ten-inch panel the middle of the screen already read "now" and the card's left half read the start of the range. The two are read in the same coordinates now.
- **A card takes every press in the room it leaves.** LVGL looks on under an overlay that takes none, so a tap beside or below a card reached the tiles and the page keys behind it: a miss beside the 1 hour / 24 hours / 1 week keys turned the page under the open card. The backdrop behind a card and the colour card's own page take the press instead, as the effects page already did. The three range keys also keep 7 mm of touch area whatever they are drawn at, like every other segmented row.
- **A graph fills the glass; what a finger works keeps a hand's width.** A sensor's card is a picture as much as a camera's is, so its graph now runs from edge to edge, and the range keys under it stand in the middle at a hand's width. A player's card does the same: the cover grows with the glass, up to the 320 px the add-on serves, and the track, the keys and the volume slider stay within one hand instead of running nineteen centimetres across. A cover is cut and rounded by the add-on at exactly the size the card asks for and drawn one to one, so the card never asks for a square the add-on will not hand over: it would answer nothing and the card would keep its placeholder. The colour card and the effects page, which still drew across whatever glass they were given, stand in the middle as a card of their own, and the effects page puts its block in the middle of the room under the title the way every other card centres what it draws: three rows and two sliders no longer hang from the top of a ten-inch screen, and on a 4-inch Guition that block moves down 44 px. The name picker on that page moves with it, by the same rule. Below a hand's width the cards themselves do not move: thirty renders of a CYD, a 4-inch Guition and a Waveshare are what they were, pixel for pixel.
- Needs firmware 0.2.82: press **Update** on the screen. Includes everything from 0.2.96.
## 0.2.98 (firmware 0.2.83)

The screens say what a picture costs them.

- **The other half of the memory, as two entities.** The four heap figures a screen reports come from ESPHome's debug platform, and on an ESP32 all four read the memory inside the chip. Nothing said what the PSRAM held, while that is where a camera picture or an album cover of a megabyte or more ends up. **Psram Free** and **Psram Largest Block** now say it, as diagnostics beside the others; a board without PSRAM reports zero. The second one is the one that decides: a picture needs one block, not a total, so 2 MB free in ten pieces holds no picture of 2 MB.
- **What one picture does to both halves, in the log.** Every picture takes the same road, an image of exactly the pixels the screen asked for, decoded to two bytes a pixel, and the allocator prefers the memory inside the chip before it falls back to PSRAM. A screen now writes one `picture` line before and after each load, for a cover, a camera and the strip of live tiles alike, with both halves in it. That is the instrument for giving every board picture sizes that fit it, instead of sizes that follow from the panel's resolution.
- Nothing on any screen looks different. Needs firmware 0.2.83 to report the two new entities: press **Update** on the screen.

## 0.2.97 (firmware 0.2.82)

A quiet build log, so the next real warning in it is seen.

- **Seventy-nine compiler warnings, all the same one.** The screens print their diagnostics with `%d`, and on the chip's toolchain `int32_t` is a `long int` rather than an `int`: every settings value, every LVGL coordinate and every slider position in a log line warned about it. The numbers were always right - both are 32 bits on an ESP32 - and the code the compiler makes is unchanged, but a build that ends in a wall of yellow is a build where a real warning goes unnoticed. They are cast where they are printed now, in the shared core, the runtime, the colour card, the diagnostics and every board's self test: 79 warnings become 0. What is left are eighteen `-Wdangling-reference` notes on the JSON loops, which GCC raises for a pattern ArduinoJson is built on (the array refers to the document, not to the temporary that made it).
- The check that every board hands the edge swipe its own width now walks the boards that ship rather than every file in the folder: a lab board is generated and disposable, and an old one on a developer's machine failed a check that CI, which has none of them, called green.
- Needs firmware 0.2.84 only to keep the numbers in step; the screen does exactly what 0.2.83 does. Press **Update** when it suits you.

## 0.2.96 (firmware 0.2.81)

The controls of a double-width card stand where the cards above and below have their edges.

- **A small slider on a double-width card stands beside the name.** "Small slider on the tile" drew a strip under the name whatever the width of the card, while the editor's mockup has drawn it beside the name on a double-width card and a wide card's own brightness slider stands there. It is that slider now: the same control in the same place, with the same value held in front while a light fades. A single card keeps its strip under the head, and so does a double-width card too narrow for a panel. A light, a fan, a blind, a player and a number each get the slider of their own domain.
- **A control that fills its room is one cell wide.** The slider, the - / + pill and a player's volume with its mute key take the content width of one cell of the board's grid, so their edges stand where the cards in the rows above and below have theirs: a double-width card is two cells, and the controls claim the second one. The sizes those controls had were what one cell of a CYD and a 4-inch Guition measures, written down as a number instead of as a rule - within two pixels, which is why those two boards draw what they drew before (three pixels wider on a CYD, two narrower on a Guition). On a board whose grid divides its glass differently the number no longer fits: on the Waveshare's three columns the slider was 251 px on a 478 px card and the name kept 28 % of it, where a Guition leaves 36 %; it is 218 px now and the name has its share back. A row of keys divides that same cell between three of them, never above the size the look gives a key and never under 7 mm of glass. A switch and a run key keep their own size, right against the same edge.
- **The test that decides whether a card has room for controls measures what they take.** It budgeted a slider panel at 188 of the look's pixels while a brightness slider takes 196, so a card that just passed left the name eight pixels less than the test had counted on. It now asks the controls themselves.
- Needs firmware 0.2.81: press **Update** on the screen. Includes everything from 0.2.95. CYD firmware: 1,617,280 bytes, 88.1 % of the update slot (128 bytes less than 0.2.95: a rule takes fewer numbers than a table), built with the ESPHome this add-on ships (2026.9.0).

## 0.2.95 (firmware 0.2.80)

A fourth screen: the 10.1-inch Guition JC8012P4A1, the first ESP32-P4 board and the first one of this size.

- **The 10.1-inch Guition JC8012P4A1.** 1280 x 800 on a MIPI-DSI panel, a grid of five by four, twenty tiles on a page and three pages. It is the first board added entirely by the recipe of 0.2.94: it brings its hardware and its glass, and the screens' own software - the tiles, the cards, the settings, the top bar, the languages - is the same firmware every other board runs. Choose it in **New screen**. The hardware of this board was worked out and checked on the real panel by [Micha Okkerman](https://github.com/michamichamicha) in [pull request #14](https://github.com/MaxGramser/homeassistant_espscreen/pull/14); ESPHome has since learned this panel and its touch chip itself, so nothing of the board needs code of our own any more.
- **New, and not yet through our own acceptance test.** We do not have this panel on the bench: the firmware compiles, every page and card was rendered at this size, and the hardware comes from a build that ran on a real screen, but board and software have not stood on one desk together. The editor marks it as new. Tell us how it goes.
- **It asks for a newer ESPHome than the other boards.** Its touch panel is newer than the ESPHome the packages build with, so this board alone states ESPHome 2026.8.0 as its minimum; the CYD, the 4-inch Guition and the Waveshare keep building on 2026.6.2. It also needs a panel with pre-v3 silicon (`chip revision: v1.3` or lower in the boot log), which is what these panels have shipped with; the two kinds of silicon are not binary compatible.
- No firmware change for the boards that were already there: a CYD, a 4-inch Guition or a Waveshare keeps firmware 0.2.80 and has nothing to update.

## 0.2.94 (firmware 0.2.80)

The screens stop being written for two panels and start being written for glass. A board file now says what its screen is - how big, how dense, how many tiles fit - and the firmware, the manager and the editor work out the rest: the grid, the size of everything drawn, the shape of every card a tap opens. Adding a board becomes a recipe instead of a rewrite, and the Waveshare ESP32-S3-Touch-LCD-4.3 is the first to walk it. The CYD and the Guition draw exactly what they drew before.

- **Every board its own grid.** A board file declares how many columns and rows a page holds, its pixel density and its look; the tile area is an LVGL grid that divides the page over those cells, and the cards of that grid come from one generated file per cell count. Every size the firmware decides itself goes through one scale, so a tile, a letter and a key keep their size in millimetres on any panel. The CYD and the Guition keep their two columns of three and draw what they drew before.
- **Waveshare ESP32-S3-Touch-LCD-4.3.** The first board added this way: 4.3 inch, 800 × 480, three by three tiles, camera pictures and album covers like a Guition. **New screen** offers it. Its backlight is a line on an expander, so it is lit or dark; the brightness settings decide when. Its LVGL draw buffer is 12 % of the glass, like the CYD's: with a quarter the chip ran on 15 KB and hung under a large layout.
- **The thermostat card on every board.** One computed card: the setpoint between its keys, a key per mode, and the fan and swing rows, fitted to the glass in a fixed order of concessions. A CYD shows all of them at once for the first time; the Mode page is gone. The blind, the robot and the light's effects page fit the same way, and the effects page stands in two columns on wide glass. A card that leaves room now sits in the middle of the glass.
- **The weather card fits its glass.** Its two blocks - the weather now with the next hours, and the coming days - are computed like the thermostat's: they stand beside each other where a board has the width for both, and where they do not fit they give up the rain under the hours, then the heading, then the hour strip, in that order, until every day keeps a row of its own. Days that still do not fit go on a next page, with the same chevrons and dots as the tile pages. On a 4.3 inch the coming days were a 51 px strip with five rows drawn over each other; the CYD and the Guition draw the same pixels as before.
- **The card of a light and a fan is a card like the rest.** A hold on a light that only dims, or on a fan, opens a white card with a standing slider, the value under it and the power key in the top bar, where the thermostat has it. It was the last card still built in YAML: an overlay that sat in the screen's memory whether it was open or not, with eight sizes of its own in every board file, two scripts, and a rainbow key of eight arcs that nothing opened any more. All of it is gone; the card is worked out for the glass it lands on (`light_card.h`) and made only while it is open. A light with a colour or a colour temperature opens the same colour card as before.
- **The manager and the editor follow the screen.** A screen reports its shape ("Screen layout": canvas, grid, density and look) and its board ("Screen board"). The editor draws the mockup at that aspect with that grid and the top bar at that density, and moves tiles by the screen's columns; saving, the tile events and the layout sensor count rows, columns, pages and the tile limit on that grid (seven pages of nine on the Waveshare, 63 tiles). The layout sensor now also says `columns`, `rows` and `max_pages`, and names a column by number on a screen with more than two; the events take a number as well as `left` and `right`. Nothing changes for a two-column screen.
- **Every screen turns.** A half turn (180°) on every board, because width, height and the grid stay the same; the quarter turns as well on a square screen, as the Guition always had. On the screen's settings page, in **Screen settings** and as `select.<screen>_rotation` in Home Assistant, which offers the angles that screen's glass allows.
- **Camera tiles and covers on any board that draws pictures.** The manager takes the picture sizes from the board file instead of a list of one board, and the editor offers cameras and covers where the board can show them. A screen that cannot hears "This screen cannot show camera pictures".
- **What a finger does lives in one place.** The three touchscreen triggers of a capacitive board call the shared handler; a new board takes them in one line each and cannot take half of them.
- **A card's head is computed, on every board.** The icon circle, the name and the state stand centred on the cell the card got, by one rule for the single, the double-width and the full-page card, whether a screen has two rows or three; a board states the icon's size and no longer six places for them. On the Waveshare's three rows the circle sat 3 px low and the two lines 3 px too close; on a Guition the circle moves 2 px down to the true middle and nothing else changes; a CYD draws the same pixels. A slider or graph tile whose cell is too short for two lines above its strip puts the name and the value on one line instead of drawing the value under the strip, and a full-page card's head keeps to the share of the card it has on a Guition, so the media card keeps its keys on a 4.3 inch. A big-value tile whose cell has no room for the icon and the name above the number puts the number big in the middle and the name small in the corner.
- **For the next board:** docs/RESPONSIVE.md says how a board fits its glass and how to design a card for glass we have never seen; docs/ADDING_A_BOARD.md is the recipe (`tools/propose_grid.py`, `tools/new_board.py`, `tools/generate_cells.py`, `tools/generate_board_shapes.py`); `tools/check.sh --firmware` compiles every board.
- Needs firmware 0.2.80: press **Update** on the screen. Includes everything from 0.2.93. CYD firmware: 1,617,408 bytes, 88.1 % of the update slot (16,352 bytes less than 0.2.92: the thermostat and the light overlays left the YAML), built with the ESPHome this add-on ships (2026.9.0).
## 0.2.93 (firmware 0.2.79)

A CYD that no longer restarts when you drag the big slider of a light, fan or blind.

- **The big slider on a card drew through a hidden buffer.** Since the first release the card a hold opens (a light without colour, a fan, a blind) rounded its slider's fill less than its track. LVGL then draws that fill into a buffer of its own on every redraw, 61 KB on a CYD that has about that much in one piece. Drag the slider while the screen is busy with something else, a light you just switched, an answer from Home Assistant, and that buffer is refused; LVGL keeps asking for it until the watchdog restarts the board. The fill now keeps the track's rounding, as the small sliders on the tiles have since 0.2.50, and nothing is drawn through a buffer any more. On a Guition the track also keeps its own rounding (42 px) instead of dropping to the CYD's 28 px after the first card opened. A test now reads the lambdas in the YAML as well as the C++ for a fill rounded less than its track.
- Needs firmware 0.2.79: press **Update** on the screen. Includes everything from 0.2.92. CYD firmware: as 0.2.92, two style calls fewer. How it was found and tested: docs/TEST_RESULTS_0293.md.

## 0.2.92 (firmware 0.2.78)

The album cover on a media tile, the way Home Assistant's own tile shows it.

- **The album cover in the icon's place.** On a Guition, a single or double-width media player tile can show the cover of what plays instead of its icon: in the tile's settings choose **Display → Album cover**. It travels the same road as the live camera pictures of 0.2.91, in the one strip a page shares: a page with a camera and a Sonos loads its strip at the camera's pace and reuses the cover until the track changes; a page of media tiles alone loads once, and again the moment a new track brings another picture. A player without a picture (a radio station, a player that is off) keeps its icon; the double-width tile keeps its volume or playback controls. The tile over the whole page keeps the card's big cover. Nothing loads in standby.
- Needs firmware 0.2.78: press **Update** on the screen. Includes everything from 0.2.91. CYD firmware: 1,633,760 bytes, 89.0 % of the update slot (32 bytes more than 0.2.91).

## 0.2.91 (firmware 0.2.77)

Your cameras on the tiles themselves, an alert button that does something, and media titles that roll by.

- **A live picture on a camera tile.** On a Guition, a camera or image tile can show a small picture of its camera in the icon's place: in the tile's settings choose **Display → Live picture** and a pace, every 15 or 30 seconds. The picture is the middle of the camera's view as a rounded square in the tile's own colour, refreshed while that page is on the screen; a tap still opens the camera full screen. The camera tiles of one page share one download (ESP Screens serves them as one strip of squares), so six live tiles cost the screen no more than one, and a 30 s camera on a 15 s page is fetched every other time. The live pictures wait for an alert's picture, an album cover or the camera full screen, and never load under an open card, in standby or under a finger. Asked for in issue #4.
- **An action behind the alert button.** The `esp_screens_show_alert` event takes `action` (a Home Assistant action such as `script.open_gate` or `light.turn_off`) and `data` for its fields: ESP Screens performs it once when the button is pressed on any screen. A timeout, a new alert or a dismissal leaves it unperformed. The screens only report the press, as they always did, so this works with every screen from firmware 0.2.31. The Alerts cheatsheet and the Claude skill document the field.
- **A full-page tile keeps its own colour.** A tile over the whole page is white, or the pastel you gave it, like every other tile; its icon shows the state. Firmware 0.2.62 to 0.2.76 tinted the whole tile in its state colour while it was on (a playing speaker turned the page blue), which is gone.
- **Media titles roll by.** A title or an artist line that is too wide for the media card or the full-page media tile now rolls by, round and round, instead of ending in dots; a text that fits stands still.
- Needs firmware 0.2.77 for the live pictures and the rolling titles: press **Update** on the screen. Includes everything from 0.2.90. CYD firmware: 1,633,728 bytes, 89.0 % of the update slot (832 bytes more than 0.2.90).

## 0.2.90 (firmware 0.2.76)

ESP Screens speaks your language: the screens, the editor and its messages in nine languages, with the numbers, the clock and Home Assistant's own words as your country writes them.

- **The editor in your language.** It follows the language of your Home Assistant profile, so two people in one house each see their own. English (United States), English (United Kingdom), Nederlands, Deutsch, Français, Español, Italiano, Português and Polski are in this release.
- **The screens in your language.** A screen carries one language, which it gets at its next firmware update: press **Update** on it (or let the nightly round do it). New in **Settings → Language & region**: the language for the screens, the clock (24 hours or 12 with AM/PM) and how numbers are written. All three start at what your Home Assistant says, so most people never have to touch them.
- **Numbers and the clock as your country writes them.** 1.234,5 in Dutch, 1,234.5 in English, 1 234,5 in French, and a room at 21,5 °C. The screens change this at once, without a new firmware. The **24-hour clock** switch of every screen is gone; the choice moved to Settings → Language & region and keeps what it was set to.
- **Home Assistant's own words stay Home Assistant's.** What a door, an airco or a robot says, and the words in their cards (fan and swing modes, suction, the mop), come from your Home Assistant in your language, exactly as its own dashboard writes them. A space in front of a percent sign follows the same rule as Home Assistant: 54% in English and Dutch, 54 % in German, French, Czech, Finnish, Slovak and Swedish.
- **Room for longer words.** The weather columns show two-letter days, a long weather word ends in an ellipsis instead of running into them, and the line under a tile's name keeps the part that carries the news: "Yest. 9:15 PM" where the full wording doesn't fit, and a robot's battery stays readable behind Home Assistant's word for its state.
- **Add or improve a language yourself.** Every text of one language sits in one file, `screen_manager/translations/<code>.json`, and docs/TRANSLATING.md walks through starting a new one, checking it with `tools/i18n.py check` (it measures the lines under a tile's name in the screens' own font) and sending it in. A language without a file falls back to English, with its own clock and number style.
- **What it costs.** The letters of the European languages sit in the fonts of both boards, and one language's texts in the firmware: 48 KB on a CYD. Built with the ESPHome this add-on ships (2026.9.0) its firmware is 1,632,896 bytes, 89.0 % of its update slot (0.2.89: 1,585,136 bytes, 86.4 %); built with the oldest ESPHome the packages accept (2026.6.2), 1,657,808 bytes or 90.3 %. A Guition, with 16 MB of flash, stays around a quarter of its own. Both boards keep building with ESPHome 2026.6.2 or newer.

## 0.2.89 (firmware 0.2.75)

ESPHome 2026.9 in ESP Screens, updates that no longer start from scratch without reason, and 94 KB more room on a CYD.

- **ESP Screens builds with ESPHome 2026.9.0** (was 2026.6.2). ESPHome now compiles an ESP32 with Espressif's own ESP-IDF instead of PlatformIO, and keeps what it compiled before in a cache. Before the first update of a screen, ESP Screens downloads ESP-IDF once (about 1.7 GB on disk) and removes PlatformIO, which only the old builds used, with the disk space it took. That first update builds each screen completely, once: on a Home Assistant Yellow 17 minutes for a CYD (about as long as before) and 23 minutes for a Guition, the download included. After it, a screen whose firmware didn't change is done in under a minute.
- **An update no longer starts from scratch because of the ESPHome Device Builder.** ESP Screens kept its memory of each build in the ESPHome folder, which the ESPHome Device Builder app empties every time it starts. The next update of every screen then rebuilt everything, 15 to 18 minutes on a Yellow. That memory now lives in ESP Screens' own storage, with ESP-IDF and the compiler's cache. Backups leave all of it out; it is downloaded or built again when needed.
- **94 KB more room on a CYD.** Its firmware is 1,585,136 bytes, 86.4 % of its update slot (was 91.5 %). That makes room for more languages and later ESPHome versions. Three changes: ESP-IDF's texts for failed internal checks are left out (49 KB; a failed check still restarts the screen), the screen logs from INFO instead of DEBUG (9 KB), and a small piece of our code no longer pulls in C's whole text scanner (9.5 KB). ESPHome 2026.9 itself saves the rest. A Guition's firmware is 110 KB smaller too.
- **Fewer log lines from the screen itself.** The screen's own log now starts at INFO: ESPHome's configuration dump and its debug lines for every state are no longer in the firmware. Nothing changes on the screen or in Home Assistant. To look closer at one screen, put `logger:` with `level: DEBUG` in its **Override YAML** and press **Update**.
- **A running timer never shows more than it lasts.** A 3-second timer could start at 0:04 on its tile. The screen counts down from Home Assistant's end time with its own clock, both in whole seconds, and its clock can be up to a second behind. The countdown now stops at the timer's duration.
- **Nothing to do in a particular order.** The firmware still builds with ESPHome 2026.6.2 or newer, so an ESP Screens that isn't updated yet, or your own ESPHome Device Builder, keeps building every screen. Update ESP Screens, then press **Update** on each screen (or let the nightly round do it): firmware 0.2.75. Includes everything from 0.2.88.

## 0.2.88 (firmware 0.2.74)

Wi-Fi that never dozes, on every screen.

- **A screen keeps its Wi-Fi awake.** ESPHome lets an ESP32's Wi-Fi doze between the router's beacons unless the screen's YAML says otherwise. Then everything Home Assistant sends to the screen waits at the router for the next beacon: 76-117 ms on the bench screens against about 20 ms awake. That wait shows in the confirmation after a tap and in a lamp reporting its brightness. With the Wi-Fi awake, the screen also stalls less often for a moment while a camera picture comes in. The YAML ESP Screens writes has said `power_save_mode: none` since app 0.2.24, but older screens and YAMLs written by hand still dozed. The firmware now keeps the Wi-Fi awake itself; the screens hang on the mains, and it costs a few tenths of a watt. The network and its password stay in the screen's own YAML, and a `power_save_mode` there still wins.
- Needs firmware 0.2.74: press **Update** on the screen. Includes everything from 0.2.87. CYD firmware: 1,678,816 bytes, 91.5 % of the update slot, the same as 0.2.87.

## 0.2.87 (firmware 0.2.73)

A starting screen with a spinner, a camera that opens sooner with a spinner, and round corners on an alert's camera picture.

- **A starting screen with a spinner.** Until the tiles arrive, a screen says in the middle what it waits for, *Connecting to Home Assistant* and then *Waiting for ESP Screens*, with a turning spinner under it. Before, that was a line of text in the top bar. The text and the spinner go as soon as the tiles come, so nothing keeps turning behind them.
- **A camera opens sooner, with a spinner.** The camera full screen shows the spinner until the first picture is there, instead of the words *Loading image*; a camera without a picture still says so. The first picture also comes sooner on a Guition. The screen asks for it the moment the camera opens and starts loading it the moment ESP Screens answers, where it used to wait for its next quarter-second tick each time. It also loads 16 KB of the picture at a time instead of 4 KB. On the bench Guition a camera the add-on had just shown opened in 2.1 s instead of 3.4 s, and a camera it had to ask Home Assistant for first in 4.6 s instead of 5.8 s. The rest of that wait is the camera itself: the EZVIZ answers in 2.4 s.
- **The picture in an alert has round corners**, the same as the alert card around it, on a Guition. LVGL rounds the picture itself while it draws it, row by row, without an extra buffer. Drawing the picture takes about 5 % longer than a square one, and only when it is drawn (the alert appearing, or coming back after the camera full screen); a picture that stays up costs nothing more. The camera full screen keeps its square picture from edge to edge.
- **Cameras are in the README**, as tiles of their own and not only in an alert: a page with a camera, a live camera and a doorbell's last ring, the picture full screen, and the same camera in an alert.
- Needs firmware 0.2.73: press **Update** on the screen. The starting screen is on both boards; the camera changes are the Guition's. Includes everything from 0.2.86. CYD firmware: 1,678,816 bytes, 91.5 % of the update slot (1,312 bytes more than 0.2.86).

## 0.2.86 (firmware 0.2.72)

The on/off switch on a wide tile switches again.

- **The switch on a wide or full-page tile does what it shows.** Since firmware 0.2.59 (app 0.2.70), a tap on the *On/off switch* of a wide card sent the opposite of what it showed. The knob moved to on, but the screen asked Home Assistant to turn the light *off*. The light already was off, so nothing happened, and a moment later the knob slid back. On a light that was on, the same happened the other way round. The switch drew its new position before it chose the action, and then chose from that new position; it now chooses first. A tap on the tile itself was never affected. This fixes lights, switches, input booleans and fans. The switch is what a wide tile of these shows unless you choose another control, so most wide tiles of them had it.
- Needs firmware 0.2.72: press **Update** on the screen. Includes everything from 0.2.85. CYD firmware: 1,677,504 bytes, 91.4 % of the update slot (16 bytes more than 0.2.85).

## 0.2.85 (firmware 0.2.71)

Off looks off on every tile, in Home Assistant's colours.

- **What Home Assistant calls off is grey.** Tiles now follow the rule Home Assistant's own cards colour by (its `stateActive()`). An airco or fan that is off, a closed blind, a docked or paused robot, a player that is off or in standby, a script that isn't running, a paused timer and a camera that isn't streaming turn grey, as an off light or door sensor already did. The airco was the one you noticed: its tile stayed orange while the airco was off.
- **An airco that is off says Off.** Its tile showed the temperature it was set to, even while off. It now reads *Off*, with the room's temperature when the device reports one (*Off · 21.5°*), as Home Assistant's tile does. While it runs, the tile still shows the set temperature.
- **Home Assistant's colours for the rest.** An alarm that goes off is red on its tile, as in the top bar: smoke, gas, carbon monoxide, a leak, heat, a problem, safety, sound, tampering, a low battery and an unlocked lock. A battery sensor is green from 70 %, orange from 30 % and red below that. A running script or timer and a streaming camera are amber. The weather takes the colour of its condition: clouds light grey, fog grey, rain blue, pouring rain indigo, snow pale blue, lightning yellow and wind green. The sun is amber by day and indigo at night, and someone in a zone other than home is blue. Scenes, selects, numbers and sensors keep their own colour per kind, where Home Assistant draws them all in one neutral blue.
- **A full-page tile lights up only when it is on.** It now also lights up for an open blind, a speaker that is on, a robot at work or on its way back, a running script, a streaming camera and someone at home or in a zone. Sensors, numbers, selects, scenes, the weather and the sun stay plain, because Home Assistant calls them active all the time; the sun no longer lights up by day.
- **The top bar knows the same alarms.** A heat, sound or lock sensor and a low battery now turn red in the top bar too. That part is the add-on's and needs no firmware.
- A closed blind's small slider keeps its colour while its tile is grey, as in Home Assistant.
- Needs firmware 0.2.71: press **Update** on the screen. Includes everything from 0.2.84. CYD firmware: 1,677,488 bytes, 91.4 % of the update slot (576 bytes more than 0.2.84).

## 0.2.84 (firmware 0.2.70)

One shared screen for every board: the two board profiles became one core plus a small file per board.

- **`packages/core.yaml` is the screen, every board builds from it.** Before, the CYD and the Guition each had a 5,000-line profile of which 87 % was the same text; every change had to be made twice, and the two had drifted apart in small ways. Now the LVGL tree, the cards, the scripts, the API actions, the entities and the fonts live once. A board file under `packages/boards/` holds what is that board's: its hardware, a table with its 84 sizes and font sizes, the lines of C++ only it adds to a shared lambda (named *hooks*, 18 of them), and its own parts (the CYD's calibration wizard, the Guition's camera images and Rotation). docs/PROFILES.md explains the files and how a new board is added: copy the nearest board file, fill the table, go through the hooks.
- **Nothing changes on a screen.** `packages/cyd.yaml` and `packages/guition.yaml` keep their names and places, so a screen installed from ESP Screens builds as before, and the firmware stays 0.2.70: the C++ ESPHome generates for each board was compared line by line with that of the old profiles, through the checkout profiles and through the GitHub route the add-on uses. Every value, every lambda and every component is the same; what differs is whitespace, line numbers, the order in which ESPHome lists fonts, entities and scripts, one boot lambda on the CYD that now holds the calibration setup together with the effects page's hooks (the same statements in the same order), and the alert's picture frame on a Guition being created after the OK button (they never overlap). docs/TEST_RESULTS_0284.md has the method and the figures.
- `tools/check_packages.py` (run by `tools/check.sh` and CI) fails when a board file leaves out a name the core uses, so a new board cannot forget a size or a hook; `tools/generate_packages.py` is gone, there is nothing to generate any more.
- No firmware update: press nothing on the screens. A screen that is built again anyway gets the same code: the CYD image is 1,676,912 bytes, 91.4 % of the update slot, 1,440 bytes more than the same 0.2.83 built on the same computer (the Guition 1,536 bytes more), all of it in ESPHome's generated `setup()` where the components are now registered in the merge's order; every lambda, every string and every font is the same size as before.

## 0.2.83 (firmware 0.2.70)

A lamp's modes on the screen: effects, palettes and presets of a WLED, and the effect of any light that has one.

- **An effects page behind the light's colour card.** A light that offers effects (a WLED, a Hue with its candle effect) gets a sparkles key at the top right of its colour card. It opens a page with one row per thing the lamp offers: the light's *Effect*, and the select entities on the lamp's device (a WLED's *Color palette*, *Preset* and *Playlist*), each with what it is set to. Under them a slider per number entity of the device (a WLED's *Speed* and *Intensity*). Nothing is hardcoded for a brand: the rows, their English names and their icons are what Home Assistant lists for the device, so another lamp shows its own rows and a lamp without any shows none.
- **A picker that turns like a drum.** A row opens LVGL's roller with every name Home Assistant has at that moment, the effects alphabetically with *Solid* on top and a select's options in Home Assistant's order. Turn it to a name and press the check at the top right: that sends one action (`light.turn_on` with the effect, `select.select_option`; a slider sends `number.set_value` when you let go), the row shows the choice at once, and the back key sends nothing. The list is asked for when the picker opens (event `esphome.screen_options`, answered with `op: options`, one page of names per message), so the screen holds no list while it is closed and a WLED update shows its new effects the next time.
- **The tile names the effect.** A light tile reads *TV Simulator* instead of *100 %* while an effect runs; *Solid*, *off* and *None* count as none.
- Needs firmware 0.2.70: press **Update** on the screen. Includes everything from 0.2.82. CYD firmware: 1,675,424 bytes, 91.3 % of the update slot (20,288 bytes more than 0.2.82: LVGL's roller is compiled in for the first time, plus the page and five icons).

## 0.2.82 (firmware 0.2.69)

The page buttons can make way, and the tiles fill the screen.

- **Page buttons: a setting to take the bar under the tiles away.** Turned off, a screen with more pages has no buttons under its tiles, and the three rows of cards share their room: every card grows by 14 px on a Guition (108 to 122) and 9 px on a CYD (52 to 61). Pages then change by swiping or with *Go to page* tiles. It sits with the other screen settings: on the screen's own settings page (Screen), in the editor's *Screen settings*, and as `switch.<screen>_page_buttons` in Home Assistant. On by default. (GitHub issue #9)
- **The editor says which pages you can't reach.** With the page buttons and swiping both off, only *Go to page* tiles change the page. The editor then says where your *Go to page* tiles lead and which pages that leaves out ("You have 3 Go to page tiles, to pages 1, 2 and 3, but none to page 4, so you can't reach it"), and it names a page with no way back to page 1. The warning shows above the pages and under the setting.
- **New page buttons: a chevron in each corner and a dot per page.** The words *Previous* and *Next* and the "2 / 4" are gone. Each half of the bar is still one big key and lights up under your finger. On the first and last page the chevron that leads nowhere is dimmed. The settings page on the screen uses the same buttons.
- **A screen with one page uses the whole screen.** Its bar was already hidden, but the tiles kept their size. Now they grow into that room the same way.
- A card keeps its layout as it grows: the name, state and circle stay in its middle, and the analog clock on a single tile keeps its dial size so the date beside it still fits. The small slider of 0.2.81 still claims the whole card when the card is taller.
- Needs firmware 0.2.69: press **Update** on the screen. Includes everything from 0.2.81. CYD firmware: 1,655,136 bytes, 90.2 % of the update slot (1,632 bytes more than 0.2.81).

## 0.2.81 (firmware 0.2.68)

A card's slider takes the whole card, and a quick drag on it never turns a page.

- **Dragging anywhere on a card with a small slider drags the slider.** The strip at the bottom of a compact card is 8 px high on a CYD, so a finger that landed a little above it pressed the card instead: the light's card opened, the light toggled, or a quick drag turned the page. The whole card now belongs to the strip, on both boards. A press that never moves is still the card's tap and a finger resting on it is still its hold, with the card lighting up as before; only a moving finger drags. The log says `Tap beside the strip of light.x: the tile's`.
- **A quick drag on a slider is never a page swipe.** The CYD's swipe between pages caught fast drags on sliders and turned the page without a word in the log. The log now says `page swipe: page 0 -> 1` when a swipe turns a page and `page swipe ignored: a slider is being dragged` when a slider had the finger. A swipe that starts on a card with a slider no longer turns the page: start it on another card, between cards, or use the buttons. The Guition's flick rule leaves a slider's drag alone the same way.
- **A second drag right after the first counts.** A slider's send within 600 ms of its previous one was dropped as a bounce, silently. That window is for buttons; a slider sends once per touch, on release.
- **The edge band on a CYD is 20 px** (was 56). Its resistive panel reports a finger up to the bezel, and on a single card's 131 px slider the old band turned a release at 71 % into 100 %. The Guition keeps its centimetre.
- Needs firmware 0.2.68: press **Update** on the screen. Includes everything from 0.2.80. CYD firmware: 1,653,504 bytes, 90.1 % of the update slot (720 bytes more than 0.2.80).

## 0.2.80 (firmware 0.2.67)

A slider swiped off the edge of the glass goes all the way.

- **Swiping a slider off the screen sets it to the end.** A fast swipe to the right that leaves the glass ended at 93 to 98 % instead of 100 %: a capacitive panel loses a fast finger 30 to 50 px before the edge, and a wide tile's slider ends only 29 px from it, so the screen never saw the finger past the end (measured on a Guition: the last touch landed 33 to 48 px inside the edge, seven times out of seven). A slider whose end lies within about a centimetre of the left or right edge now takes a finger let go in that band as that end: off the right is 100 %, off the left is the minimum (1 % for a light, as in Home Assistant, where a pointer past the bar's end counts as its end too). Letting go anywhere else keeps the exact value. Tile sliders and the sliders on the light card do this; `SLIDER_EDGE_SNAP_PX` in the board profile sets the band (Guition 67 px, CYD 56 px, 0 turns it off). The log says when it happened (`Let go 39 px from the right edge: slider 973 -> 1000`).
- Needs firmware 0.2.67: press **Update** on the screen. Includes everything from 0.2.79. CYD firmware: 1,652,784 bytes, 90.1 % of the update slot.

## 0.2.79 (firmware 0.2.66)

A blind's bar reads the same way on the tile and on its card.

- **The small slider of a blind fills with the closed part.** A closed blind is a full bar, an open one an empty bar, and dragging to the right closes it, as on the blind's card and in Home Assistant's own cover dialog, where the blind hangs down from the top. Before, the tile filled with the open part, so a closed blind looked open next to its card. The editor's mockup draws it the same way. The position in the text stays how far the blind is open, as Home Assistant says it.
- Needs firmware 0.2.66: press **Update** on the screen. Includes everything from 0.2.78.

## 0.2.78 (firmware 0.2.65)

Fixes from a full test round of 0.2.72 to 0.2.76, a light switch that works in the dark, and a way back to the menu.

- **The analog clock on a single tile ticks again.** Since 0.2.74 its second hand stood still; only the wide and full-page clocks moved.
- **A full-page light switch works with one push in standby.** On a dimmed screen the first touch only woke it, so the switch by the door needed two pushes most of the day. On a page that is one full tile switching something on or off, the waking push now switches it too; every other page still only wakes.
- **A swipe is never a tap (Guition).** A quick flick or wipe across a tile, a full-page light above all, switched it. A swipe now only swipes, and a finger that slides off a tile before letting go no longer taps it, as 0.2.33 meant. A firm press that drifts a little still counts.
- **Previous and Next react to a firm or slow press.** A press longer than about half a second did nothing; the pages of the screen's settings page too.
- **The same Go to page tile can sit on several pages**, such as a way back to page 1 on every sub-page. *Goes to page* lists the pages the screen has plus the next one, marked *(empty)*. Claude in Home Assistant names each copy by its page or spot. Needs firmware 0.2.65.
- **Save refuses what could never reach the screen**, with a sentence that says why: tiles whose entity IDs together are too long for one message, or tiles that don't fit on eight pages. Before, such a layout saved and then kept failing to send. Big layouts with actions on their taps save again (the request limit went from 16 to 128 KB).
- **A screen that is offline or restarting keeps its 48 tiles** in the editor and can still be saved: ESP Screens uses the firmware version Home Assistant remembers for the device instead of treating it as a very old screen.
- **Editor:** clicking the open screen in the sidebar (the way back from Firmware & USB, Alerts or Settings) no longer throws away unsaved changes, and a change made while *Save & send* is on its way stays unsaved. Every tile's settings have a *Page* row to move it without dragging, and on a phone the pages scroll sideways and a dragged tile reaches page 2 and beyond. When Home Assistant refuses *Identify* or *Try it*, the editor says so instead of "That didn't work". *What's new* no longer shows asterisks. The editor opens faster: the browser keeps its scripts and fonts.
- **The app stops in a moment** instead of ten seconds, and a firmware build that is running stops cleanly. An unreadable changelog no longer stops the app from starting.
- **The screen stays up when memory runs out:** a layout the screen has no room for is refused with a message instead of crashing it. Tiles 33 to 48 no longer redraw the whole page on every change. The CYD firmware is about 14 KB smaller (LVGL's unused Montserrat font is no longer built in).
- Every push now runs the release checks on GitHub (`tools/check.sh`), including a compile of both firmwares and a flash budget for the CYD. The guides match the current editor (48 tiles, the sidebar), and the 0.2.75 notes now give the real cost of the smoother icons: 108 KB, 90 % of the CYD's update slot.
- Needs firmware 0.2.65: press **Update** on the screen. Includes everything from 0.2.77.

## 0.2.77 (firmware 0.2.64)

A media card like a phone's "now playing", with the album cover on a Guition.

- **The media card is new.** Tap a media player's tile and the card shows the album cover, the title, the artist and the album, a progress bar that runs while the track plays with the elapsed and total time at its ends, three round keys (previous, play or pause on the blue key, next) and a volume row: a mute key, a wide slider with a round knob, and the percentage. The keys the player does not offer are faded, the mute key and the slider follow what Home Assistant reports (a muted player shows a grey fill and *Muted*), and a player that is off shows one power key. A stream without a length shows no bar and no times. It works in the light and the dark look.
- **The album cover** comes the way camera images do (app 0.2.66): the screen asks ESP Screen Manager, the app fetches the picture from Home Assistant with its own access, makes it exactly the size the card asks for with the corners already rounded over the card's colour, and serves it on port 8098. A Guition loads it once and keeps it until the picture changes, the card closes or the page turns. The CYD has no memory for pictures and shows the player's icon in the cover's place, as it does when a player has no picture (a radio station, a player that is off).
- **A media tile over the whole page** (size *Full page*) is the same card under the tile's head: the cover at the left, the track, the bar and the keys beside it, the volume row along the bottom. The keys and the slider work on the tile; holding the tile still opens the card.
- **One picture at a time.** A download shares the screen's loop with touch and drawing, so a Guition never loads two pictures at once. An alert closes an open card, and the card's cover goes with it. A media tile over the whole page stays under the alert, and there the alert's picture goes first: a cover that has not started waits until the alert's picture is there, and a cover already on its way finishes before the alert's picture starts. A camera full screen and the cover share one picture, so they never load together. Memory is not the limit: the pictures live in PSRAM (a cover about 70 KB, the alert's 172 KB).
- **The card's clock runs on the screen.** Home Assistant reports where a track was and when; the bar and the elapsed time run on from there every second without any traffic, and stand still while the track is paused.
- Claude in Home Assistant and the editor need nothing new: a `media_player` tile is the same tile, with the new card behind it.
- Needs firmware 0.2.64 for the new card; the app serves covers only to a Guition on that firmware. Older firmware keeps the old card. Includes everything from 0.2.76.

## 0.2.76 (firmware 0.2.63)

The CYD in the editor shows the whole tile again.

- **A tile on the mockup looks like the tile on the screen.** Both boards draw a normal tile with the icon on the left and the name and value beside it; the editor stacked the icon, the name and the value on top of each other. On a CYD's short tiles that did not fit, so the value under the name was cut in half (*26.0 °C*, *Cleaning*, *Off*) and a large value hid the name. Now the mockup uses the screen's layout on both boards: icon left, name and value next to it, the small slider underneath, and for a large value the name at the top with the number below it.
- Only the editor changed. There is no new firmware: 0.2.63 stays current. Includes everything from 0.2.75.

## 0.2.75 (firmware 0.2.63)

Smooth icons on the CYD: the power ring is a ring again.

- **Every icon is drawn with sixteen shades instead of two.** The icon fonts of both boards were rendered at one bit per pixel, the default ESPHome falls back to when a font does not say otherwise, while the text fonts already had four. On the CYD, at 18 and 28 pixels, that made a thin stroke such as the ring of the power icon lumpy and uneven; the edges of every other icon were ragged too. The icons now get the same four bits per pixel as the text, on the Guition as well, so both brands look alike.
- **Costs the CYD 108 KB of flash** (90 % of its update slot is in use now, was 84 %) and no memory: fonts live in flash. The first count, 95 KB, was taken before 0.2.74 added the big icon font of the full-page tile.
- Needs firmware 0.2.63: press **Update** on the screen. Includes everything from 0.2.74.

## 0.2.74 (firmware 0.2.62)

Forty-eight tiles, a tile over the whole page, and tiles that go to a page.

- **Up to 48 tiles per screen**, one for every slot of the eight pages (twenty before). A screen only pays for the tiles it has: the firmware keeps a list as long as the layout instead of a fixed twenty, and on a Guition that list lives in PSRAM.
- **Full page.** A tile's size can now be *Full page*: it takes all six slots of a page and is one big button, so a screen on the wall next to the door switches the light when you push anywhere on it, without looking. While the light is on the whole card lights up in the state colour (amber for a lamp, purple for a scene, blue for a blind), so you see from across the room whether it is on. Holding it still opens the card. A small slider, direct controls or a graph sit at the bottom of the page, big enough for a thumb; the room above them is still the button. The clock, the weather (now with the next hours under the days) and the sun path fill the page. A tile you make full-page keeps its page: the other tiles there move to the first free spots after it.
- **Go to page.** A new built-in tile, *Go to page*, opens the page you choose: an arrow (or an icon of your own), its name and the page number, with a chevron like the rows in Home Assistant's settings. Put a full-page light switch on page 1 and a menu of *Heating*, *Blinds* and *Vacuum* on page 2, each with its own page.
- Claude in Home Assistant can do the same: `size: full` on a tile, and `screen.page` with `to_page` for a navigation tile. The screen's sensor reports both.
- Needs firmware 0.2.62: press **Update** on the screen. Includes everything from 0.2.73.
- Going back to an app older than 0.2.74 after using more than 20 tiles or a *Go to page* tile: that app stops at startup ("Choose at most 20 tiles." or "This entity isn't supported."), and the saved layouts (`screens.json`) stay untouched. Before going back, trim the layout to 20 normal tiles, or restore the app's backup (the Supervisor restores the version and its data together).

## 0.2.73 (firmware 0.2.61)

A new editor, built as a Vue app, with the same firmware.

- **One workspace instead of one long page.** Your screens sit in a sidebar on the left, the screen you chose fills the middle, and the entity library sits on the right. The big title, the separate Settings view and the sticky save bar are gone: **Save & send** appears in the head the moment something changed, and says *Saved · sent to screen* when it is done.
- **Tile settings in a drawer.** Tap a tile and its settings slide in from the right; the mockup stays visible, so a wider tile, another background or a direct control shows up on the page while you choose. Tap another tile and the drawer follows. Esc or a tap beside the pages closes it.
- **Pages side by side.** The pages of a screen stand next to each other, at the screen's own shape (square for a Guition, 4:3 for a CYD), the way you swipe through them. Dragging from the library onto a page and between cells works as before, with mouse and touch; drop past the last page for a new one.
- **The top bar is part of the mockup.** Tap the bar on any page to name the screen and choose its items; the drawer shows every item as the screen draws it. Adding the time, the date, the dial or an entity happens in the same drawer.
- **Screen settings as a tab** next to Layout, with the same rows as the settings page on the screen. **Read current data** and **Override YAML** live in the ··· menu of the screen; New screen, Firmware & USB, Alerts and the app Settings are pages of their own, reached from the sidebar.
- **Live values on the mockup.** The tiles show what Home Assistant reports right now: the temperature with its unit, On or Off with a lit icon, the heating's current temperature and setpoint, the volume, a cover's position, the song that plays. Sliders and switches on the cards stand where they stand on the screen. The page asks every eight seconds while it is open.
- **Identify.** The ··· menu of a screen has Identify: the screen shows a short card and blinks its backlight, so with three screens you know which is which. Needs firmware 0.2.31 or newer, like every alert.
- **Try an alert.** The Alerts page opens with Try it: fill in the same seven fields an automation sends, choose one screen or all of them, and Send. The result says how many screens showed it and which fields were left empty.
- **Copy, export, import.** The ··· menu copies the layout of another screen onto this one, exports the layout as a JSON file (and to the clipboard), and imports one. An imported layout is trimmed to what the screen's firmware holds, and nothing is sent before you press Save & send.
- **A smarter library.** A room filter and Hide placed next to the domain chips; a lit icon for a light, switch or fan that is on, a grey one for an entity Home Assistant can't reach. ⌘K (Ctrl+K) opens a search over screens, entities and actions: open a screen, add an entity to the page you have open, save, identify, export.
- **Updates with content.** The Update badge has What's new: the changelog lines since that screen's firmware. A running update shows a progress bar with its stage (building, writing over Wi-Fi, waiting for the screen, checking it stays up) and the last line of the ESPHome log; Settings → Firmware updates shows the log's tail.
- **Dark mode follows your browser**, as Home Assistant's own Auto theme does.
- Same add-on API, same data, same firmware: nothing to update on the screens. The page is now built with Vue and Vite (`web/`); its files carry a hash of their content, so an update never runs an old script against a new page.

## 0.2.72 (firmware 0.2.61)

Next, Next, Next: the page buttons keep up with your finger.

- **Tap through the pages as fast as you like.** Tap Next three times in a row and you are on page 4, whether or not the pages in between had finished drawing. Before, a second tap on the same button within 600 ms was dropped as a bounce, the rule that keeps a light from switching twice on one tap, so every page made you wait before the next tap counted. The page buttons now follow the rule of the -/+ keys: every clean tap counts, and only a contact within 150 ms of the last one on the same button is taken for a bounce.
- **Previous does the same**, and tapping past the first or last page still changes nothing.
- Needs firmware 0.2.61: press **Update** on the screen. Includes everything from 0.2.71.

## 0.2.71 (firmware 0.2.60)

A small slider stays where you leave it while the lights fade towards it.

- **No jump back after a drag.** Drag the small slider on a light tile and let go, and it stays at that value while your lamps fade up or down. Before, a slow lamp or a group of lamps reported every step of the fade, and the slider jumped back to the old value and then crept up to the new one. The value on the tile follows the slider. The same goes for a fan's speed and a speaker's volume; a blind's position slider still follows the blind as it moves, because that is what it is for.
- **Home Assistant still has the last word.** The slider lets go the moment Home Assistant reports a value within 3 % of what you asked, reports the light off, or refuses. A device that stops short, such as a fan that only knows 33, 66 and 100 %, shows its own value a moment and a half after its last report. Without any report at all the slider goes back with the wait, after three seconds, and no hold lasts longer than eight.
- **A drag on an off light lights the tile up at once**, as a tap does since 0.2.70.
- Needs firmware 0.2.60: press **Update** on the screen. Includes everything from 0.2.70.

## 0.2.70 (firmware 0.2.59)

A tap looks instant, and the spinner only shows up when something really takes a while.

- **A switch flips at once.** Tap a light, switch, helper or fan and the tile shows the new stand right away, as Home Assistant's own switch does, instead of a spinner over the tile. Home Assistant's own state confirms it a moment later. Refuses it, then the tile says Refused and the old stand comes back.
- **No spinner for a normal command.** Home Assistant answers in about half a second, and for that long the tile now shows nothing at all. Takes it longer, then the spinner appears as before. On Max's house every command measured was answered in 342 to 599 ms, and every one of those showed a spinner for a full second before.
- **A command that changes nothing lets go.** Press Stop on a cover that already stands still and Home Assistant reports nothing new. The screen used to wait six seconds; it now lets go a moment after Home Assistant says the command went through.
- **Nothing waits longer than three seconds.** A screen that gets no answer at all, because Home Assistant is older or may not perform actions, gives up after three seconds instead of six.
- **The cards, keys, chips and sliders follow the same rule**, and they all ask Home Assistant for an answer now, so a refusal shows up wherever you press.
- Needs firmware 0.2.59: press **Update** on the screen.

## 0.2.69 (firmware 0.2.58)

A very large sensor value no longer stops a screen's updates.

- **A screen kept getting updates.** Since 0.2.67 a sensor tile with a display precision rounds its value as Home Assistant shows it. A value with more than 28 digits, such as `1e30` from a template or counter, made that rounding fail, and the screen with that tile then got no layout or state updates at all until the value changed. Such a value now shows as it is, and the rest of the screen goes on.
- No firmware change: firmware stays 0.2.58. Includes everything from 0.2.68.

## 0.2.68 (firmware 0.2.58)

Put a new screen on from your own computer.

- **Download the firmware.** **New screen** has a new choice under **Install via**: **Download · flash from your own computer**, for when the machine running Home Assistant is out of reach of the screen, such as a server, a virtual machine or a Docker host. ESP Screens builds the firmware as always and then offers the file, such as `kitchen.factory.bin`, with three steps: plug the screen into your computer, open ESPHome Web in Chrome or Edge and click Connect, then Install with that file. Pairing works as before, and after the first install every update goes over Wi-Fi.
- **USB on the Home Assistant machine stays first.** The list always starts with USB, also before a board is plugged in, and picks the board as soon as it shows up. **Download** and **Later** stay chosen once you pick them.
- **Firmware & USB** has the same **Download** choice for an existing profile: **Build & download** gives you that profile's file. Its USB entry is there before a board is plugged in too, and the list follows a board you plug in while the window is open.
- **Only a fresh file.** A download is always the result of the latest successful build of that profile: while a build runs or after one fails, there is nothing to download. The file holds your Wi-Fi password and the screen's keys, and the window says so next to the button.
- **The card under My screens knows.** A screen whose firmware was downloaded but isn't in Home Assistant yet says so, and what comes next.
- **The device name is checked while you type.** Current Chrome ignored the check behind **customize**, so a name with a capital or a space was only refused after clicking Install.
- No firmware change: firmware stays 0.2.58. Includes everything from 0.2.67.

## 0.2.67 (firmware 0.2.58)

Tiles take what they can do, their words and their icons from Home Assistant, and a tap can run any action Home Assistant offers.

- **On / off for blinds, curtains and garage doors.** Under **On tap**, a cover now has **On / off**: a tap opens or closes it, and stops it while it moves, with Home Assistant's own `cover.toggle`. Holding the tile still opens its card. The same goes for everything else Home Assistant can toggle, such as a script, not only for lights, switches, fans, speakers and climate.
- **Perform action.** Under **On tap**, choose **Perform action** and pick one of the actions Home Assistant has for that entity, under Home Assistant's own names: for a blind that is Open cover, Close cover, Stop cover, Toggle cover, Set cover position and the tilt actions, plus what its integration adds, such as Snapshot for a Sonos. A chosen action shows its fields as Home Assistant describes them: a number with its unit, On or Off, a choice from a list, or text. A field you leave empty is not sent, a field Home Assistant needs is marked until you fill it in, and only fields that fit the device show. Holding the tile still opens its card.
- **The choices come from Home Assistant.** ESP Screens asks Home Assistant which actions each entity has, instead of keeping a list of its own. The tile settings only offer what works: no On / off for a speaker that can't turn on and off, no small slider for a lamp that only switches, no position slider for a cover without a position, no graph for a sensor without numbers, and no forecast for a weather service without daily forecasts. An integration or device that adds an action shows it right away, without an update of ESP Screens.
- **Nothing you set changes by itself.** A tile keeps every setting it has. When Home Assistant can't do one, such as On / off on a Sonos, the tile settings show a warning and what to choose instead. A new setting Home Assistant doesn't support is refused when you save, also when Claude in Home Assistant asks for it.
- **Refused shows on the tile.** When Home Assistant refuses a tap's action, the tile says Refused for a few seconds instead of waiting with a spinner. This goes for Perform action, On / off and the other taps.
- **Numbers as Home Assistant shows them.** A sensor with a display precision in Home Assistant shows that many decimals on its tile and card: 21.456 °C becomes 21.5 °C when Home Assistant shows one decimal. A sensor without one keeps its value as it comes. Rounded values also mean fewer updates for the screen when only the hidden decimals change.
- **Home Assistant's words instead of raw states.** Where a tile or card showed a state as Home Assistant stores it, it now shows Home Assistant's own word: a blind says Open or Closing instead of open or closing, a speaker Playing, a robot Returning to dock, a washing machine Rinsing, and a select of an integration its option's name, such as Vacuum and mop. The top bar and history timelines do the same, the vacuum card's chips name a setting the screen has no short name for as the integration does (Off (raised brush)), and the editor's inspector says Heat/Cool instead of heat_cool. The words come from Home Assistant, so a new device brings its own. The screen's own words stay where it had them: On and Off, Docked, a door's Open and Closed, the person's Home and Away, the chips' Vac & mop and Normal.
- **Home Assistant's icons.** A tile without an icon of its own now shows the icon Home Assistant shows for it: a blind open or closed, a speaker that plays, a door that is open, a battery at its level, a thermostat for climate, a palette for a scene. The icon follows the state, as in Home Assistant, and the tile, the top bar and the editor show the same one. Where the screen lacks Home Assistant's icon, such as an integration's own or one a later Home Assistant adds, it keeps its own icon. An icon you chose stays.
- **A double-width tile gets a control that works.** When its usual control isn't there, such as open, stop and close on a skylight that only has a position, it takes the first one Home Assistant offers.
- **A scene or button that never ran works right away.** Home Assistant shows a scene, button or input button that was never used as unknown, and still lets you press it. The tile said Unavailable and did nothing; it now says Never run and runs when you tap it.
- **The entity list only shows what can be a tile.** Locks, trackers, counters and the other entities for the top bar no longer show under All or in a search, where adding one failed when saving. Input buttons have their own badge and show under Actions.
- **A click on the text under a setting no longer changes it.** Clicking the explanation under Direct control pressed the first choice above it.
- **Claude in Home Assistant can set it.** A tile event takes `action` and `data`, such as `action: cover.set_cover_position` with `data: {position: 50}`, and says what's missing when Home Assistant wouldn't take it. The skill also says what On / off does. Install it again from Settings → Claude to get it.
- Needs firmware 0.2.58 for On / off on covers and other entities that are new to it, Perform action, Refused on the tile, a scene or button that never ran, and the words and new icons on tiles: press **Update** on the screen. Until then a tap opens the card or taps as Automatic, as before. Everything else works right after updating the app, including the rounding and the words in the top bar, timelines, chips and inspector.

## 0.2.66 (firmware 0.2.57)

Camera images on the Guition: see who is at the door.

- **An alert with a picture.** Add `camera: camera.front_door` to the `esp_screens_show_alert` event and a Guition shows the camera's picture of that moment across the top of the alert card, with the title and subtitle under it. A tap on the picture opens the camera full screen over the alert; Back returns to the alert. Any `camera.*` or `image.*` entity works. Other screens show the same alert without the picture.
- **A camera tile.** Add a `camera.*` or `image.*` entity as a tile on a Guition. A tap opens the image full screen, with the round back key at the top left like on every card, and the image refreshes every four seconds, at a steady pace, while it is open. It is not video: ESPHome has no video decoder. Standby and **Back to page 1** close it, and a new alert closes it before it opens.
- **How it works.** The screen never gets a Home Assistant token. ESP Screen Manager fetches the snapshot, makes it exactly as large as the screen draws it and serves it on a new port, **8098**, under a random link that stops working when nobody uses it. On Home Assistant OS the app opens that port itself; keep it at 8098. docs/CAMERA.md has the details, Docker included.
- **Smooth while it loads.** The image arrives as an uncompressed BMP, which the Guition decodes piece by piece while it downloads; a JPEG held the screen for more than half a second per image, long enough to miss a tap. The app fetches the camera's next snapshot each time the screen loads one, so a new picture follows every four seconds instead of after one and a half seconds one time and six the next. A slow camera makes the picture older, never the screen slower.
- **The alert's picture is the moment it rang.** It stays as it was when the alert came in; tap it for the camera now.
- **The Guition builds with ESPHome 2026.8 and newer.** Its firmware no longer uses a backlight fader of its own, which reached into ESPHome's LEDC output; ESPHome 2026.8 closed that off, so **Install** in ESPHome Device Builder failed for a Guition. Standby now dims through ESPHome's own light transition, like any light. Updating from ESP Screens was not affected.
- **The Claude skill and the Alerts cheatsheet** describe the `camera` field. Install the skill again from Settings → Claude to get it.
- Needs firmware 0.2.57 on the Guition: press **Update** on the screen. The CYD gets 0.2.57 too, without camera images: it has no memory for them.

## 0.2.65 (firmware 0.2.56)

Wake lights the screen, and ESP Screens lets you pick the screen.

- **Wake is for the light.** The **Wake** button in Home Assistant still turns a screen in standby up to its normal brightness, brings back the second hand of an analog clock and starts the standby time again. It no longer counts as a touch for **Back to page 1**: that keeps counting from the last time someone touched the screen. An automation that presses Wake on every motion used to keep an open card or page 2 up for as long as someone moved in the room; now the screen goes back to page 1 on time.
- **Straight to page 1 after standby.** When the Back to page 1 time ran out while the screen was in standby, Wake lights it up on page 1 at once, instead of showing the old page for a moment first. With time left, the page stays.
- **Only a touch counts.** An alert that closes by itself and turning Auto standby on also start the standby time again, but not the Back to page 1 time. Opening the settings page from Home Assistant (`open_settings`) still counts, so that page stays open.
- **ESP Screens opens without a chosen screen.** It used to open the first screen in the list; now you pick one. Until then the page says **Choose a screen**, and with no screens yet it still offers to install one.
- The Claude skill describes the new Wake. Install it again from Settings → Claude to get it.
- Needs firmware 0.2.56 for Wake: press **Update** on the screen. The ESP Screens change works right after updating the app. Includes everything from 0.2.64.

## 0.2.64 (firmware 0.2.55)

A long alert title stays on its own line.

- **An alert's title no longer runs into the text below it.** A title too long for one line, such as "Washing machine is done" on a Guition, wrapped onto a second line on top of the subtitle. It now ends in an ellipsis on one line, as the alert documentation says: "Washing machine is d...". A title that fits looks exactly as before; put the details in the subtitle.
- **Claude knows how long a title can be.** The Claude skill and the alert tips in ESP Screens said the CYD shows about forty characters of a title; both screens show about twenty. Install the skill again from Settings → Claude to get it.
- Needs firmware 0.2.55: press **Update** on the screen. Includes everything from 0.2.63.

## 0.2.63 (firmware 0.2.54)

Dark mode, for a screen beside the bed.

- **Dark mode** is a new switch under **Brightness** on the screen's settings page, in the **Screen settings** of ESP Screens and as `switch.<screen>_dark_mode` in Home Assistant, so an automation can turn it on at bedtime and off in the morning. The screen switches at once, open cards and an alert included, and keeps the look after a restart.
- **The same design, darker.** Nothing moves: a black page, graphite cards with a fine edge, soft white text and grey secondary words. Home Assistant's colours stay where they tell you something: an amber lamp that is on, the orange of heating, the blue of a chosen key, the lines of a history graph. Pastel card colours become deep versions of the same colour, and a pale colour is lifted just enough to read on graphite.
- **Every screen has it:** the tiles and their keys and sliders, the top bar, the weather, climate, light, cover, vacuum and history cards, the settings page, the alert and the busy spinner, on the CYD and the Guition.
- **One place for colours.** Every colour the firmware draws now comes from one table (`components/smart_display/theme.h`) with a light and a dark value; the board profiles no longer write colours of their own. The light look is unchanged.
- **A switch on the settings page shows where it is.** A switch that was on showed its knob at the left each time a settings page opened or turned, until you changed a setting. It now sits at the right from the first moment, which matters now that turning on Dark mode draws the page again.
- **The sun card keeps its sunlight.** The area under the sun's arc turned orange after the card changed state and yellow again a minute later. It stays the soft yellow of the sun.
- Needs firmware 0.2.54: press **Update** on the screen. ESP Screens shows the Dark mode switch only for a screen that has it.

## 0.2.62 (firmware 0.2.53)

On or off at a glance, in Home Assistant's words and colours.

- **A door says Open or Closed.** A binary sensor's tile and card use the words of its kind, the same ones the top bar and the history card show: a door or window Open or Closed, motion Motion or No motion, a leak sensor Wet or Dry, and so on for smoke, battery, connectivity, plugs and the rest. A sensor without a kind still says On or Off.
- **Off looks off.** A light or binary sensor that is off turns grey, as in Home Assistant, and a light without an icon of its own shows a crossed-out bulb while it is off, in the top bar too. An icon you chose stays the same and turns grey, as Home Assistant does with an icon of its own.
- **The history card's heading is right while it loads.** It said On until the history arrived, and a card opened after another one could show that card's word for a moment, such as Open on a motion sensor.
- Needs firmware 0.2.53: press **Update** on the screen. Older firmware keeps On, Off and its colours, and shows an off light in the top bar without an icon.

## 0.2.61 (firmware 0.2.52)

Your own YAML for one screen, kept through updates.

- **Override YAML** on each screen edits a small `<screen>.local.yaml` beside the profile. It is loaded after the shared board package and stays in place when the app or the firmware package updates. New screens get an empty one; an existing profile is attached on the first save, without reformatting the rest of the file.
- The editor has an example that changes the display controller with `!extend` (ESPHome appends package lists, so a bare `id:` would add a second, incomplete display), line numbers, Tab indentation and Cmd/Ctrl-S. **Save & check** runs ESPHome's full validation of the complete profile; a build never starts from an invalid one.
- The screen's name, Wi-Fi, API, OTA, packages, external components and captive portal stay managed and are refused in the override, as are the managed substitutions. Invalid YAML is refused before anything is written, and the file is 12 KB at most.
- No firmware change: firmware stays 0.2.52.

## 0.2.60 (firmware 0.2.52)

Sliders keep their colour while a speaker plays or a blind is open.

- **Coloured sliders for speakers, blinds and numbers.** Since 0.2.42 the volume slider of a playing speaker, the position slider of a blind or curtain and the slider of a number were grey, the colour of a light that is off. Sliders now follow Home Assistant's tile sliders: a speaker that plays, is paused or is idle shows its volume in blue, a cover its position in purple, also when it is closed, and a number its value in teal. A speaker that is off or in standby, and a light or fan that is off, stay grey. This goes for the sliders on double-width tiles and for the small sliders on single tiles.
- Needs firmware 0.2.52: press **Update** on the screen.

## 0.2.59 (firmware 0.2.51)

A history card you can read: axes, an hour, a day or a week, and the value under your finger.

- **History with axes.** Tapping a sensor, a number, a binary sensor or a person, or holding a switch, opens its history the way Home Assistant shows it. Numbers get a line with round values along the side and clock times along the bottom, and their highest and lowest moment as rings with their values. On/off, home and away, zones and a status like a washing machine's get a timeline with the time spent in each state. The value now stays big at the top, with the highest and lowest moment and their times beside it, or how long the state lasted and how often it began: "Open · 22 min, 6 times".
- **An hour, a day or a week.** Three keys below the graph. Every range has the same number of points, just further apart: 24 averages on a line, 96 steps on a timeline. ESP Screens fetches the range when the card opens, from Home Assistant's statistics where the entity has them.
- **Your finger reads the graph.** Hold a finger on the graph and slide: the top of the card shows the value and the time of that moment. On a timeline it shows the state, when it began and ended, and how long it lasted, so a door that stood open for five minutes says 5 min. The graph itself stays as it is, and letting go shows the value now again.
- **Every unit.** Temperatures, percentages, watts, kilowatt-hours, lux and any other unit get an axis in round steps with the decimals the entity shows in Home Assistant. Times follow the screen's 12- or 24-hour clock.
- A switch's card keeps its toggle, top right, and a number's card its slider.
- **The weather card's back button is whole again on the Guition.** Since 0.2.43 the round back button sat half under the card with the current weather.
- Needs firmware 0.2.51: press **Update** on the screen. Screens with older firmware keep their old card.

## 0.2.58 (firmware 0.2.50)

A card for blinds, curtains and garage doors, and three fixes found right after updating to 0.2.57.

- **Cover card.** Tapping a blind, curtain, shutter or garage door opens a card like Home Assistant's own, in the style of the climate and vacuum cards: a tall position slider on which the blind hangs from the top, a tilt slider over slats for venetian blinds, and open, stop and close keys. The key of the direction the cover is moving is filled, and a key that can't move it further is greyed out. A slider shows its value while you drag and sends it when you let go. A battery-powered blind, such as Motionblinds, shows its battery at the top right. The card shows only what the cover supports: a garage door that only opens and closes gets just the keys.
- **Night brightness 0 % now shows in Home Assistant.** A brightness setting whose value is 0 stayed "unknown" in Home Assistant, so ESP Screens could not change it on a screen with firmware 0.2.49.
- **No second layout sensor while a screen restarts.** During a restart ESP Screens took "unavailable" for the screen's device name and wrote `sensor.esp_screens_unavailable`. Home Assistant drops that sensor at its next restart.
- **The entity list is filled when the page opens.** When ESP Screens was busy, such as while building firmware, the page could open a screen before its entities arrived: "No entities found" until you picked a filter, and tile names showing as entity IDs.
- **No stale page after an update.** A browser that keeps old files, as Safari did, could combine the new page with the old script and show an empty Screen settings panel. The page now always loads the script and styles of the version that is running.
- Needs firmware 0.2.50 for the cover card and the brightness fix: press **Update** on the screen.

## 0.2.57 (firmware 0.2.49)

The screen keeps its own settings, and ESP Screens shows them the way the screen does.

- **A setting you change stays changed.** Until now ESP Screens kept its own copy of a screen's settings and sent it along with every full update: after a restart of the app or Home Assistant, every hour and after every save. A change it had missed, because the app or Home Assistant was restarting, came back to the old value, and holding − or + on the screen's settings page could jump back a step. With firmware 0.2.49 the screen owns its settings, and ESP Screens changes them on the screen instead of overwriting them.
- **Every setting is an entity in Home Assistant.** Besides the brightness numbers and Auto standby, each screen now has Night mode, Night starts and Night ends, 24-hour clock, Back to page 1 and after how long, Back to page 1 on standby, Swipe between pages and, on a Guition, Rotation, all under the device's configuration. The settings page, an automation and ESP Screens change the same value, and setting a value the screen already has costs nothing. The Claude skill lists them.
- **New Screen settings panel.** The form under a screen's tiles is now three cards, Brightness, Night and Screen, with the rows of the settings page on the screen: switches, − and + that repeat while you hold them, and chips for the clock and the rotation. A change applies right away, without Save, and a change made on the screen shows up while the panel is open. An offline screen shows its values as unknown until it is back.
- **A missing tile comes back sooner.** The screen now answers ESP Screens' ping directly, so a screen that still lacks its layout or a tile right after an update gets everything again after 30 seconds instead of two minutes.
- **The Settings tile works without Home Assistant.** It did nothing while the screen had no connection, exactly when you want to see "Home Assistant: Not connected" or press Restart.
- **Claude sees the screens again after Home Assistant restarts.** The `sensor.esp_screens_<screen>` layout sensors are written again right after a restart instead of after the next change to a screen.
- **No more forecast errors in the Home Assistant log.** A weather tile only asks for the forecasts its weather entity has. Buienradar has no hourly forecast, and asking for one logged an error about 48 times a day.
- Screens with older firmware work as before, with their settings kept in ESP Screens; a change made on such a screen is no longer sent back to it.
- Needs firmware 0.2.49: press **Update** on the screen.

## 0.2.56 (firmware 0.2.48)

The back button on a card works again.

- **Back works on every card.** Since firmware 0.2.44 the back arrow of the light, colour and climate cards hardly responded, and neither did the button at the top right of the climate card. The invisible strip you hold to open the settings page lay on top of the cards and caught those taps. It now lies under the cards, so holding the top bar only opens the settings page from the tile pages, as intended.
- Needs firmware 0.2.48: press **Update** on the screen. Includes everything from 0.2.55.

## 0.2.55 (firmware 0.2.47)

A colour slider no longer turns red when you let go.

- **Sliders keep the value you let go of.** On a Guition, dragging a light's colour slider and letting go could send red instead of the colour under your finger, and brightness or colour temperature could jump to an end the same way. The touch panel now and then reports a stray touch in the top-left corner just as the finger lifts, and the screen took that as where the finger was. The screen now ignores it. Should a slider still jump when you let go, the ESPHome log says `slider jumped on release`.
- **Setting a screen to what it already has costs nothing.** An automation that sets Standby after or a brightness whenever a light changes runs on every colour and brightness change too, because a state trigger without `to:` also fires on those. Each time, ESP Screens sent the whole screen again, and while the screen redrew its page it briefly stopped reading the touch panel: exactly when you were dragging that light's slider. A value the screen already has is now neither saved on the screen nor sent again by ESP Screens.
- **A repeated layout no longer redraws the page.** The hourly repeat, and a save that changed nothing for this screen, only update the tiles whose state comes in, instead of rebuilding the whole page behind an open card.
- Needs firmware 0.2.47: press **Update** on the screen.

## 0.2.54 (firmware 0.2.46)

The standby code, tidied after a review of Wake and Sleep.

- **One rule for Sleep.** A screen put to sleep with Sleep stays asleep until someone taps it, Wake is pressed or an alert comes in. Switching Auto standby off from Home Assistant used to end it, while the same switch in ESP Screens or on the screen did not; now none of them do. Switching Auto standby off still wakes a screen that its standby time dimmed.
- **Standby closes every card.** The settings page and any open card close when the screen goes into standby, and with "also on standby" on it goes back to page 1 as well. Until now a weather or media card stayed open under a dimmed screen while a light or climate card closed.
- **The backlight light is gone from Home Assistant.** `Display Backlight` (on the CYD `Power Display Backlight`) fought the screen's own brightness: the screen put its level back within a minute, and switching the light off made the screen dark without standby, so taps landed on tiles you couldn't see. Use the brightness numbers and the Wake and Sleep buttons. If Home Assistant still lists the old light as unavailable after the update, you can delete it there.
- Under the hood: standby goes through the same scripts as "back to page 1", every card closes through one call, and a leftover of the old manual profile is gone.
- Needs firmware 0.2.46: press **Update** on the screen.

## 0.2.53 (firmware 0.2.45)

Wake a screen or put it to sleep from Home Assistant.

- **Wake and Sleep buttons.** Every screen has `button.<screen>_wake` and `button.<screen>_sleep` in Home Assistant, pressed with `button.press`. Wake does what a tap does: a screen in standby lights up and the standby time counts again from that moment. Sleep puts the screen in standby right away, just like when the standby time runs out, and also works with Auto standby off: the screen stays in standby until someone taps it, Wake is pressed or an alert comes in. An alert that is showing closes, reported as `remote`.
- **As often as you like.** Neither button saves anything on the screen, unlike the Auto standby switch, so an automation may press Wake on every motion. To reach several screens at once, list their buttons under `entity_id`; don't target an area or a device, because that presses every other button there too.
- **The Claude skill knows them.** Settings → Claude explains both buttons with an example automation. Install the skill again to get it.
- Needs firmware 0.2.45: press **Update** on the screen. Screens on older firmware keep working, without the two buttons.

## 0.2.52 (firmware 0.2.44)

Change a screen's settings on the screen itself.

- **A settings page on the glass.** Hold the top bar of the overview for about a second and a half -- a blue line fills along the top edge while you hold -- and the screen opens its own settings: Brightness, Night, Screen and This screen. Toggles flip on a tap, numbers and times have `-` and `+` (hold them and a time walks whole hours), and a choice like the clock cycles in a chip. A change is saved on the screen, takes effect at once and appears in ESP Screens within a second, so both sides always show the same value.
- **Rotation and swiping are on it too.** Everything you would want to change standing in front of the panel: brightness, standby, night mode and its hours, the 12/24-hour clock, swiping between pages and, on boards that can, the rotation. Tiles and the top bar stay in the editor, where there is a mouse.
- **This screen.** Its name, IP address, firmware version, whether Home Assistant is connected, and a Restart that asks once before it does it.
- **Back to page 1 by itself.** New setting, on by default at two minutes: a card someone opened, or a second page they left behind, closes by itself after that long without a touch. Until now that only happened when the screen went into standby, so with standby off or far away a card could stay up all day. Set the time in ESP Screens or on the screen, or switch it off there.
- **A Settings tile.** Next to the clock card there is now a `Settings` card you can put on a page, for a screen where holding the bar is not obvious. Needs firmware 0.2.44.
- **For Home Assistant.** `esphome.<screen>_open_settings` opens the page (0 menu, 1 Brightness, 2 Night, 3 Screen, 4 This screen, -1 closes it and goes back to page 1), and the Claude skill explains all of it.

## 0.2.51 (firmware 0.2.43)

Ask Claude in Home Assistant to put something on a screen.

- **Tiles from a Home Assistant event.** ESP Screens now listens for `esp_screens_add_tile`, `esp_screens_remove_tile`, `esp_screens_move_tile` and `esp_screens_order_tiles`. An event names the screen (its device name, the name Home Assistant shows, its area or its title) and the entity, and may set the size, the direct control, the display, the icon, the colour and the spot. The app changes the screen and sends it right away, with the same checks as its own editor: at most twenty tiles, an entity once per screen, and a double-width tile in the left column. A tile with a control or a forecast becomes double-width by itself. Every event gets an answer, `esp_screens_tile_result`, with `ok` or the reason it was refused; a refused event changes nothing.
- **A screen you can read.** Every screen also publishes what it shows as `sensor.esp_screens_<device name>`: the number of tiles, and per tile the entity, the page, the row, the column, the width, the control and the display. So an assistant can look before it moves something, and you can use it in a template.
- **The Claude skill knows all of it.** Settings → Claude now also covers tiles: the four events, every field, what each kind of entity can do, how to read a screen first, and the rule to show what it is about to do and wait for a yes. Install it again from the Settings page, then ask for example "put the vacuum on the living room screen", "give the living room lights a brightness slider and make that tile wide" or "order page 1 by how often I use them".
- No new firmware: screens on 0.2.43 need no update.

## 0.2.50 (firmware 0.2.43)

More memory for the CYD, so a busy moment no longer restarts it.

- **Sliders without extra buffers.** The fill of the tile and light card sliders now has the same rounded corners as its track. With the tighter corners it had since 0.2.43, the screen drew every fill into a separate buffer of up to 20 KB on each redraw, and when the CYD ran short of memory it kept retrying until its watchdog restarted it. The end of the fill is now slightly rounder behind the white handle.
- **Leaner tiles.** Climate modes, a select's options, weather, sun and timer times, the media title and the vacuum rows now only take memory on tiles that use them, and a tile keeps a short fingerprint of its last state instead of a full copy. That frees about 16 KB of RAM on the CYD.
- **The old manual setup is gone.** Before ESP Screens existed, tiles were written by hand in the screen's YAML. Nothing used that any more, and it cost a screen memory: 80 Home Assistant subscriptions, its own tap handlers and an old vacuum card it never showed. All of it is out, together with its guides and helper scripts. Choosing tiles, the top bar, the settings and the calibration work exactly as before. The unused sensor **SmartDisplay Action** disappears: Home Assistant shows it as unavailable and you can delete it.
- **No pale flash.** A tap between two tiles, or the tap that wakes a dimmed screen, lit up a pale panel. It stays transparent now, on both boards.
- **Heap Minimum Free.** A new diagnostic sensor shows the lowest free memory since the screen started.
- Firmware 0.2.43 for both boards; the app offers the update.

## 0.2.49 (firmware 0.2.42)

No more flickering stripes on the CYD.

- **CYD panel fix.** The cheap 2.8" panel showed a fine pattern of vertical lines that shimmered when you moved your eyes or the board. The screen now uses frame inversion at the panel's highest refresh rate, which removes the stripes. Colours and contrast are unchanged. Guition screens are not affected.
- Firmware 0.2.42 for both boards (version only on the Guition); the app offers the update.

## 0.2.48 (firmware 0.2.41)

Keep a screen awake from a Home Assistant automation.

- **Auto standby in Home Assistant.** Every screen gets the switch **Auto standby**, the same setting as the checkbox in ESP Screens. Turn it off and a dimmed screen wakes at once and stays on; turn it on and the screen dims again after its standby time, counted from that moment. So an automation can keep the screens on while someone is home and the lights are on or a window is open. A change shows in ESP Screens too and is kept after a restart.
- **The Claude skill knows it.** The skill under Settings → Claude now also covers standby and brightness: the Auto standby switch, Standby after and the three brightness numbers, with an example automation. Install it again from the Settings page to get the new version.
- Firmware 0.2.41 for both boards; the app offers the update.

## 0.2.47 (firmware 0.2.40)

The new climate card comes to the Guition, with fan and swing right on the card.

- **Climate card on the Guition.** The dial is gone here too: the target temperature sits big between two large − / + keys, the number follows every tap and one call goes out when you stop tapping, and holding a key keeps stepping. One row of keys picks the mode in Home Assistant's order and colours.
- **Fan and swing at a glance.** Below the mode keys a white card shows the fan speeds and the swing modes as rows of choices, each behind its icon, like the cleaning settings on the vacuum card. Tap a choice and it shows at once. The card makes room for whatever the device has: with fan and swing everything moves a little closer together, and a thermostat without them keeps a larger setpoint.
- **One mode is no choice.** A thermostat that can only heat no longer shows a single mode key; its setpoint sits in the middle of the card, on both boards. The power key still turns it on and off.
- Firmware 0.2.40 for both boards; the app offers the update. The CYD keeps fan and swing behind ···.

## 0.2.46 (firmware 0.2.39)

Choose between vacuuming, mopping or both on the vacuum card, and a climate card made for the small CYD.

- **Vacuum, vacuum and mop, or mop only.** Robots that offer a cleaning mode in Home Assistant, such as a Roborock (HA 2026.8 or newer), get a row with Vacuum, Vac & mop and Mop on the vacuum card of both screens. ESP Screens finds the mode and the mop intensity on the robot's own device, whatever language your entity IDs are in; you don't have to add them as tiles. Custom (the per-room settings from the robot's app) shows up only while the robot uses it.
- **Only what the mode uses.** Below the mode sit suction power and water as rows of choices: vacuum only shows suction, mop only shows water, both show both. A tap shows your choice at once and the card waits for Home Assistant. Speeds that belong to a mode, such as suction off for mopping, move into the mode row, and Max+ now fits next to Max.
- **A new vacuum card.** The robot, its state and battery on top, with a green bolt while it charges and the room it is in while it cleans; then Start cleaning (or Pause, Resume) and Dock; then how it cleans. On the Guition the cleaning settings share one white card, and Locate became a round button beside the robot. Since HA 2026.8 a vacuum no longer reports its battery itself, so ESP Screens now reads the battery sensor of the robot.
- **Climate card for the CYD.** No more dial to drag on the small resistive screen: the target temperature sits big between two large − / + keys. The number follows every tap at once and one call goes out when you stop tapping; holding a key keeps stepping. One row of keys picks the mode (in Home Assistant's order and colours), and ··· opens fan and swing. A tap only redraws the number or a key, so the card responds right away. The Guition keeps its dial.
- **Less redrawing after a climate change.** A card closed within three seconds of a change left a flag behind that redrew every tile each second; that flag is now cleared.
- Firmware 0.2.39 for both boards; the app offers the update. Update the app and the screens together: with firmware 0.2.39 and an older app the vacuum card falls back to suction only.

## 0.2.45 (firmware 0.2.38)

One alert for every screen, a Claude skill, and a Settings page that clears up the main page.

- **One alert for every screen.** Fire the Home Assistant event `esp_screens_show_alert` with the usual alert fields and ESP Screens shows the alert on every screen that is online, screens added later included. `esp_screens_dismiss_alert` clears it everywhere. Fields you leave out stay empty. A value that doesn't fit, such as a bare `Yes` that YAML turns into true, is left empty with a line in the log instead of losing the alert. The per-screen actions stay as they are.
- **Ask Claude.** Settings → Claude installs an ESP Screens skill for Claude Code in Home Assistant (`/homeassistant/.claude/skills/esp-screens`), or downloads it as a zip for claude.ai. Claude then knows the alert events and every field, color and icon, so "show an alert on all my screens when the mailbox is full" becomes a working automation. Nothing is written until you press the button, and the page says when a newer version of the skill is ready.
- **Settings page.** New screen, Firmware & USB, the firmware updates, Alerts and Claude moved from the header and the sidebar to a page of their own; the header keeps one Settings button. The Update button of each screen stays in My screens.
- **Clearer screen list.** Every screen in My screens sits on a light grey card; the selected screen is white.
- No new firmware: screens on firmware 0.2.31 or newer show alerts for every screen.

## 0.2.44 (firmware 0.2.38)

- **Vacuum card on the Guition.** The state line under the name is gone; the card below already shows it in its badge, and the two sat on top of each other.
- Firmware 0.2.38 for both boards; the app offers the update.

## 0.2.43 (firmware 0.2.37)

A second hand on the analog clock, sliders that look like Home Assistant's, and one top bar for every card.

- **Second hand.** The analog clock card gets a thin red second hand with a short tail that moves every second while the screen is in use. During standby (also at the night level) it is hidden and the clock keeps its once-a-minute redraw, so a sleeping screen does no extra work. Only the hand's own line is redrawn, not the card. The small dial in the top bar stays as it was.
- **Sliders like Home Assistant.** Card sliders (a light's or fan's direct control, the Sonos volume, the brightness row of the colour card) now use the proportions of HA's control slider: softer corners on track and fill, a slimmer white handle a little in from the end of the fill, a track in the fill colour at 20 %, and a short stub instead of a full circle at 0 or 1 %. A light or fan that is off shows only the empty grey track, without fill or handle, exactly as HA does; the colour card's brightness row then reads Off until you move it.
- **A light's slider stops at 1 %.** As in HA, dragging a light's slider all the way down leaves it on at 1 %; tapping the card turns it off.
- **One top bar on every card.** Every card that opens over the tiles (brightness, colour, climate, vacuum, media, timer, switch, sensor history and the others) has the same bar: a round back arrow at the left, big enough for a finger (60 px on the Guition, 40 px on the CYD), and the name in the middle. Only a card with one overriding action keeps a round button at the right, such as the on/off of a climate device; the colour and vacuum cards lose their extra "done" buttons, which only closed the card. The brightness card, which had no button at all, gets the back arrow too.
- **A starting screen says so.** Until the first layout arrives the top bar reads "Connecting to Home Assistant..." and then "Waiting for ESP Screens...", instead of "Choose tiles in HA".
- Firmware 0.2.37 for both boards; the app offers the update.

## 0.2.42 (firmware 0.2.36)

Smoother page swipes and a new colour card for lights.

- **Page swipes that keep up with your finger.** The next page shows up at once as empty cards and fills in two cards at a time, top to bottom, while the screen keeps reading touch in between, so a quick second swipe is no longer lost. On the Guition the longest pause during a swipe went from about 280 ms to about 75 ms, and the page is complete in about a quarter of a second. Swiping past the first or last page no longer redraws the page.
- **Less redrawing overall.** A state change redraws only its own card, and clock cards redraw once a minute instead of every second.
- **Slider handles sit inside the fill**, like in Home Assistant, also at 1 %. A light that is off shows a grey slider end.
- **The busy sheet covers the whole card**, including the controls of a wide card.
- **New colour card for lights.** Colour, colour temperature and brightness each get their own card with a rounded track: a knob in the chosen colour for colour and temperature, and a filled slider with the handle inside for brightness. Lights that only do colour temperature, or only colour, show just their cards. The knob no longer gets cut off at the ends of the track.
- Firmware 0.2.36 for both boards; the app offers the update.

## 0.2.41 (firmware 0.2.35)

See ESP Screens before you install it. What the screens show and what you can set stay the same.

- **Screenshots in the README.** Photos of a Guition at home, both boards with demo layouts (pages, direct controls, the weather, climate, light and vacuum cards, sensor history, an alert) and the ESP Screens page itself: the tiles, tile settings, top bar, Alerts cheatsheet and New screen. The screen images are rendered from the firmware's own LVGL code on a demo home, so they match what the screens draw. The app's page in the App store shows a photo and the editor too.
- Firmware 0.2.35 for both boards, so you can try an update from the app. It only changes the version number.

## 0.2.40 (firmware 0.2.34)

ESP Screens is now in English: the screens, the management page, the Home Assistant entities and the documentation.

- **English everywhere.** Every label on both boards (tiles, detail cards, the climate and vacuum cards, page navigation, calibration), the ESP Screens editor, the Alerts cheatsheet, error messages and logs, and the README and guides. The top bar writes numbers the English way (21.5 °C, 1,249 W). State labels follow Home Assistant's own English names, for example Heat and Cool for climate modes, Heating and Cooling for what the device is doing, Away, Returning to dock, and weather conditions such as Lightning, rainy. Dates use English abbreviations (Mo 14 Sep).
- **English entity names.** Firmware 0.2.34 names its entities Tile settings, Screen firmware, Device name, IP address, Guition screen type, Last boot, Normal brightness, Standby brightness, Night brightness, Standby after and Calibrate touch. Home Assistant registers a renamed ESPHome entity under a new entity id and removes the old one, so `text.kitchen_screen_tegelinstellingen` becomes `text.kitchen_screen_tile_settings`. Dashboards or automations that use one of these diagnostic entities need the new id.
- **Your layouts move along.** ESP Screen Manager recognises a screen that comes back under a new inbox id and moves its tiles, settings, top bar and update history to it, also when the app restarts in between. The **Update** button and the nightly round follow the screen through the rename and report the update as successful.
- **Older firmware keeps working.** Screens on firmware 0.2.33 or older still report the Dutch entity names and status messages; the app recognises both until they are updated.
- Docs use Home Assistant's current menu names (**Settings → Apps**, **App store**, **Settings → Tools**), and the guides are now `docs/TILES.md`, `docs/CALIBRATING.md`, `docs/ACCEPTANCE.md` and `docs/TROUBLESHOOTING.md`.
- Firmware 0.2.34 for both boards; the app offers the update. Besides the English text and entity names it changes nothing on the screen.

## 0.2.39 (firmware 0.2.33)

Zuiniger in dagelijks gebruik, ook met tientallen schermen. Niets verandert aan wat je ziet of instelt.

- **Alleen doorrekenen wat veranderde.** Bij een statuswijziging bouwt de app alleen de tegels (en de bovenbalk) opnieuw waar die entiteit op staat; de andere berichten blijven zoals ze verstuurd zijn. De schermlijst wordt niet meer bij elke wijziging uit het hele Home Assistant-register opgebouwd, maar bewaard tot het register of een schermdiagnose verandert. De live-stream van de beheerpagina volgt dezelfde regel.
- **Historie gebundeld, buiten de lus.** De 24 staafjes van sensortegels komen uit één `recorder/statistics_during_period`-vraag voor alle sensoren tegelijk (uurgemiddelden voor 24 uur, 5-minuutgemiddelden voor 1 en 6 uur), in een achtergrondtaak die elke vijf minuten ververst. Sensoren zonder statistiek (geen state class) houden de oude REST-historie, ook op de achtergrond. De verzendlus wacht nergens meer op de database; een gewijzigde grafiek stuurt alleen die tegel.
- **Keepalive als ping.** Schermen met firmware 0.2.33 krijgen elke twee minuten alleen een klein bericht met de revisie van hun indeling. Komt die niet overeen (herstart, demo-indeling, verloren bericht), dan meldt het scherm `Indeling opnieuw nodig` en stuurt de app alles opnieuw; als vangnet gaat eens per uur toch alles. De inbox-status wisselt niet meer per ronde tussen "Indeling ontvangen" en "Gesynchroniseerd". Oudere firmware houdt de volledige herhaling per twee minuten.
- **Eén actie per bericht.** Firmware 0.2.33 heeft de actie `esphome.<apparaatnaam>_screen_message` die een heel bericht in één keer aanneemt; de app gebruikt die zodra het scherm die firmware meldt. De base64-blokjes van 200 tekens in de tekstentiteit blijven de terugval voor oudere firmware.
- **Rustige diagnostiek.** De diagnostische sensor `Uptime` (elke 15 s een nieuwe waarde) is vervangen door `Opgestart`, een tijdstempel met één waarde per opstart; Home Assistant ruimt de oude entiteit zelf op. De heap-sensoren melden per vijf minuten in plaats van per 30 s, en de vier instellingsgetallen (helderheid, standby) publiceren alleen nog een gewijzigde waarde. Dat scheelt tot honderdduizenden recorder-rijen per dag bij dertig schermen.
- Firmware 0.2.33 voor beide borden; de app biedt de update aan. Alles werkt ook met de vorige firmware, alleen zonder ping en actie.

## 0.2.38 (firmware 0.2.32)

- **Bovenbalk per scherm.** Bovenaan elk scherm staat links de naam en rechts wat jij kiest, tot zes onderdelen: de **tijd**, een **analoge klok**, de **datum**, of een **entiteit met icoon** uit Home Assistant, zoals temperatuur, luchtvochtigheid, verbruik, een deur of raam (open/dicht), het alarmpaneel, een slot, wie er thuis is (`zone.home`) of een telefoon (`device_tracker`). Zonder aanpassing blijft het zoals het was: naam en tijd.
- **Status of "Laatst gewijzigd".** Een onderdeel toont de status zoals Home Assistant hem schrijft (21,3 °C, 65%, 1.249 W, Open/Dicht, Thuis/Weg, Afwezig, de volgende zonsondergang), of hoe lang geleden het veranderde: "Zojuist", "5 min geleden", "Gisteren". Een tijdstempel-sensor telt ook vooruit ("Over 2 uur"). Het scherm telt de minuten zelf, zonder verkeer.
- **Alleen als actief.** Laat een onderdeel alleen verschijnen als het aan, open, thuis of meer dan 0 is, bijvoorbeeld een open deur of een draaiende wasmachine. Actieve onderdelen kleuren zoals in Home Assistant: open deur amber, alarm ingeschakeld groen, alarm afgegaan of slot open rood, iemand thuis groen.
- **Iconen.** Automatisch zoals Home Assistant (een open deur krijgt een open deur-icoon, een temperatuursensor een thermometer), een eigen icoon uit de lijst, of geen icoon.
- **Netjes op het oog.** Alle waarden, de tijd ook, staan in dezelfde letter op de basislijn van de naam; iconen en de analoge klok staan gecentreerd op de cijferhoogte en even groot; de ruimte tussen icoon en waarde wordt gemeten tussen wat je ziet, dus voor elk icoon gelijk. Past niet alles, dan krijgt de naam puntjes en valt het voorste onderdeel weg.
- **Editor.** Nieuw blok **Bovenbalk** met de naam en de onderdelen als kaartjes: slepen om te ordenen, tikken om in te stellen, **＋ Toevoegen** met de tijd, klok en datum, suggesties uit je eigen huis (temperatuur en verbruik uit de ruimte van het scherm, weer, aantal thuis, zon op en onder) en een zoekveld voor elke entiteit. Elke pagina in het schermvoorbeeld toont de balk met Roboto en dezelfde plaatsingsregels als het scherm; onderdelen die niet passen of nu verborgen zijn, zijn gemarkeerd.
- De knoppenbalk **Tegels instellen / Algemene instellingen / Inspector** is weg; de secties staan gewoon onder elkaar. **Klok tonen** is verhuisd naar de bovenbalk (de 24-uursklok blijft bij de scherminstellingen en staat ook bij de klok in de balk).
- Firmware 0.2.32 voor beide borden; de app biedt de update aan. Oudere firmware toont tot de update de naam en, als die in de balk staat, de tijd.
- Voor ontwikkelaars: `tools/render_topbar.py` rendert de echte LVGL-code van de bovenbalk op je computer (ESPHome host + SDL2) naar PNG, voor beide borden, zonder scherm.

## 0.2.37 (firmware 0.2.31)

- **Cheatsheet Alerts in ESP Screens.** De knop **Alerts** bovenaan opent een naslagpagina met alles over `show_alert`: per scherm de exacte actienaam (`esphome.<apparaatnaam>_show_alert`) met kopieerknop en of de firmware het al kan, een kant-en-klaar YAML-voorbeeld per scherm, alle zeven velden met uitleg, voorbeelden en de tekstlimieten per bord, alle iconen met glyph en naam (zoeken, tikken kopieert de naam), de kleuren als stalen, het gedrag (timeout, knop, knipperen, standby, vervangen) en het event `esphome.screen_alert` met een voorbeeldautomatisering die op de knop wacht. Home Assistant toont bij ESPHome-acties zelf geen uitleg of keuzelijsten; deze pagina vult dat gat.
- Geen nieuwe firmware; de doelversie blijft 0.2.31.

## 0.2.36 (firmware 0.2.31)

- **Alert vanuit een automatisering.** Elk scherm heeft nu de actie `esphome.<scherm>_show_alert` met `title`, `subtitle`, `icon`, `color`, `button_text`, `timeout` en `flash`. De kaart ligt op LVGL's toplaag over alles heen (pagina's, kaarten, de standby-laag), wekt het scherm en houdt de backlight op de normale helderheid tot iemand op de knop tikt (`button_text`, standaard Oké), of tot `timeout` seconden (0 is tot de knop; de knop sluit ook een alert met timeout direct). `flash: true` laat de backlight vier keer knipperen bij binnenkomst. Iconen zijn de namen uit de tegelkiezer (ook als `mdi:naam`, of als hex-codepoint van een meegecompileerd glyph); onbekend wordt `alert-outline`. Kleuren zijn de pasteltinten van de tegels; leeg is de witte kaart. Een nieuwe alert vervangt de huidige. Oké, timeout, vervangen en `dismiss_alert` melden zich als event `esphome.screen_alert` met `action`, `title` en `screen`.
- De actie `esphome.<scherm>_dismiss_alert` haalt een alert op afstand weg, bijvoorbeeld als de deur al open is.
- De iconenlijst schrijft nu ook `components/smart_display/tile_icon_names.h` (naam naar codepoint) via `tools/generate_icons.py`.
- Firmware 0.2.31 voor beide borden; de app biedt de update aan. Alleen de doelversie verandert in de app.

## 0.2.35 (firmware 0.2.30)

- **Snelle randveeg pakt nu ook in één keer (Guition).** Op 0.2.29 wisselde de veeg wel, maar ongeveer de helft van de snelle vegen eindigde met `randveeg niet gevuurd: 5 px naar binnen` terwijl de vinger duidelijk verder ging; elke aanraking duurde in de firmware bijna exact 160 ms en leverde maar één meting op. Een druk in de lege rand landde op de achtergrondcontainer en de pagina, en het thema geeft elk object een ingedrukte-stijl (45% dekking): bijna het hele scherm werd bij indrukken en loslaten opnieuw getekend, wat de touch-polling precies zo lang blokkeerde als een flick duurt. De pagina en de tegelcontainer nemen nu geen drukken meer aan (`LV_OBJ_FLAG_CLICKABLE` uit), dus geen hertekening en de metingen komen elke 20 ms door.
- Zolang een randveeg gewapend is, logt de firmware elke meting (`veeg id=0 st=2 x=.. y=..`) en de eerste druk meldt zijn contact-id, zodat de bemonstering uit het log te lezen is.
- Firmware 0.2.30 voor beide borden; de app biedt de update aan. Alleen de doelversie verandert in de app.

## 0.2.34 (firmware 0.2.29)

- **Randveeg werkte in 0.2.32 en 0.2.33 helemaal niet, hersteld.** De veeg was daar op de pointer-events van LVGL gezet, maar de LVGL 9.5.0 die ESPHome meelevert stuurt het invoerapparaat wel PRESSED en RELEASED maar geen PRESSING, dus de veeg kreeg nooit positie-updates (live gezien op Studio 1: wel `GT911 press`, verder niets). De Guition volgt de veeg weer via ESPHome's touchscreen-triggers, zoals in 0.2.24 (dat werkte live zodra de kaartfix uit 0.2.32 erbij zat), met de eigen rotatiemapping gelijk aan die van ESPHome's LVGL-component, de 45°-regel, `end()` bij loslaten (een niet-afgemaakte veeg kan daardoor niet meer bij de volgende aanraking afgaan) en de logregels `randveeg genegeerd: …` en `randveeg niet gevuurd: …`.
- Firmware 0.2.29 voor beide borden; de app biedt de update aan. Alleen de doelversie verandert in de app.

## 0.2.33 (firmware 0.2.28)

- **Guition: loslaten binnen de tegel telt.** De verplaatsingsgrens voor een tik staat op de Guition uit (`TOUCH_MOVE_LIMIT_PX: "0"`); LVGL beslist, zoals iOS: laat je los binnen de tegel waarop je begon, dan is het een tik, verlaat je vinger de tegel, dan niet. Een stevige druk die een centimeter verschoof (73 px op Studio 1) werd anders nog geweigerd. De randveeg neemt zijn eigen tik weg en sliders vangen hun eigen sleep, dus de grens had daar geen taak meer. De CYD houdt zijn 56 px, omdat het resistieve paneel kan springen.
- Firmware 0.2.28 voor beide borden; de app biedt de update aan. Alleen de doelversie verandert in de app.

## 0.2.32 (firmware 0.2.27)

- **Randveeg die nooit pakte, opgelost.** Live meegelezen op een Guition: de veeg werd herkend maar geblokkeerd door de voorwaarde "kaart open". De lichtkaart, klimaatkaart en stofzuigerkaart wisten bij sluiten (kruisje, tik naast de kaart) en bij wakker worden uit standby de interne "actieve kaart" niet, dus na één keer een kaart openen bleef vegen stil geblokkeerd tot de indeling veranderde. Dat gold ook voor de oude veeg over het hele scherm en voor de CYD. Beide borden sluiten kaarten nu via één script (`close_cards`) dat alles verbergt én die toestand wist; wakker worden gebruikt hetzelfde pad.
- **Randveeg op LVGL's eigen manier.** De Guition volgt de veeg nu via de pointer-events van LVGL 9 (`lv_indev_add_event_cb`, PRESSED/PRESSING) in plaats van ESPHome's touchscreen-`on_update`: de coördinaten komen al gedraaid van LVGL (geen eigen rotatiemapping meer), en `lv_indev_wait_release` wordt vanuit LVGL zelf aangeroepen. De richtingseis is versoepeld van "twee keer zo horizontaal" naar "meer zijwaarts dan verticaal" (45°), zodat een schuine duimveeg vanaf rechts ook in één keer pakt.
- **Log zegt waarom.** Een herkende maar geblokkeerde randveeg meldt de reden (`randveeg genegeerd: kaart open`), en een randveeg die zonder paginawissel eindigt meldt hoe ver de vinger kwam (`randveeg niet gevuurd: 28 px naar binnen, 35 px verticaal`), naast het bestaande `randveeg: pagina 0 -> 1`.
- Firmware 0.2.27 voor beide borden; de app biedt de update aan. Alleen de doelversie verandert in de app.

## 0.2.31 (firmware 0.2.26)

- **Vrij slepen, met lege plekken**: de editor werkt met vaste plekken in plaats van een volgorde die steeds wordt aangeschoven. Elke tegel heeft zijn eigen plek (kolom, rij, pagina) en die verandert alleen als jij hem versleept. Lege plekken zijn gewoon lege plekken: naast een enkele tegel, midden op een pagina, waar je wilt; ze blijven staan zodat je kunt ordenen. Sleep een tegel op een lege plek en hij staat daar. Sleep hem op een andere tegel en die twee wisselen: de ander neemt de plek die vrijkwam, of anders de dichtstbijzijnde vrije plek. Alle overige tegels blijven waar ze staan. Tijdens het slepen laat het voorbeeld al zien waar alles terechtkomt; loslaten bevestigt precies dat, loslaten buiten het voorbeeld verandert niets.
- **Naar een volgende pagina slepen**, ook als de vorige nog niet vol is: onder de laatste pagina staat tijdens het slepen een lege pagina klaar. Met **Pagina toevoegen** maak je zelf een lege pagina, die ook bewaard blijft; een lege pagina heeft **Pagina weghalen** (de pagina's erna schuiven op). Maximaal acht pagina's.
- **Lege plek aanklikken**: klik op een lege plek en de volgende tegel uit de kiezer komt daar ("Volgende tegel komt hier"); zonder keuze vult toevoegen de eerste vrije plek. Een tegel die dubbelbreed wordt houdt zijn rij als de plek ernaast vrij is en gaat anders naar de dichtstbijzijnde vrije rij; de buurtegel blijft staan. Dubbelbreed terug naar normaal laat de rechterplek leeg.
- **Geen tekstselectie meer tijdens het slepen**, en een sleep die snel begint start toch (de muis blijft aan de kaart gekoppeld tot de sleep loopt). Pijltjestoetsen verplaatsen een gefocuste tegel per plek; Enter opent de instellingen.
- Firmware 0.2.26 tekent de tegels op precies die plekken: lege plekken blijven leeg en een lege pagina blijft een pagina. Oudere firmware negeert de nieuwe velden en schuift de tegels aan tot de eerste vrije plek, zoals voorheen; de editor meldt dat onder het voorbeeld zolang zo'n scherm een indeling met gaten heeft. Bestaande indelingen krijgen bij het laden de plekken die ze al hadden, er verandert niets op het scherm.
- Opslag en protocol (voor ontwikkelaars): `tiles[].slot` (0–47, absolute plek: pagina × 6 + rij × 2 + kolom; dubbelbreed altijd op een even plek) en `pages` (1–8) zijn additief in opslagversie 1; het layoutbericht krijgt `slots` en `pages`. Firmware 0.2.26 voor beide borden; de app biedt de update aan.

## 0.2.30 (firmware 0.2.25)

- **Groen bolletje voor online schermen**: in de lijst met schermen is het bolletje voor **Online** nu groen, zodat je in één oogopslag ziet welke schermen bereikbaar zijn. **Offline** blijft een grijs open rondje.
- Firmware 0.2.25 voor beide borden; de app biedt de update aan. Inhoudelijk verandert er in de firmware niets, alleen het versienummer.

## 0.2.29 (firmware 0.2.24)

- **Vegen vanaf de zijrand op de Guition**: met **Vegen tussen pagina's** aan wissel je van pagina door vanaf de linker- of rechterrand naar binnen te vegen, zoals terug-vegen op een telefoon. Vanaf rechts naar links is volgende, vanaf links naar rechts vorige. Langzaam of snel maakt niet uit: de veeg begint in een band van 32 px (circa 5 mm) langs de rand en telt na 40 px (circa 6 mm) naar binnen, duidelijk meer zijwaarts dan omhoog of omlaag (`EDGE_SWIPE_BAND_PX`, `EDGE_SWIPE_TRAVEL_PX`). Werkt in alle vier de rotaties. Een veeg die midden op het scherm begint doet niets meer, zodat tikken en slepen op tegels nooit per ongeluk van pagina wisselen; de tegel onder een randveeg krijgt geen tik. Het log meldt `randveeg: pagina 0 -> 1`.
- De CYD houdt de bestaande snelle veeg over het scherm (LVGL-gesture, firmware 0.2.7+); daar verandert niets, de firmware krijgt alleen het nieuwe versienummer.
- Firmware 0.2.24 voor beide borden; de app biedt de update aan. In de app is alleen de omschrijving van de instelling aangepast.

## 0.2.28 (firmware 0.2.23)

- **Tikken die niet doorkwamen**: de firmware gooide een tik weg zodra de vinger tijdens het drukken meer dan 18 px (nog geen 3 mm) van het eerste contactpunt afweek, ver onder LVGL's eigen veegdrempel en ook met "Vegen tussen pagina's" uit. Een vinger die platter wordt of iets rolt haalde dat al. Nu geldt per bord een grens van ongeveer één centimeter (`TOUCH_MOVE_LIMIT_PX`: Guition 67 px, CYD 56 px), gemeten als afstand tot een referentiepunt dat over de eerste vier metingen (circa 60 ms) settelt in plaats van tot het allereerste punt. Eindigt de vinger op een andere tegel, dan vangt LVGL dat nog steeds op (press lost).
- Alleen het contact dat de aanraking begon telt: een tweede vinger of een duim aan de rand geldt niet meer als verplaatsing (`touch.id` van de touchscreen-component).
- De minimale contactduur is per bord (`TOUCH_MIN_PRESS_MS`): 60 ms op de resistieve CYD (contactdender), 20 ms op de capacitieve Guition, waar een lichte snelle tik anders verloren ging.
- Elke geweigerde tik staat nu in het ESPHome-log (tag `touch`, niveau INFO) met de reden: `verplaatst 73 px (grens 67)`, `te kort (12 ms, minimaal 20)`, `al verwerkt in dit contact` of `dezelfde knop binnen de dendertijd`, zodat een gemiste aanraking uit het log te lezen is.
- Firmware 0.2.23 voor beide borden; de app biedt de update aan. Alleen firmware verandert; de app-kant is ongewijzigd behalve de doelversie.

## 0.2.27 (firmware 0.2.22 blijft actueel)

- **Nieuw scherm in één venster**: bord, naam, USB-poort, **Installeren**. Het venster maakt het profiel met unieke API- en OTA-sleutels in de ESPHome-map, bouwt de firmware en schrijft die via USB, met het ESPHome-log en de fase (bouwen, schrijven) in hetzelfde venster. Na afloop staat de API-sleutel klaar met een kopieerknop plus de koppelstappen voor Home Assistant; mislukt de build, dan staat het log open en is er **Opnieuw proberen**. De apparaatnaam volgt uit de naam (`Keuken` → `keuken`) en is aan te passen. Zonder aangesloten scherm kun je alleen het profiel bewaren; het staat dan in dezelfde map als ESPHome Device Builder. Elk scherm krijgt zijn eigen profiel; het venster zegt dat nu ook.
- **Waar is mijn scherm?** De koppeling gebeurt in Home Assistant zelf, buiten ESP Screens. Het klaar-scherm van het venster zegt dat nu expliciet, met een knop **Open Apparaten & diensten** die je daarheen brengt. Zolang een ESP Screens-profiel nog niet in Home Assistant staat, toont **Mijn schermen** er een kaart voor ("geïnstalleerd, maar nog niet in Home Assistant", of "nog niet geflasht"), met dezelfde knop, **Kopieer API-sleutel** en de herinnering om bij Configureren "Allow the device to perform Home Assistant actions" aan te zetten (anders ziet het scherm alles, maar bedient het niets). De kaart verdwijnt zodra het scherm in de lijst staat. `/api/inventory` levert daarvoor `pending` (profielen die het bordpakket van dit project gebruiken zonder gekoppeld scherm).
- **Wifi zonder handwerk**: ontbreken `wifi_ssid` of `wifi_password` in de ESPHome `secrets.yaml`, of bestaat het bestand niet, dan vraagt het venster ze en zet ESP Screens alleen de ontbrekende regels in het bestand; commentaar en andere secrets blijven staan (de wizard weigerde eerder bij een bestaand bestand zonder wifi). Een ongeldig `secrets.yaml` wordt nog steeds niet aangeraakt.
- Kopiëren en downloaden van de installatie-YAML is vervallen (`POST /api/install` bestaat niet meer): het profiel staat al in de ESPHome-map. `POST /api/firmware/profiles` accepteert `target` (USB-poort) en start dan direct de build en flash; poort en vrije bouwslot worden gecontroleerd vóór er iets wordt geschreven, en het antwoord bevat `api_key`. Het firmwarejob-object meldt de lopende fase in `stage`.
- Alleen de app verandert; firmware 0.2.22 blijft actueel.

## 0.2.26 (firmware 0.2.22)

- **"HA niet verbonden" om de twee minuten opgelost**: sinds 0.2.20 herhaalt de app de indeling elke 120 s, maar de firmware verwachtte binnen 95 s een bericht (gemaakt voor de oude 25 s). Op een rustig scherm stonden alle tegels daardoor 25 tot 45 s per ronde op "Niet beschikbaar". De firmware gebruikt nu ESPHome's eigen API-verbindingsstatus voor "HA niet verbonden" (direct bij wegvallen en terugkeren van Home Assistant) en bewaakt de gegevensstroom apart met het interval dat de app zelf declareert: het layoutbericht bevat `keepalive` (seconden). Pas na twee gemiste rondes plus marge meldt het scherm "ESP Screens niet actief". Zonder het veld (oudere app) rekent de firmware met 120 s. Firmware 0.2.22 voor beide borden; firmware tot 0.2.21 negeert het veld en houdt zijn 95 s.

## 0.2.25 (firmware 0.2.21)

- **− / + in één beweging**: snel drie keer tikken telt drie stappen (van 20 naar 17); de touch-guard hield een tweede tik op dezelfde knop binnen 600 ms tegen. De − / + knoppen gebruiken nu een eigen korte guard (150 ms, alleen tegen stuiteren) en stappen ook door zolang je ze vasthoudt (drie per seconde). Na 700 ms rust gaat nog steeds één opdracht naar Home Assistant.

## 0.2.24 (firmware 0.2.20)

- **Lichter en zuiniger**: de dag- en uurvoorspelling zitten alleen nog in het geheugen van weertegels (was 832 bytes in elk van de twintig tegels, ruim 16 KB op de CYD zonder PSRAM). De mini-slider onderin een tegel (**Kleine slider**) heeft nu dezelfde zichtbare witte greep als de nieuwe schuiven. De licht-, ventilator- en zonweringkaart op de CYD gebruiken het lichte palet van de Guition (de laatste rest van het donkere thema).
- **Wifi zonder modem-slaap** (`power_save_mode: none`) in de installatie-YAML van de wizard en de bordprofielen: statusupdates, tikacties en OTA wachten niet meer op een wifi-beacon. Bestaande schermen: voeg de regel zelf toe onder `wifi:` in je ESPHome-YAML.
- Doorlichting van de rendering: LVGL 9.5 tekent partieel en slaat ongewijzigde posities en maten al over; de winst zat in de stijlzetters (0.2.23) en in niet meer herrenderen tijdens *bezig*. Een paginawissel tekent bewust twee keer (skelet, dan inhoud). Verder geen structurele last gevonden; zie docs/TEST_RESULTS_0224.md.

## 0.2.23 (firmware 0.2.19)

- **Directe bediening op dubbelbrede tegels**, zoals de entiteitsrijen in Home Assistant: rechts op de kaart staan knoppen of een schuif, links blijven icoon, naam en status. Per domein kies je in het tegelpaneel onder **Directe bediening op de tegel** welke set de tegel toont:
  - klimaat: **Temperatuur − / +** (de gewenste temperatuur in een pill; tikken past direct aan, na een korte pauze gaat één opdracht naar HA) of **Uit, verwarmen, koelen** (maximaal drie modusknoppen uit `hvac_modes`, de actieve gekleurd);
  - schakelaar, input_boolean, lamp en ventilator: **Aan/uit-schakelaar** (toggle die direct omklapt); lamp ook **Helderheidsschuif**, ventilator ook **Snelheidsschuif**;
  - stofzuiger: **Start, stop, naar dock** (start wordt pauze tijdens het schoonmaken; dock en stop grijs als ze niet kunnen);
  - zonwering: **Open, stop, dicht** (pijlen horizontaal voor gordijnen, deuren, poorten en zonneschermen; open/dicht grijs aan het eind van de slag; stop alleen als het apparaat het kan) of **Positieschuif**;
  - mediaspeler: **Volume en dempen** (schuif met witte greep en dempknop) of **Vorige, play/pauze, volgende**;
  - getal: **Waarde − / +** of **Schuif**; keuzelijst: **Vorige / volgende keuze**; kookwekker: **Start/pauze en annuleren**; scène, script en knop: één knop **Activeren**, **Uitvoeren** of **Indrukken**.
- Zonder keuze toont een dubbelbrede tegel van zo'n domein de eerste set; **Geen** houdt de gewone kaart. Enkele tegels veranderen niet. De statusregel volgt HA: `Koelen · 21.5°`, `Open · 80%`, `TV · 17%`.
- De mockup in de editor toont de gekozen bediening in het klein; de Inspector meldt de gekozen set. De add-on stuurt alleen de werkelijk getoonde set mee (`o.controls`), plus `device_class`, `hvac_action` en `is_volume_muted`. Firmware 0.2.18 en ouder negeert het veld; het paneel meldt dat.
- Firmware 0.2.19: het paneel wordt alleen opgebouwd voor tegels die het tonen en per set hergebruikt; de render-selftest controleert dat knoppen binnen de kaart en rechts van de tekst blijven. De drie icoonfonts bevatten 18 extra bedieningsglyphs (CYD +3 KB, Guition +5 KB) en het middenpunt `·` in de tekstfonts.
- **Bezig-status als spinner**: een tegel die op Home Assistant wacht krijgt een licht-witte laag met een klein draaiend cirkeltje in plaats van de blauwe voortgangsbalk en de tekst "Bezig...". De laag vangt tikken op zolang de opdracht loopt.
- **Weerkaart** (bediening openen op een weertegel), in twee kaarten: *nu* met groot icoon, temperatuur, omschrijving en een gedempte regel met gevoelstemperatuur, luchtvochtigheid en wind, daaronder de komende zes uren (tijd, icoon, temperatuur, regenkans in blauw); en *Komende dagen* met per dag icoon, omschrijving, regen met druppel (kans en millimeters) en de hoogste temperatuur vet naast de laagste gedempt. De add-on haalt naast de dagvoorspelling nu ook de uurvoorspelling op (`weather.get_forecasts` type `hourly`, elk half uur ververst) en stuurt `x.hours` plus regen (`p` kans, `r` mm) per dag en uur mee. Zonder uurvoorspelling blijft de kaart bij de dagen.
- **Klimaat**: het vinkje rechtsboven in de klimaatkaart is een **aan/uit-knop** geworden (`climate.turn_on`/`turn_off`, licht op als het apparaat draait); het kruisje sluit nog steeds. De moduskiezer toont naast de HVAC-modi ook de **ventilatorstanden** en **zwenkstanden** van het apparaat (`fan_modes`, `swing_modes`, maximaal vier per rij; Nederlands waar bekend). Bij aantikken van een klimaattegel kun je nu ook **Aan / uit** kiezen (`climate.toggle`).
- **Scènes, scripts en knoppen** tonen niet langer "Uit" maar wanneer ze voor het laatst liepen: `Laatst 14:32`, `Gisteren 14:32` of `Laatst 13 sep`, en `Bezig...` zolang een script draait; `Nog niet gestart` als het nog nooit liep. De add-on stuurt daarvoor `x.last` (unix-tijd uit `last_triggered` of de tijdstempel-status).
- **Moduskiezer van de klimaatkaart** opnieuw ingedeeld: titel *Modus*, de kiezer op het schermgrijs met witte chips met randje (contrast), Nederlandse HVAC-chips drie per rij, de actieve chip in het accentblauw met witte tekst, daaronder de rijen *Ventilator* en *Zwenken* met de standen zoals het apparaat ze meldt (alleen een hoofdletter, geen vertaaltabel: werkt met elk apparaat). Het overbodige vinkje is weg; een chip past de stand toe en sluit, het kruisje sluit. *Nu:* en *Gewenst* vervangen de Engelse labels in de kaart.
- **Lichter tekenen**: de firmware zet lettertypen, uitlijning, padding en lijndikte alleen nog als ze echt veranderen (elke `lv_obj_set_style_*` maakt anders het hele object ongeldig), en herrendert tijdens *bezig* niet meer elke 250 ms de hele pagina. Een tikkende klokkaart of een draaiende spinner tekent zo alleen nog zichzelf. Het donkere thema is uit de runtime-code verwijderd; het lichte palet is het enige palet.
- Getallen boven een miljoen gaan niet mee als weergavewaarde, behalve `supported_features` (een bitveld; mediaspelers zitten boven de 8 miljoen), anders hadden Sonos-tegels geen volume- of playbackknoppen.

## 0.2.22 (firmware 0.2.18 blijft actueel)

- De eventstream stuurt het eerste event direct bij openen in plaats van na 3 s. Gemeten op een Home Assistant Yellow na 0.2.21: `/api/inventory` 50 ms (was 7,2 s), lichte poll 2,6 KB, CPU in rust 0,5% van één core (was 8,7%). Alleen de app verandert.

## 0.2.21 (firmware 0.2.18 blijft actueel)

- **Live updates zonder pollen**: de pagina luistert op `/api/events` (server-sent events). De add-on stuurt schermstatus en updatestatus zodra de synchronisatielus of een opslag iets verandert, en controleert elke 3 s op wijzigingen tijdens een firmware-update. Zolang de stream open is pollt de pagina niet meer; valt de stream weg, dan neemt de poll van 10 s het over. De volledige lijst met entiteiten, achtergronden en iconen wordt nog elke 5 minuten ververst.
- Het log meldt bij het wegvallen van de Home Assistant-verbinding hoe lang die stond, de websocket close-code en de fout, ook wanneer de verbinding zonder foutmelding sluit. Het add-on-log op de Yellow toonde herhaalde "Home Assistant verbonden"-regels zonder waarschuwing ervoor; met deze regels is de oorzaak bij de volgende keer uit het log te halen.
- Alleen de app verandert; firmware 0.2.18 blijft actueel.

## 0.2.20 (firmware 0.2.18 blijft actueel)

- **Minder verbruik in rust**: de synchronisatielus wordt alleen nog wakker voor entiteiten die op een indeling staan of bij een scherm horen (Tegelinstellingen, Schermfirmware, Apparaatnaam, IP-adres, Guition schermtype), niet meer bij elke `state_changed` in Home Assistant.
- De entity-, device- en area-registry (circa 1 MB JSON) wordt niet meer elke 30 s opgehaald, maar bij een `*_registry_updated`-event van Home Assistant (1 s gedebounced) en als vangnet elke 10 minuten.
- De volledige keepalive naar de schermen loopt elke 2 minuten in plaats van elke 25 s. Een scherm dat offline en weer online komt krijgt de volledige indeling direct, zoals voorheen.
- **Lichte poll**: de pagina haalt elke 10 s alleen nog schermen en updatestatus op (`/api/inventory?light=1`, enkele KB) en de volledige lijst met entiteiten, achtergronden en iconen bij openen, bij terugkeer naar het tabblad en elke 5 minuten.
- Alleen de app verandert; firmware 0.2.18 blijft actueel.

## 0.2.19 (firmware 0.2.18 blijft actueel)

- **Sneller overzicht**: `/api/inventory` las bij elke aanroep alle ESPHome-profielen opnieuw in (tot vier keer per verzoek), waardoor de add-on op een Pi seconden per verzoek blokkeerde. Profielen worden nu per bestand gecachet op inode, wijzigingstijd en grootte; alleen een gewijzigd profiel wordt opnieuw gelezen en verwijderde profielen verdwijnen direct. Het parsen zelf gebruikt libyaml wanneer die beschikbaar is (circa tien keer sneller).
- Het overzicht en de updatestatus lezen de profiellijst en de HA-inventaris nog één keer per verzoek; de synchronisatielus rekent de inventaris één keer per ronde uit in plaats van per scherm.
- De pagina pollt niet meer in een verborgen tabblad en ververst direct zodra het tabblad weer zichtbaar is.
- Alleen de app verandert; firmware 0.2.18 blijft actueel.

## 0.2.18 (firmware 0.2.18)

- **Eigen icoon per tegel**: in het tegelpaneel staat onder de naam het veld **Icoon**. Kies uit 150 iconen in twaalf groepen (verlichting, ruimtes, klimaat, weer, media en muziek, beveiliging, apparaten, energie, zonwering, tuin en huisdieren, mensen en onderweg, overig), met zoeken op Nederlandse naam, Engelse MDI-naam of groep. De mockup en de kop van het paneel tonen het gekozen icoon direct.
- **Automatisch** gebruikt het icoon dat je in Home Assistant aan de entiteit gaf (`mdi:…`), als het in de set zit; anders het standaardicoon zoals voorheen. De mockup toont nu overal het icoon dat het scherm werkelijk tekent.
- Firmware 0.2.18 bevat alle 150 iconen in de drie icoonfonts van beide borden (CYD +22 KB, Guition +36 KB). Oudere firmware negeert de keuze en houdt het standaardicoon; het paneel meldt dat een update nodig is.
- De weersvoorspelling blijft het icoon van het actuele weer tonen; klok, voorspelling en zonnebaan hebben geen icoonkeuze.

## 0.2.17 (firmware 0.2.17 blijft actueel)

- Het vinkje **Elke nacht automatisch bijwerken** kreeg de algemene invoerstijl (100% breed met padding), waardoor de tekst buiten de zijkolom onder het editorpaneel viel. Het checkboxje heeft nu een vaste maat. Alleen de app verandert.

## 0.2.16 (firmware 0.2.17)

- **Bijwerken met één knop**: een scherm met oudere firmware krijgt in de lijst een badge *Update 0.2.17* en een knop **Bijwerken**. De app bouwt het eigen profiel, installeert draadloos en toont een spinner tot het scherm terug is met de nieuwe versie en een minuut stabiel blijft. Het resultaat blijft een dag zichtbaar bij het scherm.
- **Elke nacht automatisch bijwerken**: vinkje onder *Firmware-updates*. Tussen 03:00 en 06:00 (tijdzone van HA) werkt de app schermen met oudere firmware één voor één bij, met twee minuten pauze ertussen. Mislukt een scherm, dan stopt de ronde en verschijnt een melding in Home Assistant; de overige schermen blijven op hun oude firmware.
- **Alle schermen bijwerken** doet dezelfde ronde direct, bijvoorbeeld na een app-update.
- Nieuwe firmware is er zodra deze app een nieuwe versie heeft: de app kent de bijbehorende firmwareversie en vergelijkt die met `Schermfirmware` per scherm.
- Firmware 0.2.17 meldt twee diagnostische sensors extra: **Apparaatnaam** (de ESPHome-naam, gelijk aan het YAML-profiel) en **IP-adres**. Daarmee vindt de app zelf het profiel en het OTA-adres. Een scherm met oudere firmware wordt op apparaatnaam aan een profiel gekoppeld en vraagt eenmalig het IP-adres.

## 0.2.15 (firmware 0.2.16)

- **Achtergrond: Geen** als extra keuze in het tegelpalet: de kaart en de rand vallen weg en de tegelinhoud staat direct op de schermachtergrond, in dezelfde maat en op dezelfde plek als mét kaart. Werkt voor elke tegel; de mockup toont zo'n tegel met een stippellijn. Vereist schermfirmware 0.2.16; de app bewaart de indeling en meldt het als het scherm ouder is.
- **Analoge klok**: streepjes als index met de cijfers 12, 3, 6 en 9 (de CYD houdt alleen streepjes). Op een enkele tegel staat naast de wijzerplaat een kalenderblok — weekdag, grote dag, maand (CYD: "13 sep"). Dubbelbreed blijft de digitale tijd met datum naast de wijzerplaat.

## 0.2.14 (firmware 0.2.15 blijft actueel)

- Tegelinstellingen openen in een paneel bóven de schermmockup (op mobiel een sheet onderaan): naam, weergave, breedte, tikgedrag, slider, geschiedenis en kleur als knoppen, direct zichtbaar in de mockup erachter. Geen springende pagina meer.
- Verwijderen kan direct in de mockup met het kruisje op een tegel; de melding onderaan heeft **Ongedaan maken**.
- De tegellijst onder de mockup is vervallen; ordenen doe je door te slepen.

## 0.2.13 (firmware 0.2.15)

- Editor: sleep tegels in de schermmockup om te ordenen en sleep entiteiten rechtstreeks uit de lijst naar een plek in de mockup — met muis én touch (even vasthouden). De opslaan-balk blijft altijd in beeld.
- Nieuwe kop met duidelijke acties (**Nieuw scherm**, **Firmware & USB**, **Uitleg**) en een korte uitleg in drie stappen; de firmwaredialoog legt profiel, doel en knoppen uit.
- **Zonnebaan**: `sun.sun` toont dubbelbreed een horizon met de zon op zijn huidige positie tussen opkomst en ondergang (’s nachts onder de horizon), met beide tijden. Nieuwe zon-, weer- en kloktegels starten meteen dubbelbreed in hun mooiste weergave.
- Grafiek: vloeiende curve door dezelfde 24 punten met een zachte vulling eronder, zoals de HA-trendkaart.
- Scherm: de paginering is één geïntegreerde onderbalk — links tikken is vorige, rechts is volgende, het paginanummer staat in het midden.
- Scherm: bij een paginawissel verschijnen direct de kaartkaders van de nieuwe pagina (skeleton) en vult de inhoud een fractie later; geen oude waarden meer in nieuwe kaders.
- CYD: hetzelfde lichte kleurenschema als de Guition — lichtgrijze achtergrond, witte kaarten met een fijne rand, donkere tekst en lichtblauwe accenten, ook in de bedieningskaarten.

## 0.2.12 (firmware 0.2.14)

- Nieuwe kaarten in de kiezer: **Klok** (digitaal of analoog, ingebouwd), **weersvoorspelling** met vijf dagen op een dubbelbrede weerkaart, **grafiek** van de sensorgeschiedenis in de tegel, **zon** (`sun.sun`, opkomst en ondergang in je eigen tijdzone), **kookwekker** (`timer.*`, live aftellen; tikken start of pauzeert, lang indrukken annuleert) en **aanwezigheid** (`person.*`).
- **Dubbelbreed** als breedte-optie voor elke tegel. Een dubbelbrede tegel begint links en telt voor twee vakjes; het schermvoorbeeld toont ook de lege plek ervoor.
- De weerkaart toont het icoon van de actuele weersituatie. Voorspellingen komen van `weather.get_forecasts` en worden elk half uur ververst.
- Nieuwe domeinen en de klok vereisen schermfirmware 0.2.14; de app weigert opslaan voor oudere firmware en bewaart je bestaande indeling. Breedte en weergave-opties negeert oudere firmware gewoon.

## Firmware 0.2.13 (app 0.2.11 blijft bruikbaar)

- Grote waarde: klein domeinicoon naast de titel, titel en waarde verticaal gecentreerd, groter cijferfont (38 px Guition, 22 px CYD). Een te lange waarde krijgt puntjes; de eenheid staat altijd rechts naast het getal.
- Guition: de backlight dimt naar standby via de LEDC-hardwarefader in 1,5 s en wordt in 80 ms wakker. Schermherteken onderbreekt de overgang niet meer, dus geen schokkerig uitfaden.
- Installeer de nieuwe schermfirmware via ESP Screens; geen appupdate of gewijzigde configuratie nodig.

## Firmware 0.2.12 (app 0.2.11 blijft bruikbaar)

- Switches herkennen nu een aan/uit-terugmelding met ongewijzigde attributen. Daarmee verdwijnt de onterechte wachttijd van zes seconden. Na HA-bevestiging geldt voor switches slechts 150 ms minimale feedback.
- Uitgeschakelde switches hebben een grijs icoon en een grijze icoonachtergrond. Een zelfgekozen pastel tegelachtergrond blijft behouden.
- Mini-sliders behouden een compact domeinicoon naast titel en waarde. CYD centreert iconen en tekst verticaal; de renderdiagnose controleert centrering en vrije ruimte boven de slider.
- Lang indrukken op een switch of input_boolean opent een grote native LVGL-schakelaar met de echte HA-status, ook op CYD. Openen verstuurt geen opdracht.
- Installeer de nieuwe schermfirmware via ESP Screens; geen appupdate of gewijzigde configuratie nodig.

## 0.2.11

- Compact raster voor de pastelkleuren in de tegeleditor; voorkomt dat algemene formulierstijlen het palet in een lange kolom zetten. Alleen de app verandert; schermfirmware 0.2.10 blijft actueel.

## 0.2.10

- Kies per tegel een pastel achtergrond: rood, oranje, geel, groen, mint, blauw, paars, roze of grijs. Standaard herstelt de normale kleuren. De keuze is zichtbaar in het schermvoorbeeld en werkt met donkere tekst op Guition én CYD.
- Tegelkleuren blijven behouden bij appupdates en bij opslaan vanuit een oudere beheerpagina. Installeer firmware 0.2.10 op het scherm om de kleuren weer te geven.
- README en Easy Setup beschrijven de huidige één-app-installatie, twintig tegels, inspector, rotatie en updates via de ingebouwde ESPHome-CLI.

## 0.2.9

- Guition: kies 0°, 90°, 180° of 270° onder Scherminstellingen. Na opslaan draait de interface direct mee, inclusief touch. De hoek blijft bewaard na herstart; een nieuwe flash per hoek is niet nodig.
- Installeer eerst Guition-firmware 0.2.9 voor deze optie. De CYD behoudt zijn vaste oriëntatie en kalibratie.

## 0.2.8

- Firmware: vaste tekstbreedtes voor nette afkapping met puntjes. Ondertitels gebruiken de beschikbare ruimte, ook bij korte titels.
- Firmware: op de CYD staat de mini-slider onder beide tekstregels, met minder verticale padding. Zonder icoon krijgen de tekstregels de volledige kaartbreedte.
- De renderdiagnose controleert nu ook de daadwerkelijke tekst- en slidercoördinaten. Installeer de schermfirmware om deze verbeteringen te gebruiken; bestaande tegels, instellingen en sleutels blijven behouden.

## 0.2.7

- Tot twintig tegels op vier vaste pagina’s; installeer eerst firmware 0.2.7. Zes tegelvakken worden hergebruikt om geheugen te sparen.
- Optionele LVGL-swipes tussen pagina’s via scherminstellingen. Sliders en detailmenu’s wisselen niet van pagina; na een swipe wordt de aanraking geconsumeerd.

## 0.2.6

- Nieuw scherm hergebruikt bestaande ESPHome-wifi-secrets automatisch. De wizard vraagt alleen wifi als secrets.yaml nog niet bestaat. Ontbrekende wifi-sleutels in een bestaand bestand worden gemeld zonder het bestand te overschrijven.

## 0.2.5

- Firmware: een vacuumkaart openen toont de echte status, geen opdrachtmelding. Het statuslabel in de robotkaart blijft ook na een actie actueel.

## 0.2.4

- Visuele tegelkiezer met domeiniconen, zachte kleuren en een klikbaar schermvoorbeeld van zes tegels per pagina. Selecteer een tegel om de instellingen te openen; sleep tegels in het voorbeeld om te ordenen. Geen firmware-update nodig.

## 0.2.3

- Firmware: iets donkerdere Guition-achtergrond, zachte domeinkleuren op iconen en de echte HA-lampkleur in iconen/mini-sliders. Aangepaste Lovelace-thema- en kaartkleuren worden niet automatisch geïmporteerd.

## 0.2.2

- Firmware: terug naar pagina 1 bij standby sluit nu ook runtime-detailkaarten, waaronder vacuum, historie en media. Installeer hiervoor de nieuwe schermfirmware via Firmware & USB.

## 0.2.1

- Algemene instellingen en Inspector direct bovenaan bereikbaar.
- Tegel selecteren: klikactie, grote waarde, kleine slider (ja/nee) en historieperiode.
- Inspectie per tegel met actuele HA-status en eigenschappen.
- Firmware: schuifgebaren correct verwerken, brede mini-slider zonder handvat, concrete historie-as.
- Nieuwe vacuumkaart met robotweergave, actieve zuigkracht en druk-/opdrachtfeedback.

# 0.2.0

- ESPHome CLI in de app: bestaande profielen controleren, bouwen en via USB/OTA installeren.
- Nieuwe profielen met unieke sleutels; bestaande YAML, secrets en appdata blijven behouden.
- Tegelopties: klikgedrag, grote waarde, mini-schuif en sensorgeschiedenis.
- Media-, weather-, number- en select-kaarten en vernieuwde vacuumkaart op beide borden.
- Actiefeedback, vaste tekstregels en zwarte sliderknoppen.
- Inspector en helderheid/standby als instellingen bij het HA-apparaat.
- Native Guition ST7701S-configuratie en lichte kaartstijl. Duuracceptatie van het fysieke beeld blijft apart van firmwaretests.

# 0.1.2

- Per scherm standbyduur, normale/standby/nachthelderheid en nachturen instellen.
- Klok aan/uit, 12/24 uur en terug naar pagina 1 na standby.
- Instellingen direct doorsturen; firmware 0.1.2 bewaart ze in preferences.
- Bestaande tegels en sleutels blijven behouden. Eenmalig firmware bijwerken.
- De Guition-displaydriver is ongewijzigd; dit is geen oplossing voor paneelstrepen.

# 0.1.1

- Duidelijke foutmelding bij een ongeldige naam, te veel tegels of dubbele entiteiten.
- Updatepad met behoud van bestaande schermindelingen.

# 0.1.0

- Eerste ESP Screen Manager met Home Assistant Ingress.
- Zoek op entiteit, apparaat of ruimte; tien geordende tegels per scherm.
- Tegelwijzigingen en actuele waarden zonder firmwareflash.
- Installatie-YAML met unieke sleutels voor CYD en Guition.
- Permanente indelingen, automatisch herstel na HA-/schermherstart.
