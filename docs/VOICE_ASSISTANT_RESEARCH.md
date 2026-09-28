# Voice assistant research: Waveshare ESP32-P4 wall panel

Research date: 2026-09-28. Status: proposal, no voice firmware implemented or
hardware tested. Baseline: repository `main` at `05ee2be`, with ESPHome 2026.9.0.

A separate [browser proof of concept](VOICE_PREVIEW_POC.md) now implements the
direct audio transport and screen-first name resolution on the test branch.
It also offers an optional Claude adapter using Home Assistant STT and TTS,
with the same context and validated tools. OpenAI retains direct Realtime audio.
Its automated tests do not establish voice quality or physical board support.

## Recommendation

Prioritize accurate understanding, natural phrasing and conversational context.
Evaluate a direct speech-to-speech model through OpenAI Realtime first, with
Home Assistant executing validated device actions. The model receives audio
and conversation context without depending on a separate local transcript as
its sole input. This is a candidate to measure, not a guarantee of better word
recognition than a well-configured Whisper pipeline.
[Official OpenAI documentation](https://developers.openai.com/api/docs/guides/realtime).

Start the evaluation in the browser with tap-to-talk and the shared firmware
UI. A server-side bridge would manage credentials, session events and HA action
tools. Physical microphone capture, playback handover and wake words follow
after the conversation test. Reuse ESPHome hardware drivers and LVGL; direct
Realtime transport is additional integration work, not something the existing
ESPHome `voice_assistant` component enables through a model setting.

The standard Assist route below remains an alternative for a native or local
deployment. It should not become a mandatory command-matching gate for the
initial speech-to-speech evaluation. Internet access and paid API usage are
required for the proposed cloud route.

## General questions after activation

A wake word must eventually open the same general assistant session as the
browser's **Start voice** button. It activates listening; it does not limit the
conversation to home-control commands or a fixed set of phrases.

Use one conversation with three capabilities: validated Home Assistant actions
for device commands, direct model answers for general knowledge, and a live
lookup for current information such as weather in any city or recent news.
Visible tile names remain the first choice when resolving a device command.
General questions must not require corresponding Home Assistant entities.

The browser experiment now has a server-side current-information tool callable
by Realtime. It uses the OpenAI Responses API with `web_search` and returns an
answer with sources for Realtime to speak. Keep this tool and its result format
independent of microphone capture, so the physical panel's later audio adapter
can reuse it. Direct audio remains the conversation input; this does not add a
separate speech-to-text pipeline. See [Realtime function calling](https://developers.openai.com/api/docs/guides/realtime-conversations#function-calling)
and [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search).

Physical wake-word activation is not implemented yet. Validate current-information
questions and lookup failures in the browser first; a
failed lookup must not become an invented current-weather or news answer.

## Name resolution: screen labels first

Use the names visible on the originating panel as the primary vocabulary for
voice commands. Fall back to Home Assistant entity names and aliases when no
screen label matches. This selects the command's target; it does not define a
wake word or restrict speech to fixed phrases.

1. Match against the displayed labels of tiles on the current page, using their
   linked entity IDs. For example, "Turn on Reading light" should target the
   entity behind the tile labelled "Reading light", even if HA names it
   "Corner lamp".
2. If no visible label matches, resolve using HA names, aliases and areas within
   the entities exposed to the assistant. "Turn on Corner lamp" must still work.
3. Respect explicit room or device qualifiers. If multiple targets still match,
   ask which one; do not silently select a different entity through fallback.

Keep display labels separate from HA registry names. Renaming a tile changes
the panel's voice vocabulary without renaming the entity in HA. An empty custom
label should resolve to the same fallback name the panel actually displays.
Do not treat unsaved editor changes as names already visible on the device.

The manager already stores tile labels, entity IDs and page positions. The
browser voice bridge consumes the rendered layout, tracks the active firmware
page and refreshes context when displayed names change. A layout snapshot alone does
not identify the currently visible page. Screen labels never grant permission
to control an entity that is not exposed to the assistant.

This policy is implemented in the browser experiment. The physical panel still
needs its own audio and context adapter.

## Quality acceptance

- Test natural Dutch speech, device and room names, varied phrasing, corrections
  and follow-ups using prior context.
- Test clear speech, background television, silence and partially heard words.
  Configure the agent to ask a short clarification when audio or the target is
  ambiguous. Do not let it invent a missing device name or temperature.
- Give the model the visible tile labels and their entity bindings first, with
  exposed HA names, aliases and areas as fallback. Test renamed tiles, label
  collisions and page changes. Validate the selected entity and action on the
  server, and report the actual HA result. Prefer
  explicit on/off actions over toggle so retries cannot reverse the result.
- Record correct-action rate, wrong-device actions, unnecessary clarification,
  end-of-speech to response latency and recovery from failed requests.
- Repeat the tests on the wall-mounted hardware. Browser microphone processing
  and a quiet laptop test do not establish the panel's acoustic performance.

These are proposed acceptance checks. None have been run. A stronger model
cannot recover audio lost through clipping, dropped samples or severe echo.
[Realtime tools](https://developers.openai.com/api/docs/guides/realtime-mcp),
[handling unclear audio](https://developers.openai.com/api/docs/guides/voice-prompting#handle-unclear-audio).

## Hardware and project support

The target is **ESP32-P4-86-Panel-ETH-2RO**, SKU 31570, the relay-equipped variant
of the ESP32-P4-WIFI6-Touch-LCD-4B family. It has a 720 x 720 touchscreen,
32 MB flash and 32 MB PSRAM. Waveshare documents two onboard microphones,
an ES7210 audio ADC, ES8311 codec and NS4150B speaker amplifier. Its speaker
connector accepts an 8 ohm, 2 W speaker. Confirm the speaker supplied with the
chosen package separately. Ethernet is available on this variant.
[Waveshare hardware documentation](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-4B).

This repository does not yet have that physical board profile or voice
configuration. Its `waveshare4b` entry is the **ESP32-S3-Touch-LCD-4B**, a different
board. A virtual profile does not establish hardware support.

ESPHome already provides `mipi_dsi` model `WAVESHARE-P4-86-PANEL`. Adding the
board should reuse this driver and the existing firmware renderer.
[ESPHome display driver](https://esphome.io/components/display/mipi_dsi/).

## Standard Assist alternative: available capabilities

These are proposed capabilities, not features already enabled in ESP Screens.

| Capability | Approach and limit |
| --- | --- |
| Tap to speak | A firmware button starts an Assist session; silence ends capture. |
| Hands-free activation | Test `micro_wake_word` on the P4 with a supported model, such as `okay_nabu`. A build and physical test are still required. |
| Spoken replies | Play the Assist response through the panel's speaker. |
| Screen feedback | Show listening, processing, response and error states; display the recognized sentence and reply. |
| Home control | Assist operates exposed lights, switches, climate entities, scenes and scripts. Supported phrases depend on the selected language and pipeline. |
| Timers and lists | Assist supports timers and adding list items. The speech engine must support the requested vocabulary. |
| Announcements | Add the appropriate speaker/media-player and Assist announcement support. |

ESPHome exposes the voice lifecycle and recognized/response text through
`voice_assistant` callbacks. Its native Assist transport should carry audio;
the ESP Screens layout protocol should not become an audio protocol.
[ESPHome Voice Assistant](https://esphome.io/components/voice_assistant/),
[microWakeWord](https://esphome.io/components/micro_wake_word/).

Home Assistant defines the commands and entity exposure. Climate control should
target the thermostat entity, preserving its control logic. Arbitrary calendar
queries and scheduling edits are not implied by adding a microphone; they need
an appropriate Assist intent, script or conversation agent.
[Built-in intents](https://developers.home-assistant.io/docs/intent_builtin/),
[example Assist commands](https://www.home-assistant.io/voice_control/builtin_sentences/).

## Where processing runs

The proposed speech-to-speech evaluation uses this architecture:

```text
Browser or panel audio <-> audio/session bridge <-> OpenAI Realtime
                                  |
                          validated HA action tools
                                  |
                            Home Assistant
```

The browser can use WebRTC for audio, with the server managing session setup and
private tool execution. The physical panel's bridge transport remains to be
designed. Text and status events feed the same firmware-rendered UI on both.

The standard Assist alternative separates the stages:

```text
Panel microphone -> ESPHome native API -> Home Assistant Assist
                                            |
                                     speech-to-text
                                            |
                                     intent / action
                                            |
                                      text-to-speech
                                            |
Panel speaker and LVGL feedback <------------+
```

For a local home-control alternative, **Speech-to-Phrase plus Piper** is an option.
Speech-to-Phrase recognizes a constrained set of commands and supports Dutch.
For free-form list entries or broader speech, evaluate **Whisper plus Piper**;
the more general recognition costs more host resources. A local pipeline needs
no cloud subscription, but still depends on the Home Assistant host and network.
Local wake-word detection does not make full commands independent of HA.
[Local Assist options](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/),
[Speech-to-Phrase languages](https://github.com/OHF-Voice/speech-to-phrase#supported-languages).

For Home Assistant Container, run speech services in separate containers and
connect them through the native Wyoming integration. HA OS can install the
corresponding apps. These are speech services, not a custom ESP Screens
integration. Actual command latency must be measured on the chosen host.
[Wyoming integration](https://www.home-assistant.io/integrations/wyoming/),
[Whisper container](https://github.com/OHF-Voice/wyoming-faster-whisper#docker-image),
[Piper container](https://github.com/OHF-Voice/wyoming-piper#docker-image).

## Audio wiring and limitations

The following assignments were read from page 1 of the linked main-board
schematic, including the audio nets, and cross-checked against a same-board
community configuration. Confirm the shipped PCB revision before using them.

| Signal | GPIO |
| --- | --- |
| Shared I2C SDA / SCL | 7 / 8 |
| I2S master clock | 13 |
| I2S bit clock | 12 |
| I2S word-select clock | 10 |
| ES7210 data to processor | 11 |
| Processor data to ES8311 | 9 |
| Speaker amplifier control | 53 |

The web documentation's quick GPIO table has different audio signal labels;
do not use that table alone to generate the configuration. The schematic shows
ES7210 SDOUT1 connected to GPIO11 through R87, while its SDOUT2 route has an
unpopulated R93. The AEC section feeds a playback reference into ADC channel 3.
That circuit alone does not implement the echo-cancellation algorithm.
[Main-board schematic](https://files.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-4B/ESP32-P4-WIFI6-Touch-LCD-4B.pdf),
[community audio configuration](https://github.com/chrisdunnname/esphome-p4-86-panel-eth-2ro-lvgl/blob/main/esp32-p4-86-panel.yaml).

ESPHome 2026.9.0 has standard `es7210`, `es8311`, I2S microphone and speaker
components. Local source inspection found the ES7210 driver defaults to
non-TDM output, with microphone channels 1/2 on SDOUT1 and 3/4 on SDOUT2. Capturing
the onboard microphones is therefore a different task from acquiring the AEC
reference. Do not promise beamforming, reliable interruption during playback,
or a particular listening distance without implementing and measuring them.
[ES7210 component](https://esphome.io/components/audio_adc/es7210/),
[ES8311 component](https://esphome.io/components/audio_dac/es8311/).

The installed I2S microphone and speaker implementations acquire the same
parent-bus lock. The initial design must serialize capture and playback, then
restart listening when playback releases the bus. A historical P4 report on
ESPHome 2026.4.2 describes failures during this handover. Its proposed cause is
the reporter's analysis, not a verified diagnosis for this project; its closed
status does not prove a fix. Treat handover as a hardware acceptance test.
[ESPHome issue 16043](https://github.com/esphome/esphome/issues/16043).

The local `micro_wake_word` schema permits ESP32 targets, and I2S explicitly
includes the P4. This supports trying the standard components but does not prove
that the chosen model, audio path and LVGL workload work together. Measure free
internal RAM, CPU load, audio dropouts, UI responsiveness and OTA headroom. The
board's PSRAM capacity is not a substitute for internal DMA-capable memory.

## Implementation plan

First build an isolated browser evaluation on a test branch combining the voice
work with the firmware preview. Supply real microphone audio and play the real
response, with no duplicate Vue voice interface. Compare results against the
quality checks above before selecting a production audio architecture.

The physical implementation then needs the following steps:

1. **Add and validate the physical board profile.** Follow
   [ADDING_A_BOARD.md](ADDING_A_BOARD.md), reusing the native DSI model, GT911 and
   existing layout code. Verify backlight, touch, networking and memory. Keep
   relay configuration separate from display bring-up.
2. **Prove audio in isolation.** Configure the shared I2C/I2S buses and standard
   codec components. Check both microphone channels, gain and a known playback
   sample. Verify the amplifier's control behaviour on the actual revision.
3. **Connect tap-to-talk to the selected backend.** For direct speech-to-speech,
   implement and test the panel-to-bridge audio and session adapter. For the
   standard Assist alternative, use `voice_assistant` actions and callbacks.
   Keep capture/playback ownership explicit, share the firmware overlay and
   mute control, and handle disconnects visibly.
4. **Add wake-word detection.** Start with one model. Stop detection during the
   conversation/playback and restart only when audio is available. Measure
   false activations and recovery after repeated conversations.
5. **Keep voice optional and reusable.** Put common behaviour in an opt-in
   feature package and pin/codec facts in board hardware. Advertise runtime
   capability through the existing feature mechanism. Do not add audio models
   or memory costs to boards without voice support.
6. **Verify integration and updates.** Test page navigation during voice use,
   announcements, mute, connection loss, errors and repeated sessions. Pin
   model/dependency versions for reproducible builds. Follow repository checks
   for the affected code and boards; measure the resulting binary sizes.

The existing emulator can later exercise the overlay and state transitions.
It cannot validate the physical microphones, I2S timing, acoustic feedback or
listening range. Browser-microphone input, if added, would be a separate host
adapter and must not be presented as a physical audio test.

## Evidence and remaining work

Reviewed vendor documentation and schematic, current ESPHome documentation,
installed ESPHome 2026.9.0 component sources, the repository board catalog and
Home Assistant voice documentation. A same-board project also lists voice
support as testing, providing another reference rather than a finished feature
to assume works here.
[Same-board project](https://github.com/alaltitov/Waveshare-ESP32-P4-86-Panel-ETH-2RO).

This branch currently contains documentation only. No speech service has been
installed, no audio has been recorded, no firmware compiled or flashed, and no
change made to the running Home Assistant deployment.
