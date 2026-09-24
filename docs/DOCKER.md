# ESP Screens with Home Assistant Container (Docker)

Home Assistant Container has no App store, so ESP Screen Manager can't be installed as an
app there. This guide runs the same app as its own container next to Home Assistant, with
the ESPHome CLI included. On Home Assistant OS, follow the
[normal installation](../README.md#installing-from-home-assistant) instead.

This route is new. If something doesn't work on your setup, please
[open an issue](https://github.com/MaxGramser/homeassistant_espscreen/issues).

## What you need

- Home Assistant Container on a Linux host (aarch64 or amd64) with host networking,
  as in the Home Assistant installation docs.
- Docker with Compose, best on the same host. Home Assistant on another machine works too, see
  [Home Assistant on another machine](#home-assistant-on-another-machine).
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
   `Home Assistant connected` once the token works. Until then the screens show
   *Waiting for ESP Screens*.

## Home Assistant on https with its own certificate

With `HA_API` on `https://`, the app checks Home Assistant's certificate like a browser does.
A self-signed certificate isn't on that list, so the log repeats
`Home Assistant temporarily unavailable (ClientConnectorCertificateError ...)` and nothing
connects. Other clients that work, such as the Companion app, were told to trust it once;
the app needs that too (app 0.2.134+):

1. Copy the certificate Home Assistant uses (the file after `ssl_certificate:` in its
   `configuration.yaml`, not the key) next to `compose.yaml` as `ha_cert.pem`.
2. In `compose.yaml`, uncomment `HA_CA_FILE: /run/secrets/ha_cert`, `- ha_cert` under the
   service's `secrets:`, and the `ha_cert:` entry at the bottom.
3. `docker compose up -d`.

The certificate has to name the address in `HA_API`: a certificate made for
`homeassistant.lan` doesn't cover `https://192.168.1.10:8123`. The log then says
`IP address mismatch` or `Hostname mismatch`; use the name in the certificate in `HA_API`.
If the certificate names neither, `HA_VERIFY_SSL: "0"` connects without checking it. That
is only reasonable on your own network: the token then goes to whoever answers at that address.

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

Home Assistant then handles the login, like the app panel on Home Assistant OS. The
`127.0.0.1` in `url` is Home Assistant's own machine, so this works as is only when Home
Assistant runs on the Docker host; otherwise see below.

**On the Docker host itself.** Open `http://localhost:8099` in a browser there. No tunnel needed.

**Through an SSH tunnel.** From another computer, when the Docker host runs an SSH server
(`Connection refused` means it doesn't: install `openssh-server` there, or use one of the
other ways):

```sh
ssh -L 8099:127.0.0.1:8099 you@docker-host
```

`you` is your login on the Docker host, not your Home Assistant user. Then open
`http://localhost:8099`. The **Open Devices & services** button only works in the sidebar
panel; here, open Home Assistant yourself.

### Home Assistant on another machine

For example Home Assistant in a virtual machine and Docker on the machine around it. The app
only listens on `127.0.0.1` of the Docker host, which Home Assistant can't reach from there.

1. In `compose.yaml`, set `HA_API` to Home Assistant's address as the Docker host reaches it,
   such as `https://192.168.1.10:8123/api`, and uncomment `SCREEN_INGRESS_FROM` with Home
   Assistant's address as the Docker host sees it, such as `192.168.1.10` (app 0.2.134+). The
   page then listens on the network too, but answers only that address and the Docker host itself.
2. In hass_ingress, use the Docker host's address in `url`, such as `http://192.168.1.20:8099`.
3. `docker compose up -d` and restart Home Assistant.

Anyone who can send from Home Assistant's address can open the page, so only do this on a
network you trust.

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
- **Backups:** Home Assistant backups don't include this container. Keep a copy of
  `data/screens.json` and `data/updates.json` (layouts and update settings) and of the
  ESPHome folder. `data/build`, `data/esphome`, `data/idf` and `data/platformio` are caches.
- **Claude:** **Install for Claude Code** is meant for the Claude Code app on Home Assistant
  OS. Use **Download for claude.ai** instead.
- **Camera images (Guition, app 0.2.66+):** the screens load camera pictures, and from app 0.2.77 the
  album covers of the media card, from port **8098** of this host, on all its addresses, so keep that port open to the screens. The app uses Home
  Assistant's own LAN address; when the screens reach this host under another one, set
  `SCREEN_CAMERA_URL` (see below). The links are random and short-lived. [docs/CAMERA.md](CAMERA.md)

## Updating

```sh
docker compose build --pull
docker compose up -d
```

This builds the latest version from `main`, the same one the App store offers. To stay on
one version, replace `main` in `compose.yaml` with a release tag, such as `screens-v0.2.49`.
After an update, ESP Screens shows per screen whether newer firmware is available, as usual.

## Settings in compose.yaml

| Setting | What it does |
| --- | --- |
| `SCREEN_DEV: "1"` | Runs the app outside the Supervisor: it reads the token from `HA_TOKEN_FILE` and serves its page on 127.0.0.1 only, unless `SCREEN_INGRESS_FROM` is set (camera images still on port 8098 for the screens) |
| `HA_API` | Home Assistant's address, ending in `/api` |
| `HA_TOKEN_FILE` | The token file inside the container (the `ha_token` secret) |
| `HA_CA_FILE` | Optional: the certificate (or its CA) to trust for Home Assistant on https, such as a self-signed one |
| `HA_VERIFY_SSL` | Optional: `"0"` doesn't check Home Assistant's certificate; the last resort when it doesn't name the address in `HA_API` |
| `SCREEN_INGRESS_FROM` | Optional: Home Assistant's address when it runs on another machine; the page then also listens on the network, for that address only |
| `ESPHOME_CONFIG` | The ESPHome folder inside the container |
| `SCREEN_DATA` | Layouts, update settings, and build caches |
| `SCREEN_CAMERA_URL` | Optional: where screens load camera images, such as `http://192.168.1.20:8098`; by default Home Assistant's own LAN address |
| `SCREEN_CAMERA_PORT` | Optional: the camera image port instead of 8098 |
