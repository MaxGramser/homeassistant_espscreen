# A board's second chip

Some boards have a second chip beside the ESP32 that Tessera runs on. The SenseCAP Indicator has an RP2040, which
drives its buzzer, reads its sensors and holds its microSD slot. Tessera has a firmware of its own for that chip, and
with it the buzzer is the screen's speaker.

## The parts

| Part | Where |
|---|---|
| The chip's firmware | `chips/indicator-rp2040/` (the Pico SDK): `src/main.cpp`, `src/sound_out.cpp` |
| The words between the two chips | `components/chip_link/chip_protocol.h`, built by both ends |
| The screen's side | `components/chip_link/`: the line (`chip_link.cpp`) and ESPHome's speaker on it (`chip_speaker.cpp`) |
| The speaker in a board file | `packages/features/chip-speaker.yaml` |
| The built file in the app | `screen_manager/app/chips/<name>.uf2` and `.json`, by `tools/build_chips.py` |
| How it gets onto the chip | a step of the board (docs/BOARD_STEPS.md, the kind `chip_firmware`) |
| The chip from a computer | `tools/chip.py` |

## The line

The two chips share a serial line (on the Indicator the ESP32-S3's GPIO19 and GPIO20, the RP2040's GPIO17 and GPIO16),
at 921600 baud. A frame is a type, a payload and a CRC-16 of the two, COBS-encoded and closed with a zero byte, so a
reader that lost its place finds the next frame at the next zero. Seeed's own firmware frames its packets the same way
without the check and with types from 0xA0; Tessera's types stay below that, so the two are never taken for each other.

| Type | From | What |
|---|---|---|
| `HELLO` | screen | who are you? |
| `HELLO_BACK` | chip | the protocol, its firmware's version, what it can do, the samples it holds, a number drawn at its start |
| `BEGIN` | screen | a sound starts: its stream number and its rate |
| `AUDIO` | screen | samples of that stream, 16 bits, mono |
| `END` | screen | the sound is over: play out what is held, or stop at once |
| `VOLUME` | screen | what every sample is multiplied by |
| `TRY` | screen | play your own two notes |
| `STATUS` | chip | the samples taken in and played, 50 times a second while a sound is open |

The screen asks `HELLO` every two seconds until a chip answers and every ten after that. A chip with another firmware
never answers; then the screen has no sound, says so to the app (`hw::speaker_now`) and waits for nothing. A chip that
restarted answers with another start number, and the screen tells it its volume again.

The screen sends only what the chip has room for: the chip holds two seconds of sound, the screen counts what it sent
against what `STATUS` says was played (`chip_protocol::may_send`). So a screen that draws for half a second leaves no
gap. The same frames travel over the chip's USB port, which is how `tools/chip.py` and the editor ask a chip which
firmware it runs.

The line is the ESP32's UART taken straight from ESP-IDF, with a buffer for what it sends. ESPHome's `uart:` writes
without one and would hold the screen's loop for a third of every second of sound.

## The sound

The buzzer's pin has two levels. The chip switches it 64 000 times a second with a pulse whose width is the sample, and
the buzzer's coil evens the pulses out, as a class D amplifier's speaker does. A stream of any rate up to 48 kHz is
brought to that rate on the chip.

A coil that rests in the middle of its swing carries current, so the middle is held only while there is sound: it comes
up in 16 ms before the first loud sample, slowly enough to be silent, and goes down after a quarter of a second of
quiet. At rest the pin is low. A watchdog restarts the chip if its program hangs, so the coil is never left switched on.

**A buzzer rings at one pitch.** A full-scale tone every 50 Hz, heard by a microphone, gave for a SenseCAP Indicator:
level within 4 dB from 2.5 to 3.05 kHz, 10 dB down at 2.4 and at 3.2 kHz, 20 dB down at 2 kHz and at 1 kHz. The
built-in sounds of docs/SOUNDS.md have no note in that band and were all but silent. So a screen whose speaker is a
buzzer says `buzzer` in its hello, and the app sends it each built-in sound with its notes moved into the band
(`sounds.BUZZER`): the same rhythm and shape, 20 dB louder at the microphone. A sound of your own plays as it is, and is
heard as far as it has something between 2.5 and 3 kHz.

A buzzer is also quieter than a speaker and does not distort at full scale, so a kind's volume is raised by 20 dB for
it, up to full scale (`sounds.BUZZER_LIFT`). The screen's own Volume (Extras) then turns it down, evenly in decibels
over 30 dB.

## What the screen has with it

`features/chip-speaker.yaml` gives the screen the speaker under the id plugins count on (`ts_speaker`), so everything
that plays on a speaker plays on the buzzer as it is: an alert's sound, a doorbell's chime, the Test key on the Events
page, a plugin's sounds, and a sound that asks to be louder than the screen (`volume_lift.h`). It has no media player
and no microphone: Home Assistant plays no music on a buzzer, and a call needs both ends.

## Building it

`tools/build_chips.py` builds every chip under `chips/` (each folder's `build.sh`: the Pico SDK in `PICO_SDK_PATH`, an
`arm-none-eabi-gcc` with its C library in `PICO_TOOLCHAIN_PATH`, and picotool) and writes the file and its record into
`screen_manager/app/chips/`. The app ships the built file, as it ships the browser's firmware preview: no Home
Assistant compiles for an RP2040. The record holds the version (`version.txt`), the file's size and SHA-256, the USB ids
of the chip's port, the name of its drive, and a hash of the sources. `tools/build_chips.py --check` compares that
hash, so a source that changed without a new build is caught (`tests/test_board_steps.py` runs it).

A change of the firmware raises `version.txt`: a screen whose chip runs an older one is then offered the update.

## From a computer

```
uv run --with pyserial python tools/chip.py hello          # which firmware the chip runs
uv run --with pyserial python tools/chip.py flash FILE.uf2  # restart it as a drive and copy the file
uv run --with pyserial python tools/chip.py play FILE.wav   # play a WAV on it
uv run --with pyserial python tools/chip.py try             # its own two notes
```

## Going back

Seeed's firmware goes back on the same way: restart the chip as the drive `RPI-RP2` (`tools/chip.py flash` does it, or
hold the button inside the small hole of the case while the USB cable goes in) and copy Seeed's `.uf2` onto it. The
screen then works as before, without sound.

## Not yet

- The sensors of a D1S and a D1Pro (CO2, temperature and humidity, tVOC), the Grove ports and the microSD slot. The
  frame types leave room for them.
- A new firmware for the chip over the screen itself, without the USB cable.

## Tests

`tests/test_chip_protocol.cpp` (the frames and the room), `tests/test_sounds.py` (a buzzer's sounds and their volume),
`tests/test_board_steps.py` (the built file and its record).
