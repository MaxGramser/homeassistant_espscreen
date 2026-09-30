# Firmware preview architecture

The tile editor remains Vue. Its optional device preview is a single canvas backed
by LVGL and the actual `components/smart_display/runtime_tiles.h` renderer.

```text
Shared firmware YAML ── ESPHome codegen ── styles, widgets, fonts
Shared runtime_tiles.h + ESPHome font.cpp + LVGL ── Emscripten ── WASM
Manager's normal layout/header/state packets ── WASM receive()
Browser pointer events ── firmware touch guard + LVGL pointer input
Firmware ESPHome action requests ── browser transport ── Manager ── Home Assistant
Home Assistant action responses + state packets ── firmware confirmation handling
WASM display flush ── RGBA framebuffer ── canvas
```

The host owns transport, time and input. Firmware owns tile placement, sizing,
colours, glyph selection, detail rendering and page transitions. No browser tile
renderer is a fallback. There are no HTML page dots over the framebuffer.

Taps control the Home Assistant instance connected to Screen Manager, including
real devices if that instance has them. The host copies the firmware's existing
ESPHome service requests into a queue, relays them through a CSRF-protected endpoint,
and supplies Home Assistant's success/refusal to the firmware's normal callbacks.
Live entity changes and a post-command refresh use the manager's device state packets.
There is no browser switch simulation or duplicate thermostat action logic. Commands
must target an existing entity and an action Home Assistant offers for that entity.

`renderer_host_api.h` declares the browser adapter's C interface. A source fingerprint
covers the shared renderer's local dependencies, generated UI/font assets, UI-related
YAML and the host adapter. Changing board pins alone does not change it. The manifest
check rejects changed source, and the runtime test compares the binary's embedded
fingerprint with the manifest, so updating only a header cannot pass.

When updating firmware:

1. Run the regular firmware checks (`tools/check.sh --firmware`).
2. Run `web/wasm/build.sh` against that same checkout. It uses the add-on's pinned
   ESPHome version and regenerates every font/style profile from the shared YAML.
3. Run the WASM runtime tests at the supported profiles and the normal repository checks.
4. Build the editor and include its generated static assets in the change.

Changes to renderer internals normally compile directly. Changes to hardware APIs or
ESPHome's code-generation shape may require an adapter/generator update; these should
fail the build, rather than loading a stale imitation. Resolution and grid are runtime
inputs. Font/style density profiles are generated at build time.

See [the build instructions and current limitations](../web/wasm/README.md).
