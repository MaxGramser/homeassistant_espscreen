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
Reinstall from dev, a plugin that joins it) leaves the round, so it is never left out for another screen's failure. Between two updates of one round there is a pause (`Updater.pause_seconds`).

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

## Adding a kind of build

1. Give its steps as a coroutine that takes the build and returns `'success'`, `'failed'` or `'skipped'`. Every ESPHome
   action in it goes through `BuildQueue.step`.
2. Add it with `BuildQueue.add(by, file, run, ...)`, or `attended(request)` for one ESPHome action a person follows.
   Name its kind in `KINDS`, `Manager.builds` and the editor's `Build` type.
3. What must happen once it ended, whatever the outcome, goes in `build.ends`.
4. Test it in `tests/test_build_queue.py`.
