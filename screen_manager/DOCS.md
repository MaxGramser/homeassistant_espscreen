# Installation and everyday use

See [the full installation guide](https://github.com/MaxGramser/homeassistant_espscreen/blob/main/docs/EASY_SETUP.md).

Open **New screen** in the sidebar to install a screen: connect it via USB to the
Home Assistant machine, choose the board, name and USB port, then click **Install**.
The profile with unique keys goes into the ESPHome folder of the HA configuration,
any missing Wi-Fi goes into `secrets.yaml` (existing secrets are left untouched), and the
build and flash run in the same window; it then shows the API key
for pairing. Is the Home Assistant machine out of reach of the screen, such as a server or a
virtual machine? Plug it into your own computer and choose **This computer** under **Install via**:
ESP Screens builds the firmware and the page puts it on the screen, in Chrome or Edge with Home
Assistant opened over https. Or choose **Download** and put it on the screen with
[ESPHome Web](https://web.esphome.io). Pairing itself happens in Home Assistant under **Settings → Devices & services** (a button in the window and on the *not yet in Home Assistant* card under Screens in the sidebar). Each screen has its own profile. **Firmware & USB** in the sidebar is
for existing profiles: check, build or reinstall via USB, the IP address (OTA), this computer
or Download. Existing ESPHome profiles in the HA config folder are
found automatically.

**Alerts** in the sidebar is the cheatsheet, with a form to try an alert
(an alert on one screen, or on every screen with the `esp_screens_show_alert` event). Its **One screen** part
lists what to fill in after `screen:` for each screen, for an alert with a camera picture on one screen.
**Settings** in the sidebar has the nightly firmware updates (the Update badge of a screen lists what's new, a
running update shows its progress) and **Claude**: install the ESP Screens skill for Claude Code in Home Assistant, or
download it for claude.ai, and ask Claude for the alert automation.

Tap the bar at the top of any page in the mockup to set the **Top bar** of a screen: the name on the left, up
to six items on the right (time, analog clock, date, or an entity with an icon, such as
temperature, a door, the alarm, or "last changed"). Drag to reorder, tap
to configure; firmware 0.2.32 or newer renders them.

After pairing via the HA ESPHome integration, choose the tiles in ESP Screens.
Tap a tile and its settings open in a drawer on the right, with the mockup still in view: click behavior, larger values, mini-sliders, a wider tile or one over the whole page, backgrounds.
The mockup shows what Home Assistant reports right now: values, On or Off, positions, the song that plays. **Identify** in the ··· menu blinks a screen so you know which one it is; the same menu copies the layout of another screen, or exports and imports one as JSON. ⌘K searches screens, entities and actions.
**Screen settings**, the tab next to Layout, has brightness, Dark mode and standby, the night hours, and the
clock, back to page 1, swiping, the page buttons and the rotation. **Read current data** in the ··· menu of a screen helps with
missing attributes or an offline screen. A new card needs new firmware on the screen: press **Update** on it.
The ··· menu of a screen also has **Override YAML** for a persistent, hardware-specific
`<screen>.local.yaml` file. It is loaded after the shared package and does not
replace the managed name, credentials, Wi-Fi, OTA or package connection.

The screen carries the same settings itself (firmware 0.2.44 or newer): hold the top bar for
about a second and a half, or put the built-in **Settings** card on a page. What is changed
there appears here within a second, and the other way around.

In Home Assistant every screen also has a **Wake** and a **Sleep** button (firmware 0.2.45 or
newer). Press them from an automation with `button.press`: Wake lights the screen up and restarts the
standby time, Sleep puts the screen in standby right away, also with Auto standby off. Wake is not a
touch, so an open card or a later page still goes back to page 1 on time (firmware 0.2.56 or newer).
