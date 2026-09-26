# ESP Screens with Home Assistant Container (Docker)

Home Assistant Container has no App store, so ESP Screen Manager can't be installed as an
app there. This guide runs the same app as its own container next to Home Assistant, with
the ESPHome CLI included. On Home Assistant OS, follow the
[normal installation](../README.md#installing-from-home-assistant) instead.

This route is new. If something doesn't work on your setup, please
[open an issue](https://github.com/MaxGramser/homeassistant_espscreen/issues).

## What you need

- Home Assistant Container on a Linux host (aarch64 or amd64) with host networking,
  as in the Home Assistant installation docs. Home Assistant on Docker's bridge network, as
  is usual with Docker Desktop on Windows or macOS, works too: see
  [Home Assistant on a bridge network](#home-assistant-on-a-bridge-network).
- Docker with Compose on the same host, and `git`: Compose builds the image straight from GitHub. Synology
  Container Manager has no `git`; download the release's source ZIP instead and point `context:` in
  `compose.yaml` at its `screen_manager` folder (GitHub #32).
- The ESPHome integration in Home Assistant, to pair the screens. ESPHome Device Builder
  is optional: the ESPHome CLI is already in this image.

## Install

1. Create a folder, for example `esp-screens`, and put
   [`docker/compose.yaml`](../docker/compose.yaml) in it.
2. In Home Assistant, open your profile → **Security** → **Long-lived access tokens** and
   create a token, signed in as an administrator. Save only the token in a file named
   `ha_token` next to `compose.yaml`, readable for you only (`chmod 600 ha_token`).
3. Check two lines in `compose.yaml`:
   - `HA_API`: `http://127.0.0.1:8123/api` works when Home Assistant runs on the same host
     on port 8123. Keep `/api` at the end.
   - The ESPHome folder: `./esphome` works as is. Already using ESPHome Device Builder?
     Use its folder instead, so both see the same device profiles.
4. Start it:

   ```sh
   docker compose up -d --build
   ```

   The first build downloads the official ESPHome image. `docker compose logs -f` shows
   `Home Assistant connected` once the token works.

## Open ESP Screens

The page has no login of its own, so it only listens on `127.0.0.1:8099` of the Docker
host. Don't make port 8099 reachable from your network without a login in front of it.

**In the Home Assistant sidebar (recommended).** Install
[hass_ingress](https://github.com/lovelylain/hass_ingress) from HACS, add this to
`configuration.yaml`, and restart Home Assistant:

```yaml
ingress:
  esp_screens:
    title: ESP Screens
    icon: mdi:monitor-dashboard
    require_admin: true
    url: http://127.0.0.1:8099
```

Home Assistant then handles the login, like the app panel on Home Assistant OS.

**Through an SSH tunnel.** From your computer:

```sh
ssh -L 8099:127.0.0.1:8099 you@docker-host
```

Then open `http://localhost:8099`. The **Open Devices & services** button only works in
the sidebar panel; here, open Home Assistant yourself.

### Home Assistant on a bridge network

Without `network_mode: host`, Home Assistant runs on Docker's bridge network with its ports
published under `ports:`. This is common with Docker Desktop on Windows and macOS, where
"host" is Docker's own Linux VM and not your computer. Inside the Home Assistant container,
`127.0.0.1` is then Home Assistant itself, so the sidebar panel shows **502: Bad Gateway**.

Let ESP Screens share the network of the Home Assistant container instead. `127.0.0.1` then
means the same in both, and the hass_ingress configuration above stays as it is. Put both in
the same `compose.yaml` and change it like this, with the service name of Home Assistant after
`service:`:

```yaml
services:
  homeassistant:
    # ... your existing settings ...
    ports:
      # ... your existing ports ...
      - 8098:8098                    # camera images for the screens, published by this container

  esp-screens:
    # ... build, restart, init, secrets, volumes and healthcheck as in docker/compose.yaml ...
    network_mode: "service:homeassistant"   # replaces network_mode: host
    depends_on:
      - homeassistant
    environment:
      SCREEN_DEV: "1"
      HA_API: http://127.0.0.1:8123/api     # Home Assistant itself, in the shared network
      HA_TOKEN_FILE: /run/secrets/ha_token
      ESPHOME_CONFIG: /config
      SCREEN_DATA: /data
      SCREEN_CAMERA_URL: http://192.168.1.20:8098   # your Docker host's LAN address
```

Then run `docker compose up -d` again and check that Home Assistant reaches the app:

```sh
docker exec homeassistant curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8099/
```

`200` means the panel works; `000` means the two containers don't share a network yet.

- **Home Assistant on https only:** `https://127.0.0.1:8123` fails the certificate check.
  Point `HA_API` at an http address that reaches Home Assistant instead, such as a reverse
  proxy in front of it. On Docker Desktop, `host.docker.internal` is the address of your
  computer, so `http://host.docker.internal:<port>/api` reaches a port it publishes.
- **Recreating Home Assistant** (an update, for example) takes the shared network away:
  run `docker compose up -d` again so ESP Screens is recreated too.
- **Camera images:** the firewall of the Docker host has to let the screens in on port 8098.
- **USB:** Docker Desktop passes no USB ports to containers. Use **Download · flash from your
  own computer** in **New screen** (see below).

This setup is confirmed on Docker Desktop for Windows with WSL 2 for opening the panel.
Camera images and updates over Wi-Fi haven't been tested on it yet.

## Using it

From here it works like the app: **New screen** installs a screen, you pair it
under **Settings → Devices & services** in Home Assistant, and then choose the tiles. See the
[installation guide](EASY_SETUP.md).

- **USB (Linux only):** connect the screen, uncomment `devices:` in `compose.yaml` with its
  port (`/dev/ttyUSB0` or `/dev/ttyACM0`), and run `docker compose up -d` again. Installs
  over Wi-Fi (OTA) and the nightly updates need nothing extra.
- **Without USB passthrough (app 0.2.68+):** in **New screen**, choose **Download · flash from
  your own computer**. The container builds the firmware, and you put it on the screen with
  [ESPHome Web](https://web.esphome.io) in Chrome or Edge on the computer the screen is plugged into.
  **This computer · install from this browser** does both in one step, but only on a page served
  over https (or from `localhost` on the computer that runs the container).
- **Backups:** Home Assistant backups don't include this container. Keep a copy of
  `data/screens.json` and `data/updates.json` (layouts and update settings) and of the
  ESPHome folder. `data/build`, `data/esphome`, `data/idf` and `data/platformio` are caches.
- **Claude:** **Install for Claude Code** is meant for the Claude Code app on Home Assistant
  OS. Use **Download for claude.ai** instead.
- **Camera images (every board except the CYD, the Waveshare 3.5-inch and the Hosyond 4-inch):** the screens load camera pictures, and from app 0.2.77 the
  album covers of the media card, from port **8098** of this host, on all its addresses, so keep that port open to the screens. The app uses Home
  Assistant's own LAN address; when the screens reach this host under another one, set
  `SCREEN_CAMERA_URL` (see below). The links are random and short-lived. [docs/CAMERA.md](CAMERA.md)

## Updating

```sh
docker compose build --pull
docker compose up -d
```

This builds the latest version from `main`, the same one the App store offers. To stay on
one version, replace `#main` in the `context:` line of `compose.yaml` with a release tag, such as `#screens-v0.3.14`.
After an update, ESP Screens shows per screen whether newer firmware is available, as usual.

## Settings in compose.yaml

| Setting | What it does |
| --- | --- |
| `SCREEN_DEV: "1"` | Runs the app outside the Supervisor: it reads the token from `HA_TOKEN_FILE` and serves its page on 127.0.0.1 only (camera images still on port 8098 for the screens) |
| `HA_API` | Home Assistant's address, ending in `/api` |
| `HA_TOKEN_FILE` | The token file inside the container (the `ha_token` secret) |
| `ESPHOME_CONFIG` | The ESPHome folder inside the container |
| `SCREEN_DATA` | Layouts, update settings, and build caches |
| `SCREEN_CAMERA_URL` | Optional: where screens load camera images, such as `http://192.168.1.20:8098`; by default Home Assistant's own LAN address |
| `SCREEN_CAMERA_PORT` | Optional: the camera image port instead of 8098 |
