# Physical panel voice, experimental

The optional `voice` audio mode connects the Waveshare ESP32-P4-WIFI6-Touch-LCD-4B
(`wavesharep4`, also sold as ESP32-P4-86-Panel-ETH-2RO) to the add-on's existing
voice assistant. Start a conversation from **Settings → Audio → Start voice**.
Wake-word activation is off by default. Enable **Wake word enabled** in Audio
and choose Okay Nabu, Hey Jarvis, Alexa or Hey Mycroft to start a session hands-free.
This preference survives reboot. Recognition is local; no audio reaches the add-on
until a wake word or Start voice requests a session. The diagnostic in `test` mode
remains a separate, timed local test.

This branch combines board/audio support and the browser voice assistant. It is
not part of either independent contribution until the integration is reviewed.
Hardware acceptance of local recording does not establish end-to-end voice quality.

## Set up

1. Install this add-on build and enable **Enable voice assistant** in its
   Configuration tab. Configure OpenAI or Claude in **Settings → Voice assistant**.
   [Provider setup](VOICE_PREVIEW_POC.md) applies to physical panels too. OpenAI
   uses direct Realtime audio. Claude additionally needs a Home Assistant voice
   assistant with working speech-to-text and text-to-speech services.
2. Add the physical panel to Home Assistant and give it a saved Tessera layout.
   Under **Physical voice panel**, choose it and enter the add-on's LAN address,
   for example `ws://homeassistant.local:8098`. The panel must reach the published
   media port. An ingress URL or `localhost` on the panel is not this address.
3. Choose **Pair panel** and download the voice configuration. Merge its three
   substitutions into this panel's **Build & install → Override YAML**, preserving
   other settings. Change any previous `AUDIO_MODE` entry to `voice`; do not add a
   duplicate. Keep the downloaded token private. It is shown once and authorizes
   this panel's voice sessions, but contains no provider API key.
4. Build and install from this integration branch, using the panel's existing
   profile, Wi-Fi and API keys. The current upstream package without this feature
   cannot build `AUDIO_MODE: voice`. A local checkout build uses the same packages;
   an installed add-on needs a published source ref containing this integration.
5. On the panel, hold Home to open Settings, open Audio and select **Start voice**.
   You can speak directly after a recognized wake word. **Stop voice** and microphone mute end
   capture. Provider settings choose the same reply destination as the browser;
   **Screen / this browser** means the panel's connected speaker here.

The voice indicator sits to the left of the top-bar clock on every tile page,
not just Home. All three states use the same space so the clock stays in place:

- A muted grey ear means local wake-word detection is running and ready.
- A blue microphone means the panel is ready to capture your question.
- A blue hourglass means a response is pending.

The indicator hides during spoken replies and when the microphone is muted.
After Stop or the silence timeout, the grey ear returns once the enabled wake
detector is ready again. With wake detection disabled, no idle icon appears.
The indicator and its additional glyphs are included only in `voice` firmware builds.

Replacing or revoking a pairing ends any active session. Replacement credentials
must be flashed before the panel can connect again. Disable this feature by
returning `AUDIO_MODE` to `hardware` or `off` and rebuilding. The add-on option
can also stop access without a firmware update.

`ws://` carries microphone audio, replies and the pairing token over the local
network without transport encryption; use it only on a trusted LAN. `wss://`
requires a TLS reverse proxy with a certificate trusted by the ESPHome
certificate bundle and WebSocket forwarding to the media port. Do not publish
the unencrypted media endpoint to the internet.

## What runs where

ESPHome owns the ES7210/ES8311 codecs, microphone source conversion, speaker and
ring buffers. `PanelVoice` adds a bounded WebSocket transport task. Driver and UI
calls stay in the main loop, so network waits do not block touch rendering.
Capture is mono 16-bit PCM at 16 kHz; the add-on resamples to OpenAI's 24 kHz
format with PyAV and converts replies back to 16 kHz. OpenAI has no separate
STT or TTS stage. Claude reuses the existing HA speech and conversation services.
Provider keys, name resolution, Assist exposure and action validation remain in
the add-on. Spotify track search reuses the existing **Spotify search** settings
and credentials there; playback still uses Home Assistant. Neither Spotify keys
nor catalogue code enter the firmware. No media or other tile renderer is replaced.

With wake-word activation enabled, the panel prepares an authenticated connection
while the detector listens locally. OpenAI's Realtime session is opened ahead of
the wake; no microphone audio is sent while waiting. Claude prepares the selected
HA speech configuration and uses the add-on's HTTP connection pool for its text
requests. It has no continuously open native audio session.

A half-second local rolling buffer preserves the end of the wake-word detector's
stream. After activation, a bounded five-second buffer holds the start of the
command while the provider becomes ready. A full buffer or failed connection ends
the attempt rather than silently dropping words. No one-second delay is applied
after recognition; the microphone handoff still waits for ESPHome to release it.

Each completed conversation is discarded. With wake-word activation still enabled,
the panel prepares a fresh connection for the next wake, retrying failed preparation
with a bounded backoff. Idle OpenAI connections are renewed before their session
limit. Disabling wake-word activation or muting the microphone closes preparation.
Changing provider, credentials, voice or reply output invalidates a prepared session.

The panel sends its actual displayed page and configuration revision. The add-on
rejects a stale revision and takes the layout from its own saved record. Each
activation refreshes the visible page, entity state and current time in Home
Assistant's time zone. Context metadata includes the configured HA home name and
coordinates as the default location for both providers. Changes to HA's home
configuration are picked up without another panel setting. Missing or invalid
coordinates leave the default location unknown. A spoken place name overrides
this default; a home label or room name must not be treated as a city.
Live public information still requires a tool
lookup, and its observation time must be distinguished from the lookup time. Page
changes update voice context. Only the paired physical panel can use its token;
browser clients and another device identity are rejected.

Opening the prepared connection sends assistant instructions, panel context and
tool definitions, not a user question. After activation, OpenAI receives the
spoken audio directly. The assistant can use tools behind the conversation for
current information or device commands. Follow-up questions use the same active
conversation. Instructions follow the user's question language, regardless of
the wake phrase or the language of retrieved facts, with Dutch as the default.
Replies use short spoken language and metric units. Stable general knowledge
can be answered directly; current facts use a lookup only when needed. Unsupported
actions are reported as unavailable rather than promised. These instructions
are shared with Claude and do not add a transcription step to OpenAI audio.
Activation alone is silent: a wake phrase or its trailing audio fragment uses
the shared `wait_for_user` tool without generating a greeting or spoken follow-up.
A question spoken directly after the wake phrase is handled normally. Waiting
keeps the panel's existing silence deadline; it does not leave the microphone
open indefinitely. There is currently no greeting setting.

Microphone and speaker take turns because this board shares one I²S bus. This is
half-duplex, not acoustic echo cancellation: the panel pauses capture during its
reply and resumes only after playback. Music-start confirmations end the session
to avoid listening to lyrics. Stop, microphone mute, HA loss, transport loss,
silence timeout and the ten-minute session limit release audio resources.
There is no automatic microphone restart after a failed conversation. If wake-word activation
is enabled, local detection resumes after audio has stopped and a one-second
cooldown. Preparing a connection never starts a conversation: another wake word
or Start voice is required. Microphone mute
stops both kinds of capture. Capture and playback also have
bounded per-turn buffers and deadlines. Replies are limited to 45 seconds.

The add-on log records voice phases, elapsed time, accepted audio duration and
error categories, without audio samples, transcripts, pairing tokens or API keys.
Current-information lookups log the provider and elapsed time separately.
Panel logs distinguish add-on errors, heartbeat loss and microphone start timeouts.
Local wake detection pauses during a conversation: another wake phrase spoken
before the conversation has ended is part of that conversation's audio. Separate
conversations clear the input buffers and use fresh provider sessions.

The `voice` mode includes audio hardware, the transport and ESPHome micro_wake_word
with four trained models, but not the local recording test engine. `off`, `hardware`, `test` and other boards do
not link the voice transport or its WebSocket dependency. Only `test` and `voice`
include wake-word models; `hardware`, `off` and other board profiles exclude them.
The shared text index retains empty entries for omitted voice strings. PyAV is included in the
add-on image and is imported only when physical voice audio is used.

## Future custom wake words

"Okay Tessera" and "Hey Tessera" are proposed follow-ups, not supplied models.
Train and validate each phrase with the open-source
[microWakeWord training framework](https://github.com/OHF-Voice/micro-wake-word).
Generate varied voices and include the intended Dutch and English pronunciations,
then evaluate on separate real recordings from the target panel. Test missed
detections, similar phrases, conversation, television and music. The basic training
notebook is a starting point and does not establish production recognition quality.

Export a quantized streaming microWakeWord model (`.tflite`) with its matching
version-2 JSON manifest. Publish versioned assets with their training configuration,
evaluation results and redistribution terms. ESPHome accepts a local manifest or
a pinned URL; see [custom model configuration](https://esphome.io/components/micro_wake_word/).

Integrate a tested model through `packages/features/audio-wake-word.yaml`, including
the enable/disable script. Append its selection after the existing options to preserve
saved numeric preferences, and keep the firmware, add-on and editor option tables
consistent using the setting-range checks. Include models only in the optional
wake-word packages of supported boards and measure their flash and RAM cost.
Other boards should not acquire a model merely because it exists in the repository.

No additional recognizer, paid wake-word service or change to the OpenAI/Claude
conversation layer is needed. Changing the displayed name alone does not change
which phrase a model recognizes.

## First hardware check

Use a harmless Assist-exposed test light. Check a general spoken answer and a
light command with each provider, then Stop during connection, listening and
playback. Confirm that silence ends the session, microphone mute stops input,
and losing the add-on connection stops capture without restarting. Verify that
normal tiles and touch still work during a conversation. Finish with the test
light off. Enable a wake word and check activation, display wake-up, reply playback
and return to local detection. Disable the setting and verify that only Start voice
can start another session. Recognition at a distance and echo cancellation are not
established by a software test.
