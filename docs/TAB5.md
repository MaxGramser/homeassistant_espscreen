# M5Stack Tab5

The M5Stack Tab5 is sold with one of two display and touch controllers, the ST7121 or the ST7123. They need a different
start sequence, and the wrong one leaves the screen black with its backlight on, without an error. The label on the back
is not a reliable guide. The factory firmware's USB log says which one a unit has:

```text
Detected ST7121 touch controller (FW version: 1), using ST7121 display
Detected ST7123 touch controller (FW version: 3)
```

The first reported unit has an ESP32-P4 eco2 at chip revision v1.3, 16 MB SPI flash and 32 MB PSRAM. The screen is
720 × 1280 pixels, used as a 1280 × 720 landscape layout. The board file selects ESPHome's `M5STACK-TAB5-ST7121` or
`M5STACK-TAB5-ST7123` MIPI-DSI model through its `DISPLAY_MODEL` substitution (`ST7121` or `ST7123`). The touch uses
ESPHome's `st7123` platform for both controllers.

## Install and test

The Tab5 is listed as a new board after successful hardware testing. In **New screen**, choose **M5Stack Tab5**, then
the display controller: **ST7121** (the default) or **ST7123**. If the screen stays black with its backlight on after
the install, build it again with the other one. The ST7123 was confirmed by two owners (GitHub #240), first through an
Override YAML that changed only the display model.

In Tessera, the screen's board label comes from its **Screen board** diagnostic and should identify the Tab5 (`tab5`).
If it identifies another board, such as the CYD, reinstall the screen using the **M5Stack Tab5** profile so its firmware
reports the correct board.

The landscape grid starts with three rows of tiles; the Grid button beside the pages in the editor gives it more, up to
five by five, without a new build (firmware 0.53.0+). Every grid takes up to 64 tiles across eight pages; the last page
may be partly filled. Standing up it starts on one column of five rows.

Camera tiles, live camera pictures, full-screen camera views, camera alerts and media artwork are enabled. Add a camera
entity to a screen tile to use these features.

The INA226 battery monitor exposes **Battery Voltage** as a diagnostic sensor and **Battery Level** as a percentage
sensor in Home Assistant. The percentage is an estimate from the 2-cell lithium-ion pack voltage, using a piecewise
voltage curve from 6.0 V (empty) to 8.4 V (full); voltage changes under load or while charging can affect the estimate.

The battery shows in the top bar from firmware 0.41.0, with Home Assistant's icon for its level and while it charges
(**Add → Battery** in the editor). **Battery Charging** is on while more than 50 mA flows into the pack, from the same
INA226, and **Battery Current** shows that current as the INA226 reads it, negative while the pack charges.
docs/BATTERY.md has the details.

The ESP32-C6 that does the Wi-Fi and the battery charger get their power from the second I/O expander (address 0x44),
which starts with every output off. The firmware switches on its Wi-Fi power (P0), quick charge (P5) and charge enable
(P7) at boot, as M5Stack's own firmware does. Without the Wi-Fi power output, the screen only finds its network while
an earlier firmware left the C6 powered, and after a cold start it stops at `esp_wifi_init failed: ESP_FAIL`.

After flashing, confirm that the screen boots, has a stable picture with correct colors, responds at the four corners
and across the surface, changes pages, pairs with Home Assistant, and remains working after a restart and a cold start.
Check the USB log and report the firmware and board variant with the results.

## Speaker and microphones

The speaker (an ES8388) and the two microphones (an ES7210) are the screen's audio through `features/audio.yaml`: a
media player in Home Assistant for announcements, text to speech and music, a **Volume** and a **Microphone** setting
under Extras (on the screen and in Screen settings), and the speaker and microphone that plugins use, such as the voice
assistant and Tap sound. Both codecs share one I2S bus. By default the AEC transport (below) runs it in both directions
at once, so the microphone keeps listening while the speaker plays. With the plain I2S bus, as ESPHome's own Tab5
configuration has it, the board sets `AUDIO_HALF_DUPLEX` and they take turns: the speaker lets go of the bus after a
sound, and the microphone lets go of it whenever the speaker wants it, and listens again after. Either way the
amplifier (SPK_EN on the first I/O expander) is on only while sound plays.
The volume runs evenly in decibels from -45 dB to the ES8388's full scale.

Four choices are the Tab5's own, in its audio configuration. At start the board turns on the ES8388's LINE1 output, where the
speaker is connected: ESPHome's es8388 leaves the outputs off, and ESPHome's own Tab5 configuration turns them on by
hand. The microphones take their gain in the ES7210's analogue stage (30 dB), before the converter, and are read on
the right channel with their DC offset removed, as the working Tab5 voice configurations do. The speaker keeps half a
second of sound in its buffer, so a spoken answer that arrives over the C6's Wi-Fi in bursts plays without gaps.

## Echo cancellation

The Tab5 uses an AEC transport by default. It reuses the Waveshare P4's reviewed ES7210 extension,
Hane's pinned audio stack and Espressif's FD low-cost algorithm. **Hardware acceptance
is still pending for music playback, cold starts and the enabled/bypassed AEC comparison.**
A successful compile does not confirm audio quality, acoustic cancellation or
interruption of a voice assistant.

To use the plain I2S bus instead, select it in the screen's **Override YAML** and rebuild
only that screen:

```yaml
substitutions:
  TAB5_AUDIO_TRANSPORT: "i2s"
```

Keep the screen's own name, Wi-Fi settings and API/update keys. Plain I2S removes the AEC stack and its DSP libraries
entirely. It has no Echo cancellation switch, so the editor shows that row as unavailable.

The AEC transport adds **Echo cancellation** under Extras on the panel and, with the
matching app, under Screen settings. Home Assistant exposes the same switch and an
**Echo cancellation status** diagnostic. Switching off bypasses cancellation while
the filter keeps adapting; it is not a CPU-saving mode. "Enabled" reports DSP
initialization and selection, not a measured amount of echo reduction.

The shared `ts_microphone`, `ts_speaker` and `ts_media_player` interfaces remain.
No assistant, wake-word model or AI provider is installed by the audio transport.
Microphone gain stays at 30 dB, with codec ALC off for the initial comparison.

### Wiring and choices to verify

The [official schematic](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1132/Tab5_Schematics_PDF.pdf),
audio sheet, shows the ES8388's HPOUT_L feeding both the speaker amplifier and AEC_P
through R41 (0 ohm). AEC_P goes to ES7210 MIC3P; MIC3N is AC-grounded. This is an
electrical reference before the power amplifier, not sound captured by a second
microphone. Its gain starts at **0 dB**, with unity digital gain and no ALC, unlike
the attenuated Waveshare reference's 24 dB. Measure its level and clipping on hardware.

The codecs share MCLK30, BCLK27 and LRCLK29, with DOUT26 to the ES8388 and DIN28 from
the ES7210. One owner drives the full-duplex bus at 48 kHz with four 16-bit Philips TDM
slots. The ES7210's SDOUT1 order is MIC1, MIC3, MIC2, MIC4: microphone slot 2 retains
the physical MIC2 of the original right-channel input, and slot 1 supplies the
reference. TX slot 0 supplies the left DAC output. Check ES8388 playback/framing on
hardware as well as the microphone slot. LINE1 initialization, amplifier gating
and the 500 ms speaker buffer are retained.

This uses one microphone, with no beamforming. The extended ADC configures its
hardware high-pass filters; the native-I2S microphone's software DC correction is
not part of the AEC adapter. The stack converts the selected microphone and reference
together to 16 kHz for the speech AEC processor. Playback remains at 48 kHz, matching
the native player's rate. AEC bypass still delivers 16 kHz microphone audio and keeps
48 kHz playback. This uses the pinned stack's existing sample-rate converter; the new
bus rate and additional processing require another hardware acceptance test.

### Hardware acceptance

1. Keep a known working firmware available. Check display, touch, Wi-Fi and HA after
   a reboot and a cold start, before testing audio.
2. Compare music with the native 48 kHz path, then play a short spoken announcement
   at moderate volume. Check its beginning and end, then repeat with microphone
   capture running. Both must remain continuous. Check logs for a 48 kHz bus,
   16 kHz microphone output and conversion ratio 3.
3. Verify microphone mute and volume. Check the AEC switch on the panel and in HA,
   then in the matching Tessera editor, including its restored state after reboot.
4. With identical speaker volume and microphone gain, capture the microphone output
   during the same announcement with AEC bypassed and enabled. The enabled capture
   should contain less of the panel's own speech. Speak over the announcement too:
   the user's voice must remain intelligible. A silent/muted microphone is not a pass.
5. Inspect the raw microphone and reference levels with the optional sensors below.
   Check recorded PCM for clipping and compare the processed output separately.
   A zero or clipped reference must be fixed before tuning AEC. Repeat after cold
   boot and at several volumes, with headphones disconnected first.
6. Test the installed voice plugin separately. If it stops capture during playback,
   it cannot demonstrate simultaneous capture or interruption; board AEC alone does
   not change that plugin's conversation flow.

Record board/display and chip revision, firmware commit, ESPHome version, volume,
gain, AEC state and the boot/audio logs. Mark hardware results pending until a Tab5
owner performs these checks. Do not infer them from tests on a Waveshare panel.

For initial bring-up, this optional Override YAML adds the pinned audio stack's
existing raw-level sensors to Home Assistant. Use it together with the AEC transport
selection above and rebuild. The values are RMS dBFS, not a measurement of AEC
effectiveness; they help establish that the selected inputs carry audio. Remove
these diagnostic sensors when the measurements are complete.

```yaml
sensor:
  - platform: esp_audio_stack
    esp_audio_stack_id: board_audio_stack
    tdm_slot_levels:
      - name: "AEC reference level"
        slot: 1
      - name: "Microphone level"
        slot: 2
```

The shared implementation, pinned dependencies and upstream notices are described
in [P4 audio](P4_AUDIO.md#sources-and-attribution),
[the AEC wrapper](../components/esp_aec/README.md) and
[the ES7210 extension](../components/es7210_extended/README.md).
[Espressif's Tab5 BSP](https://github.com/espressif/esp-bsp/blob/master/bsp/m5stack_tab5/src/bsp_audio.c)
also initializes RX and TX together on a single peripheral; it is a hardware
reference, not proof that this TDM/ES8388 configuration has been tested. No BSP or
M5Stack application code is copied by this port. Existing dependency licenses remain
applicable, including the binary redistribution caveat in P4 audio.

## Camera

The 2 MP camera on the MIPI-CSI port answers on the system I2C bus and takes its 24 MHz clock from GPIO36, as M5Stack's
own firmware drives it. The camera's driver makes that clock with LEDC timer 0 and channel 0, so the backlight's PWM
stands on channel 2 (timer 1): on one timer, the backlight and the camera would undo each other. The board takes the
sensor out of reset at start (CAM_RST, pin 6 of the first I/O expander, active low); with that pin loose, the sensor
does not answer on its bus and the USB log says "Get sensor ID failed". The board states both (`CAMERA_I2C`, `CAMERA_XCLK_PIN`, the feature `camera_sensor`), and the
Screen camera plugin makes it a camera of the screen's device in Home Assistant.

## Built, not yet heard or seen

The audio and the camera are built for this board on the `dev` branch but have not run on a Tab5 yet. To try them,
install the app from the `#dev` repository URL (docs/RELEASING.md, "Testing dev"), update the screen, and add the
plugins. Then report:

1. an announcement or text to speech from Home Assistant on the screen's media player, at a few volumes;
2. the Volume and Microphone rows under Extras, on the screen and in Screen settings;
3. with the Voice assistant plugin: the wake word, a question and its spoken answer;
4. with the Screen camera plugin: a picture and the live view in Home Assistant, and the camera in the top bar;
5. the USB log of the first start, which says whether the camera's sensor was found.

## Hardware references

- [M5Stack Tab5 product page](https://shop.m5stack.com/products/m5stack-tab5-iot-development-kit-esp32-p4)
- [ESPHome MIPI-DSI display](https://esphome.io/components/display/mipi_dsi/)
- [ESPHome ST7123 touchscreen](https://esphome.io/components/touchscreen/st7123/)
- [Community ESPHome configuration](https://github.com/Axellum/M5-Tab5-ESPHome-LVGL)
- [ESPHome's Tab5 configuration](https://devices.esphome.io/devices/m5stack-tab5) (the audio pins and codecs)
- [M5Stack's Tab5 BSP](https://github.com/m5stack/M5Tab5-UserDemo) (`m5stack_tab5.h`, `m5stack_tab5.c`: the I2S pins and
  the camera's clock)
