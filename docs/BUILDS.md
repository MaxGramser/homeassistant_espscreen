# Builds: one line for everything that builds

Tessera Screen Manager builds one firmware at a time. Everything that builds a screen's firmware waits its turn in one
line: a firmware update (one screen, Update all, the nightly round), a plugin build, New screen, and Firmware & USB with
its YAML check. Nothing is refused because something else builds. It waits, and the editor says what it waits for.

The line is `screen_manager/app/build_queue.py` (`BuildQueue`). The Manager holds one (`manager.build_queue`), and it is
the only thing that starts an ESPHome job (`Firmware.start`).

## What a build is

A build is what was asked for one profile, with the steps of its kind:

| Kind (`by`) | Who asks | Its steps |
|---|---|---|
| `update` | Update, Update all, the nightly round, Reinstall from dev | `Updater.update_one`: install (over the bridge on a board with 4 MB when it must), wait for the screen to report the firmware, settle |
| `plugins` | Plugins page, a screen's Plugins tab | install the screen's firmware with its plugins file, then settle the plugins (`Plugins._built`) |
| `icons` | A screen's Icons page, Put on every screen | install the screen's firmware with its plugins file, then settle its icons (docs/ICONS.md) |
| `install` | New screen, Firmware & USB | one ESPHome action: build, install or download |
| `check` | Override YAML, Firmware & USB | `esphome config` |

A build keeps the slot until all of its steps are done. ESPHome is idle between two steps of an update (while the screen
restarts, or between the bridge and the firmware), and no other build starts in that gap.

## The order

- As asked, one after the other.
- What a person follows on the page goes first: New screen, Firmware & USB and the YAML check (`attended`) go before
  the updates and plugin builds that wait. They never stop the build that runs.
- A build that runs is never stopped for another.

## One build per screen

What is asked for a profile that already waits joins that build (`Build.join`):

- A plugin asked while the screen's plugin build waits builds once, with everything asked for it.
- A plugin build and an update of the same screen are one build. An update builds the screen's plugins file too, so the
  build becomes the update and settles the plugins once the screen's firmware went on (`installed`).
- An update asked again while it waits or runs stays the one update it is.
- What is asked while the screen's own build runs waits for a build after it. That build may have read its YAML
  already.

What a person follows (`attended`) never joins and is never joined. The same request twice (a second click) waits once.

A plugin build whose plugin parts changed starts from an empty build folder (`Build.fresh`, `Firmware.clean_build`),
and so does the build it joins. ESPHome never takes a file it wrote into the build folder away again (it wipes the
folder only when a component it had is gone), so a part that needs what an earlier build left a placeholder for would
find the placeholder (docs/CAMERA.md, Screen camera's video). The compile cache outside the folder stays.

## Rounds

Update all and the nightly round are a `Round`: one build that fails leaves the builds of its round that still wait out
(`skipped`), so a bad build never reaches the next screen. Builds asked apart, such as another screen's Update or a
plugin build, stay in the line. A build of the round that someone also asks for by itself (its screen's Update or
Reinstall from dev, a plugin that joins it) leaves the round, so it is never left out for another screen's failure.

## Following a build

Every build has an id. The line goes to the editor with every live answer of the app, the inventory it pushes over its
event stream (`light_payload`): `line` holds what runs, what waits in order (with its turn, `place`, and the profile it
waits for, `after`) and the last builds that ended (`ENDED`, newest first), with how each ended (`success`, `failed`,
`skipped`, `interrupted`), its `reason` and the memory it had. `builds` (`Manager.builds`) is, from the same look at the
line, the build on its way for each screen (`id`, `by`, `state`, `place`, `phase`, `plugins`, `stage`); a YAML check
builds nothing and has no record there. Every change of the line asks for a live answer (`BuildQueue._changed`), and so
does a new ESPHome step or memory plan of the build that runs (`Firmware._changed`).

Logs are too large for every live answer. ESPHome's log of the build that runs is in the firmware answer
(`GET api/firmware`), asked every few seconds only while someone follows a running build. The log of one build that
ended, also after the next one started, is `GET api/firmware/builds/{id}/log`.

In the editor, the builds store (`web/src/stores/builds.ts`) is the one place that reads them: `line`, `lineBuild`,
`buildOf` and the outcome of a build that ended all come from the inventory, the logs through `buildLogOf` and
`loadBuildLog`. `useLineBuild` (in `composables/useFirmwareJob.ts`) follows one build by its id: New screen, Firmware &
USB and the YAML check use it. A view keeps only which build it follows. Never follow a build by "the firmware job that
runs now": the next build starts at once, and its job is another one.

## Kept logs

The line keeps its last builds in memory, and those are gone when the app restarts. A build the app restarted during is
the one whose log matters most, so every build that runs an ESPHome step also writes its log to disk
(`screen_manager/app/build_logs.py`): `/data/build_logs/<key>.log`, line by line as ESPHome writes it, with
`<key>.json` beside it (kind, profile, screen, plugins, when it started and how it ended). A log whose build never ended
reads as `interrupted`. The newest 40 stay; the clean-up of build files leaves them alone. The lines are redacted before
they get there, as on the page.

A plugin build the app restarted during (an update of the app, a restart of Home Assistant) starts once more by itself:
its plugins file already holds the plugins, so `Plugins.settle` queues the same build again as soon as the screen has an
address, at the start (`resume_after_start`) and whenever the editor asks. The record is marked `resumed`; a build that is
cut off a second time, or a screen still without an address ten minutes after the start (`RESUME_WAIT`), counts as failed
(`interrupted`), with the log it wrote until then.

A build names its log by that key (`log` in the line), and so does a plugin that did not build (`log` on a failed plugin,
`failed_update.log` on an update the screen went back from). `GET api/firmware/logs` lists the kept logs, newest first,
and `GET api/firmware/logs/{key}` sends one as a file. In the editor:

- A screen's Plugins tab says first what did not build on it (`PluginFailures.vue`, `plugins.failuresOn`): the plugin,
  the version, why, and the log to download, with the way to try again. It stays until the plugin builds or is taken
  off. When the build stopped on the plugin (not a restart of the app), it also offers an issue at the plugin's GitHub
  repository, filled in with the plugin, version, board, firmware and the line it stopped on (`issueUrl` in
  `web/src/model/plugins.ts`), naming no screen or home; the person attaches the log they downloaded.
- A plugin's details and the screen's build note (`BuildLog.vue`) offer the same download.
- The screen's Plugins tab lists its last builds with their logs (`BuildHistory.vue`).
- Firmware & USB lists every kept log, to download.

## Building ahead

The slot is ESPHome's, not the build's. A build holds it while ESPHome compiles or uploads, and gives it up while it
only waits (`BuildQueue.handoff`): while its screen restarts and is checked, and in a round while it waits for its turn
to install. The next build compiles meanwhile. Its next ESPHome step takes the slot back before anything that waits in
the line (`BuildQueue.step` asks `reacquire` for the build of its task, `build_queue.CURRENT`), after the job that runs
now. A build that gave the slot up still runs for its screen (`aside`, and `on_the_way`); the page sees two or more
builds running, one of them compiling.

In a round of more than one screen an update is made in two steps (`Updater.build_and_install`): `build` (compile, on the
build server when it is on), then `upload` (Firmware's action that sends what the last build made, also the build
server's images). Between the two it waits, beside the line (phase `ready`), until every screen before it in the round
has ended: its install goes only once those passed their check (they report the new firmware and stay up through
`settle_seconds`). A screen before it that failed ends the round, and the build made ahead is not installed
(`skipped`, `addon.updates.round_stopped`). A screen updated alone builds and installs in one `install`.

A failure that says nothing about the firmware does not end the round: a download the build needs that did not come
(`network`) or a screen that was away for its upload (`offline`, `Updater.passing`, by `build_failures.PASSING`). That
screen goes once more, at the end of the line in the same round (its build ends `retry`, `Build.attempt` 2), with what
it brought for the screen's plugins and whoever waits for its end; a second failure is a failure. A screen that was away
goes once more only with other screens of its round between. While a build waits beside the line no other build of its
screen starts (`BuildQueue._pick`): it would install over it or empty its build folder. A build keeps every step's lines
(`Build.logs`), so one made ahead keeps its compile log as well as its upload's, and a step refused before it ran (a file
that went, a wrong address) leaves no step and no log behind. A plugin build gives the slot
up as well while its screen restarts and confirms the plugins (`Plugins._verify`). There is no pause between two updates
of a round any more: the check is the wait.

With a build server, the Mac compiles the next screen while this app uploads to one screen and waits for another, so it
is busy as long as a round has screens left to build.

## The steps of a build

Every place that shows a build shows its steps (`BuildSteps.vue`, `web/src/model/build-steps.ts`): waits its turn,
builds (on the build server or here), sends it to the screen, the screen confirms. The add-on says the ESPHome step a
build is at (`stage`: compile, upload) and the build's own phase (`verify`), and for a build that ended the step it got
to (`stage`) and whether the screen confirmed (`verified`).

A plugin build waits after its upload until the screen has restarted and says, in its hello, that it runs the plugins
at the versions built (`Plugins._verify`, up to four minutes). True is a confirmed build; false a screen that came back
without them (a plugin that crashed at boot), which the editor answers with the version before (below); null a screen
that could not tell. A build that went well stays on the page for ten minutes with its steps done.

## Why a build failed

A build that fails is given a kind (`failure_kind` in `screen_manager/app/build_failures.py`, the one place that reads a
build's log for its cause), and for a plugin build each kind has its own words and its own way out in the screen's
Plugins tab (`PluginFailures.vue`):

| Kind | What happened | The way out |
|---|---|---|
| `plugin` | a compiler error in the plugin's own component (`blame`) | a filled-in issue at the maker's GitHub, with the log |
| `memory` | this Home Assistant ran short of memory (build_memory.py) | a build server |
| `offline` | built, but the screen was not there for the upload | installed once more by itself within a minute of the screen being back (`Plugins.SETTLE_EVERY`), once |
| `network` | a download the build needs did not come | tried once more by itself at once; then a key to try again |
| `interrupted` | the app restarted during the build | built once more by itself after the start (above); this kind is a second cut |
| `build` | anything else | the log, and the issue at the maker |

A failure is said in Home Assistant too: one notification per screen (`tessera_plugins_<screen>`), taken away by the
next build that goes well (`Plugins._tell_home_assistant`, through `ha_notice.py`, the one way this app leaves a
notification in Home Assistant). The page's own message after a failed plugin build opens the
screen's Plugins tab.

## A version that does not run well

A plugin build that went well keeps what the screen ran before (`before` on the record, its files kept as the release's
snapshot). The plugin's details offer "Back to <version>" (`POST api/screens/{inbox}/plugins/{plugin}/back`,
`Plugins.go_back`), first of all when the screen came back without the plugin. It is a plugin build like any other: a
failure keeps what runs.

## Updates of a screen

A screen's updates are in one card at the top of its Plugins tab (`ScreenUpdates.vue`): its firmware and each plugin,
from the version it runs to the new one, and one key for all of it. `POST api/screens/{inbox}/update-everything`
(`Plugins.update_everything`) writes the plugins file with the new versions and starts the firmware update, which builds
that file; the plugins settle with that build. Without a firmware update it is a plugin build.

The sidebar names a screen's plugin updates beside its name (a key that opens its Plugins tab) and marks a plugin that
did not build. The Updates card of the settings lists the screens with plugin updates, and lets the nightly round start
at an hour of the owner's choosing (`hour` in `updates.json`, three hours from it; `Updater.round_day` keeps a window
past midnight one round; the summary sends `hour` and `window`, so the editor shows the add-on's own numbers). Home Assistant hears of new updates too: one notification (`tessera_updates`) that names each
screen and what waits, made again when that changes and taken away once nothing waits (`update_notice.py`, every
fifteen minutes, from `Updater.firmware_waiting` and `Plugins.updates_on`).

## Before a build

`build_room` in the live answer says whether this Home Assistant has the memory a build needs: free memory against the
heaviest file (build_memory.py), and whether the build server takes the builds. Tight without a build server, the
editor says so where builds are started (`BuildRoom.vue`), with the two ways round it: a build server, or ESPHome
Device Builder on a computer. Building here stays the default; nothing is refused.

The editor also counts the plugin host for the first plugin on a 4 MB screen (`PLUGIN_HOST_KB` in
`web/src/model/plugins.ts`, #440), and New screen refuses a name with `"` or `\`, which would break the C++ strings it
goes into (#453).

## After an update of the app

A page keeps the editor it loaded, also after the app was updated or the dev app rebuilt, and an old editor against a
new app may not understand what the app sends. Every live answer names the editor the app serves (`editor`: the
`index-<hash>.js` its `static/index.html` names, `server.editor_bundle`). A page that runs another one reloads itself as
soon as nothing is in progress: no unsaved change of a screen, no plugin work the page holds (`plugins.pending`: the
tray, a change on its way), not in New screen or Firmware & USB (a flash from the browser would break off), not writing a
troubleshooting report. Until then it says so once, with a key to reload now (`web/src/stores/editor-version.ts`). It
reloads at most once for one editor the app serves (kept for the tab), so it never loops. Under SCREEN_DEV the live answer
reads the bundle with the page, so a fresh `npm run build` reloads the page once.

## On a build server

A Raspberry Pi takes a long time over a screen's firmware and can run short of memory. When a faster computer on the
same network runs an ESPHome build server, the app sends its builds there instead. The build server is ESPHome's own
remote build: the app speaks the sending side of it, as an ESPHome Device Builder does when it sends builds.

### Setting one up

1. Start a build server on the faster computer, one of these:
   - **ESPHome Desktop.** It builds for other devices from the start.
   - **ESPHome Device Builder** (in Docker, or the ESPHome app of another Home Assistant): Settings → Build server →
     Enable remote build.
   - **Without a screen:** `esphome-device-builder --remote-build-only <folder>`. It prints its fingerprint and a
     one-time pairing key.
   The build server listens on TCP port 6055. A firewall has to let that port through (Windows blocks it by default).
2. In Tessera: **Settings → Build server → Connect a build server**. Type the computer's IP address or host name (an
   app in Home Assistant cannot look for it on the network) and press **Look it up**.
3. Compare the seven emoji with the fingerprint the build server shows. Pair only when they match.
   - A headless build server asks for its one-time key, and lets Tessera in at once.
   - ESPHome Desktop and Device Builder: open **Pairing requests** there, check that Tessera's emoji match, and accept
     it. The card waits for that and then shows the server as Ready.
4. **Build screens on this server** is on from then on. Every build goes there: updates, plugin builds, New screen and
   Firmware & USB.

The build server and Tessera must reach each other on the local network. Over a VPN or across networks it may work,
but ESPHome does not support remote builds there, and neither does Tessera.

### What happens in a build

- The app packs the screen's YAML with `esphome bundle` (its includes, the secrets it uses, local components) and
  sends it. Plugins kept in a folder beside the ESPHome folder go into the bundle too, which `esphome bundle` alone
  leaves out. Packages and plugins from GitHub are fetched by the build server itself.
- The build server compiles with the ESPHome version this app builds with: it installs that version once, beside its
  own, so a screen is the same firmware wherever it was built. The first build of a new version takes a few minutes
  longer there.
- The images come back into the app's build folder (`/data/build/<screen>/server`), and everything after the build
  runs here as before: the update over Wi-Fi, USB, the download for the browser, the bridge and the wide partition
  table on boards with 4 MB of flash (`esphome upload --file`).
- An update builds, then installs, the same YAML: the install takes the build just made instead of asking the server
  again. A YAML that takes its packages from a branch (`ref: dev` or `ref: main`) is the same text after every push,
  as the server fetches the branch itself, so its build is taken again only within two minutes, the update it was
  made for; a release tag or a commit builds the same whenever (`REUSE_MOVING_SECONDS`, `follows_branch`).
- The page says where a build runs and at which step (packing, sending, waiting, building, fetching), and the Build
  server card says how the last build went.

### When it builds here instead

A build runs here, as without a build server, and its log and the page say why, when:

- the build server is switched off, not paired, or not reachable;
- it forgot Tessera (pair it again) or answers with another fingerprint than the one you checked;
- the link drops during the build, the server does not take the build, cannot install the ESPHome version, or the
  firmware does not come back.

When the log says the server could not install ESPHome, the build server's own log says why. On an Intel Mac, a
package of ESPHome 2026.9 has no ready-made build and needs Rust to be compiled there
(github.com/esphome/esphome/issues/20286): install Rust on that computer, pin the package that needs it to its last
release with a ready-made build (`PIP_CONSTRAINT` pointing at a file with `cbor2==5.9.0`, in the build server's
environment), or use another computer as the build server.

A build that fails on the server itself (a compile error) fails: the same YAML fails here too, after a much longer
wait. Its log is the server's.

### For developers

- `screen_manager/app/build_server.py` is the pairing, the link and the build; `Firmware.compile_on_server` and
  `Firmware.served_file` put it into a job; the build line carries `where`, `server`, `remote` and `fallback` to the
  page (`BuildQueue.view`, `Manager.builds`). The editor's card is `web/src/components/BuildServerCard.vue`, the steps'
  words `serverStep` in `web/src/model/screen-status.ts`.
- The protocol is Device Builder's peer link (github.com/esphome/device-builder, docs/ARCHITECTURE.md "Remote build"
  and docs/API.md): a WebSocket on port 6055, a Noise XX handshake (`Noise_XX_25519_ChaChaPoly_SHA256`), then
  encrypted JSON frames. It has no version number; a frame the app does not know is ignored, and anything it cannot
  read ends the session, which means a build here. Asked upstream: github.com/orgs/esphome/discussions/3910.
- `tests/test_build_server.py` runs a small server in the test that speaks the server's side. To try the real one:
  `uvx --from 'esphome-device-builder[esphome]' esphome-device-builder --remote-build-only <folder>`.

## Build files

Every build leaves files in the app's data folder (`/data`, or `data/` beside `compose.yaml` on Docker) so the next
build of the same screen is quick. `Firmware.build_env` says where each kind goes, and `screen_manager/app/build_files.py`
measures them and cleans them up. Measured in the app's own image with ESPHome 2026.9 (one Guition 4848S040 and one
Guition P4 10.1):

| Kind | Where | Size | Without it, the next build |
|---|---|---|---|
| A screen's build folder | `build/<profile>` | about 1 GB per screen (1.0 GB for the Guition 4848S040, 0.9 GB for the P4 10.1) | compiles that screen's firmware again; the compile cache answers most of it, so it takes a few minutes longer (57 seconds instead of 8 for an unchanged screen, and 223 for its first build, with four compilers on a Mac; several times that on a Raspberry Pi) |
| The compile cache | `idf/ccache` | up to 1 GB (`CCACHE_SIZE`) | fetches its board's cache from GitHub again (build_cache.py), or compiles from scratch where there is none |
| ESP-IDF and its compilers | `idf` (the rest), `platformio` | 2 GB with an ESP32-S3 screen, 3.9 GB once an ESP32-P4 screen was built too (its RISC-V compilers) | downloads them again first (about 1 GB), then compiles from scratch |
| What ESPHome fetched | `esphome` but `esphome/storage` | 0.6 GB | fetches this repository's packages and components from GitHub again |

So a home with eight screens holds 10 GB or more, most of it in the build folders. Everything else in `/data` (the
layouts in `screens.json`, keys, plugin data, icons, the update and build server settings) is never a build file.

### Cleaning up

Settings → Build files shows the sizes and has two buttons:

- **Clean up build folders** removes `build/*` for every screen, as ESPHome Device Builder's Clean Build Files does
  for one device. The toolchain and the compile cache stay, so the next build of a screen takes minutes more, not the
  first build's quarter of an hour.
- **Also remove the compile cache and ESP-IDF** removes the rest of the table too, as Device Builder's Clean All does.
  The next build downloads ESP-IDF again and compiles from the start.

Both ask first and say what they free and cost. A clean-up never runs while a build runs or waits (`BuildQueue.busy`
refuses it), and the build line holds what is asked meanwhile until it is done (`BuildQueue.hold` and `release`), so no
build starts on a folder that is half gone.

### When it is offered

From 2 GB of build folders (`OFFER_BYTES`, two or three screens) the editor offers the clean-up: the message that a
build is ready carries a Free button once per page, and the card says so with a Not now. Not now waits until the
build folders grew by another 2 GB (`OFFER_AGAIN_BYTES`). The sizes are measured off the loop when the line has nothing
more to build, when the app starts and after a clean-up, never during a build.

### Clean up after building

Off unless the owner turns it on (`build_files.json`, `auto`). When it is on, the build folders are removed each time the
line has nothing more to build. That keeps `/data` small, at the cost the switch says beside it: every next build of a
screen compiles everything again and takes a few minutes longer. It keeps ESP-IDF and the compile cache.

### Backups

`backup_exclude` in `screen_manager/config.yaml` leaves `build/`, `esphome/`, `idf/` and `platformio/` out of Home
Assistant's backups, so a backup holds the layouts and settings only. A restored backup has none of the build files:
the first build after it downloads ESP-IDF and compiles each screen as its first build did. On Docker, Home Assistant
backs up nothing of the container; docs/DOCKER.md says which files to keep.

`tests/test_build_files.py` proves the sizes, what each clean-up removes and keeps, the refusal while building, the
build that waits for a clean-up, the offer and the automatic clean-up; `web/tests/build-files.spec.ts` the card and
the offer.

## Adding a kind of build

1. Give its steps as a coroutine that takes the build and returns `'success'`, `'failed'` or `'skipped'`. Every ESPHome
   action in it goes through `BuildQueue.step`.
2. Add it with `BuildQueue.add(by, file, run, ...)`, or `attended(request)` for one ESPHome action a person follows.
   Name its kind in `KINDS`, `Manager.builds` and the editor's `Build` type.
3. What must happen once it ended, whatever the outcome, goes in `build.ends`.
4. Test it in `tests/test_build_queue.py`.
