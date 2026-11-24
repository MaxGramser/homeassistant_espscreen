# Sounds

A screen with a speaker plays three kinds of sound that you choose in Tessera: what rings when another screen calls it,
the chime when the doorbell rings, and a sound when an alert comes up. This is how they work, and the recipe for a new
kind.

## Choosing

Each kind has its place on the editor's Events page: **Calls** (the ringtone), **Doorbell** (the chime) and **Alerts**
(the alert sound). There you choose one sound for every screen, and, if you like, another for a screen of its own, or
**No sound**. Only screens with a speaker are listed.

Six sounds come with the app: Classic, Marimba, Digital, Bell, Ding-dong and Notice. Classic is the ring and Ding-dong
the chime the screens played before they had a choice. Nothing changes by itself: a call rings Classic, a doorbell
chimes Ding-dong and an alert stays silent until you choose otherwise.

## Volume and Test

Each kind has a **Volume** slider, from -40 to 0 dB: where the loudest moment of its sound sits. A call's ring starts
at -20 dB and so does an alert's sound; a doorbell's chime starts at -7 dB, as loud as the screens chimed before,
because a chime and an alert play at the screen's own volume while a ring raises the speaker to the top. A volume is
kept once you move its slider; until then the kind follows where it starts.
The small speakers of these screens distort when a sound is louder: at -6 dB a ring still distorted on a Guition 10.1,
and of -10, -14 and -20 dB the last sounded best. The app makes the file at that volume itself, so a screen with any
firmware that takes the sound gets it at the new volume with its next ring.

Each screen under **Per screen** has a **Test** key: the screen plays its sound of that kind now, the way it will for
real. For a call that is a ring of six seconds at the volume a ring stands at, with "Ringtone test" as the caller and
nobody on the other end; for a chime and an alert's sound, the sound once. A screen in a call is not rung.

## Louder than the screen

A call's ring, and a plugin's sound that asks for it (plugin API 0.29, `tessera::audio::raise_volume`, as an alarm
clock does), play louder than the screen's own volume. Each of them lifts the speaker: it plays at the loudest of the
screen's volume and every lift that is up, and when the last lift comes down the screen's volume comes back. One place
keeps what that volume was (`volume_lift.h`), so an alarm and a ring that overlap never put back each other's level
and never leave the speaker loud, in whatever order they stop.

- A lift never makes the screen quieter: where the screen already stands louder, it stays there.
- A plugin asks on the screen's own scale, 0 to 1 as Home Assistant shows the volume (1 is its 100 %); the ring stands
  at the top of that scale.
- Someone who moves the volume while a lift is up (Home Assistant, the settings page) keeps what they chose.
- Nothing of a lift is stored. The screen's volume is the media player's, which ESPHome keeps and sets at every start,
  so a restart or an update in the middle of a ring comes back at the screen's own volume. An update takes every lift
  down before it starts.
- A muted screen stays muted.

## A sound of your own

Under any kind, **Add your own sound** opens the audio editor. Drop a sound file on it or choose one (WAV, MP3, M4A,
OGG, FLAC, whatever the browser plays); the browser decodes it and brings it to 16 kHz mono. The editor shows:

- the whole file in a thin strip on top, with the part that plays in it: drag the part along a long song there;
- that part large below it, with room on either side, a grip at its start and end that shows its time, and a ruler;
- the part's length against the most it may be: a ringtone at most 3 seconds, with the pause you want before it
  rings again, since it plays back to back for as long as the screen rings; a chime at most 5 seconds and an alert
  sound at most 3, each played once.

Drag the part or a grip on either waveform; the arrow keys move a grip or the part by 0.05 s (Shift: 0.5 s), and the
space bar plays. Play plays that part the way the screen will. What is kept is not the file as it came:

- the bass under 400 Hz is filtered out: the small speakers cannot play it, and it only takes level the rest could use;
- the ends fade over 8 ms, so a ring that loops does not click at every turn;
- the level is set so the loudest sample is at half of full scale, the same for every sound; what a screen plays is
  then set by the kind's Volume.

The app checks the finished WAV again (16 kHz, mono, 16 bits, a quarter of a second to 5 seconds) and keeps up to
twelve sounds of your own, in its own data, so they are still there after a restart of the app or a screen. A sound of
your own can be chosen for every kind whose length it fits. Removing it puts whatever played it back on that kind's own
sound.

## How a sound reaches a screen

Every sound is a file of the app (docs/SCREEN_FILES.md), named by its content. The message that needs it carries its
link, or `none` for silence:

| Kind | Message | Field | Plays |
|---|---|---|---|
| Call | the op `call` with state `ring` | `rt` | back to back while it rings |
| Doorbell | the op `doorbell` of a ring | `ch` | once per ring |
| Doorbell, on a screen that shows its alert | the op `sound` beside the alert | `u` | once |
| Alert | the op `sound` beside the alert | `u` | once |

A screen downloads a file it does not have and keeps it in memory until a message names another, so a new choice needs
no update: it plays with the next ring. After a restart of the screen it downloads the file again with the first
message that names it. A sound waits at most 1.5 s for a file on its way; then a ring rings and a chime chimes with the
screen's own sound, and an alert shows without one.

A doorbell automation with `chime: false` rings without a chime, as before. An alert sent with the
`esp_screens_show_alert` event plays its sound unless the event has `sound: false`. An alert from a screen's own
`show_alert` action, called directly, plays none: that action's fields are fixed, and only the event goes through the
app.

The chime and the alert sound go only to a screen whose hello says `sounds` (a speaker and the download of
`SCREEN_PICTURES`). An older screen plays its own ring and chime as before and nothing with an alert. The ring's `rt`
needs no feature: the module call reads it since it came. The switch **Call ringtone** still turns a call's sound off.

## In the code

| Part | Where |
|---|---|
| The library, the choices, the built-in sounds, the volume | `screen_manager/app/sounds.py` (`KINDS`, `BUILT_IN`, `VOLUME`, `at_volume`, `sounds.json`) |
| The Test key | `server.py`: `sound_test` |
| The links in the messages | `server.py`: `call_send`, `doorbell_show`, `broadcast` and `alert_sounds` |
| The editor | `web/src/components/sounds/SoundPicker.vue` and `AudioEditor.vue` (the audio editor, one for every kind), `web/src/stores/sounds.ts`, `web/src/model/ringtone.ts` |
| A file kept by its name, the sound that plays once | `components/smart_display/kept_sound.h` |
| The ring, the chime | `module_call.cpp` (`want_tone`, `ring_tone`), `module_doorbell.cpp` (`chime`) |
| A sound louder than the screen, and the volume put back | `components/smart_display/volume_lift.h` (`tests/test_volume_lift.cpp`), bound in `packages/features/audio-player.yaml`; `tessera::audio::raise_volume` in `plugin_host.cpp` |

## A new kind of sound

1. A row in `sounds.KINDS`: its default (a built-in sound or `none`, so nothing changes by itself), its longest sound and
   whether it loops.
2. The message that plays it carries `sounds.link(kind, base, screen)` (through `Manager.sound_link`, which asks for the
   screen's `sounds`), or the op `sound` for a sound that plays once and belongs to no module.
3. On the screen, a `kept_sound::Kept` for a module's own sound, or `kept_sound::play` for one that plays once.
4. `<SoundPicker kind="..." />` in the kind's part of the editor, and its title and text under `editor.sounds.kinds`.
5. A row in the tables above.

## Tests

`tests/test_sounds.py` checks the library, the kinds and their limits, the built-in sounds against the screen's own, the
links in the messages and the files path; `tests/test_wav.cpp` the screen's reading of a WAV; `web/tests/ringtone.spec.ts`
the cut, the filter, the fades and the level.
