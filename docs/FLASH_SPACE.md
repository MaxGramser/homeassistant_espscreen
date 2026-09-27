# Firmware size and free flash space

When choosing a screen, compare the space left in one firmware update slot, not
just the flash capacity on the product page. More space in that slot leaves room
for future firmware releases and your own ESPHome additions.

## Recommended flash capacity for a new screen

**Choose at least 8 MiB of configured flash; prefer 16 MiB for room to grow.**
This is buying guidance based on the measured headroom below, not a new minimum
requirement for running Tessera. Choose an exact supported board and check its
hardware support status as well as its flash capacity.

| Configured flash | Buying guidance |
| --- | --- |
| 16 MiB | Preferred for a new installation, especially for custom ESPHome components or future firmware growth. The measured profiles use less than a third of one OTA slot. |
| 8 MiB | Recommended minimum. The measured Waveshare 7-inch profile uses about half of one OTA slot. |
| 4 MiB | Supported, but constrained. Avoid choosing a low-cost 4 MiB model for a new installation if you expect to add features or want generous update headroom. |

The cheapest 4 MiB boards have only a 1.75 MiB OTA slot. A stock build fitting
today does not guarantee that added components or later toolchains will fit.
Check the compiled image after each addition. More PSRAM does not increase this
flash limit, and a larger flash chip helps only when the board's profile uses it.

Existing 4 MiB screens do not need replacing just because of this recommendation.
Upstream [release 0.4.5](https://github.com/MaxGramser/homeassistant_espscreen/blob/4ae55a1/screen_manager/CHANGELOG.md)
reports a CYD image of 1,631,488 bytes (88.9% used, 198.8 KiB free) after removing
the fallback hotspot and captive portal on the 4 MiB profiles. That improves
their margin, but also illustrates the feature tradeoffs of a small flash chip:
changing Wi-Fi settings now requires the documented USB recovery route.

## What the numbers mean

- **Configured flash** is the capacity the default board profile builds for.
- **OTA slot** is the partition for one firmware image. Over-the-air updates use
  two slots, keeping the running image while the next image is downloaded.
  Other partitions also occupy flash, so neither slot holds the entire chip.
- **Used** is the size of `firmware.ota.bin` divided by the OTA slot size.
- **Free** is the space left in that slot for firmware growth. It is not free RAM,
  PSRAM, storage for files, or a promise of how many more tiles will fit.

MiB means 1,048,576 bytes; KiB means 1,024 bytes. The `4MB`, `8MB` and `16MB`
ESPHome flash settings correspond to 4, 8 and 16 MiB here.

## Measured release snapshot

These measurements are for stock **app release 0.4.4**, commit
[`366686a`](https://github.com/MaxGramser/homeassistant_espscreen/commit/366686a384e6fb4dae6321614115e42d6e3f1a8d),
built with **ESPHome 2026.9.0** on **2026-09-27**. Shared firmware is **0.4.0**;
the ILI9342 CYD uses its board revision **0.4.1**. They are a dated comparison,
not live measurements of the latest release or of an installed screen.
In particular, these measurements predate the 4 MiB hotspot removal in 0.4.5;
the later CYD result above is reported by upstream, not a new all-board measurement.

All 13 default checkout profiles were compiled with English text, their default
orientation and features, and the check tool's placeholder credentials. They
include Wi-Fi, the fallback access point, captive portal, API encryption and OTA,
as in a normal installation. No custom components or user overrides were added.

| Board profile | Configured flash (MiB) | OTA slot (MiB) | Firmware (bytes) | Used | Free (KiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| [ESP32-2432S028](../checkout/cyd.yaml) (`cyd`) | 4 | 1.75 | 1,719,888 | 93.7% | 112.4 |
| [ESP32-2432S028 ILI9342](../checkout/cyd9342.yaml) (`cyd9342`) | 4 | 1.75 | 1,719,888 | 93.7% | 112.4 |
| [ESP32-S3-4848S040](../checkout/guition.yaml) (`guition`) | 16 | 7.75 | 2,141,472 | 26.4% | 5,844.7 |
| [ESP32-S3-Touch-LCD-4.3](../checkout/waveshare43.yaml) (`waveshare43`) | 16 | 7.75 | 2,403,280 | 29.6% | 5,589.0 |
| [JC8012P4A1](../checkout/jc8012p4a1.yaml) (`jc8012p4a1`) | 16 | 7.75 | 2,112,336 | 26.0% | 5,873.2 |
| [JC8012P4A1 V3](../checkout/jc8012p4a1v3.yaml) (`jc8012p4a1v3`) | 16 | 7.75 | 2,115,200 | 26.0% | 5,870.4 |
| [ESP32-S3-Touch-LCD-7](../checkout/waveshare7.yaml) (`waveshare7`) | 8 | 3.75 | 1,923,600 | 48.9% | 1,961.5 |
| [ESP32-S3-Touch-LCD-4B](../checkout/waveshare4b.yaml) (`waveshare4b`) | 16 | 7.75 | 2,143,424 | 26.4% | 5,842.8 |
| [ESP32-S3-Touch-LCD-3.5](../checkout/waveshare35.yaml) (`waveshare35`) | 16 | 7.75 | 1,970,096 | 24.2% | 6,012.1 |
| [JC1060P470](../checkout/jc1060p470.yaml) (`jc1060p470`) | 16 | 7.75 | 2,201,936 | 27.1% | 5,785.7 |
| [JC1060P470 V2](../checkout/jc1060p470v2.yaml) (`jc1060p470v2`) | 16 | 7.75 | 2,201,968 | 27.1% | 5,785.6 |
| [ESP32-32E E32R40T](../checkout/hosyond40.yaml) (`hosyond40`) | 4 | 1.75 | 1,726,336 | 94.1% | 106.1 |
| [JC3248W535](../checkout/jc3248w535.yaml) (`jc3248w535`) | 16 | 7.75 | 2,085,408 | 25.7% | 5,899.5 |

The values above describe the exact profiles, not every similarly named product.
In particular, `waveshare4b` is the **ESP32-S3-Touch-LCD-4B, 480 × 480**. It is
not the ESP32-P4 720 × 720 panel.

The Waveshare 7-inch profile builds for 8 MiB. A 16 MiB hardware variant still
uses that profile's 8 MiB partition layout unless its configuration is changed;
the extra physical flash does not automatically enlarge the OTA slots. See
[Waveshare 7-inch](WAVESHARE7.md).

The [CYD release budget](RELEASING.md#for-every-release) reserves room for compiler
updates and user additions: up to 90% is normal, 90-93% is tight, 93-97% permits
only fixes, and above 97% must not ship. Free bytes up to 100% are therefore not
all available for new features. The larger slots leave substantially more room,
but flash capacity alone does not establish hardware support or performance;
check the [supported-screen status](../README.md#which-screen) as well.

Firmware releases, ESPHome/toolchain versions, language, hardware choices and
Override YAML can change the image size. Reordering or adding tiles in the
editor does not rebuild the firmware: layouts are delivered while the screen
runs, and their limits are separate from flash headroom.

## Checking or refreshing the comparison

From a checkout of the release being measured, use the ESPHome version pinned in
`screen_manager/Dockerfile` and the dependencies in
[the release checks](RELEASING.md#for-every-release). Run:

```sh
tools/check.sh --firmware
```

This compiles every board with placeholder secrets; it does not flash a device.
Each successful `Firmware: <board>` line reports the image size, slot size,
percentage used and free bytes. The CYD budget is checked separately. To measure
just one profile, use its key from `boards.yaml`, for example:

```sh
tools/check.sh --firmware --board guition
```

The check reads `firmware.ota.bin` and the `app0` / `ota_0` partition in that
build's `partitions.csv`. Builds are under `.esphome/check/build/check-<board>` by
default, or the configured `ESPHOME_DATA_DIR`. Do not compare the padded factory
image to an OTA slot, and do not substitute the total flash capacity for the
slot size.

When refreshing this table, compile all profiles for the same commit and
ESPHome version, then replace the table and its release, commit, version and
date together. Record a failed or unmeasured profile explicitly rather than
carrying its old result into a new release snapshot. Check `boards.yaml` for new
profiles. Keep the per-board firmware revision when it differs from the shared
firmware. The existing check output supplies the measurements; there is no
second list of partition sizes to maintain.
