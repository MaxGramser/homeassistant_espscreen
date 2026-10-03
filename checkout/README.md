# Building a screen from a checkout

Almost everyone installs a screen from ESP Screens (docs/EASY_SETUP.md), or builds it in ESPHome Device Builder from
the remote package `packages/<board>.yaml`. Neither uses this folder.

This folder is for building the firmware yourself from a clone of this repository, with the ESPHome command line. It
holds one file per board, named after the board's key in `boards.yaml`:

| File | Board |
|---|---|
| `cyd.yaml` | CYD, ESP32-2432S028 |
| `cyd9342.yaml` | CYD, ESP32-2432S028 with an ILI9342 display controller (experimental) |
| `guition.yaml` | Guition ESP32-S3-4848S040, 4 inch |
| `waveshare43.yaml` | Waveshare ESP32-S3-Touch-LCD-4.3 |
| `jc8012p4a1.yaml` | Guition JC8012P4A1, 10.1 inch |
| `jc8012p4a1v3.yaml` | Guition JC8012P4A1 V3, 10.1 inch (experimental) |
| `tab5.yaml` | M5Stack Tab5 ST7121 variant, 5 inch (experimental) |
| `waveshare7.yaml` | Waveshare ESP32-S3-Touch-LCD-7 (experimental) |
| `waveshare4b.yaml` | Waveshare ESP32-S3-Touch-LCD-4B (experimental) |

Each file builds the same two packages a screen from ESP Screens builds (`packages/core.yaml` and the board's file
under `packages/boards/`), with the components and fonts of this checkout instead of GitHub's.

## Secrets

ESPHome reads `secrets.yaml` from the folder of the file it builds, so it goes in this folder:
`checkout/secrets.yaml`. Git ignores it. It needs these keys:

```yaml
wifi_ssid: "your network"
wifi_password: "your Wi-Fi password"
api_encryption_key: "32 random bytes, base64"  # esphome's own: openssl rand -base64 32
ota_password: "a password for updates over Wi-Fi"
ap_password: "a password for the fallback hotspot"
```

## Building

From the root of the repository:

```sh
esphome run checkout/guition.yaml
```

ESPHome keeps its build files in `checkout/.esphome/`, which Git ignores too. For a screen of your own, copy the file
under another name and set `DEVICE_NAME` and `DEVICE_FRIENDLY_NAME` in its `substitutions:`; two files with the same
`DEVICE_NAME` share one build folder, so don't build them at the same time.
