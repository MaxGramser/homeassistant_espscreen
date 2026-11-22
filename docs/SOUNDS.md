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

## A sound of your own

Under any kind, **Add your own sound** opens a sound file (WAV, MP3, M4A, OGG, FLAC, whatever the browser plays). The
browser decodes it, brings it to 16 kHz mono and draws its waveform. You pick the part to keep by dragging it or its
edges:

- a ringtone at most 3 seconds, with the pause you want before it rings again, since it plays back to back for as long
  as the screen rings;
- a chime at most 5 seconds, and an alert sound at most 3, each played once.

Play plays that part the way the screen will. What is kept is not the file as it came:

- the bass under 400 Hz is filtered out: the small speakers cannot play it, and it only takes level the rest could use;
- the ends fade over 8 ms, so a ring that loops does not click at every turn;
- the level is set so the loudest sample is at half of full scale, the same for every sound: loud enough across a room
  at the volume a ring plays at, where 97 % made the speakers distort.

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
| The library, the choices, the built-in sounds | `screen_manager/app/sounds.py` (`KINDS`, `BUILT_IN`, `sounds.json`) |
| The links in the messages | `server.py`: `call_send`, `doorbell_show`, `broadcast` and `alert_sounds` |
| The editor | `web/src/components/sounds/SoundPicker.vue` and `SoundCutter.vue`, `web/src/stores/sounds.ts`, `web/src/model/ringtone.ts` |
| A file kept by its name, the sound that plays once | `components/smart_display/kept_sound.h` |
| The ring, the chime | `module_call.cpp` (`want_tone`, `ring_tone`), `module_doorbell.cpp` (`chime`) |

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
