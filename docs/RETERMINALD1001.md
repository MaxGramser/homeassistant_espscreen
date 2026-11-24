# Seeed reTerminal D1001

An 8-inch 800 x 1280 MIPI-DSI panel with GSL3670 capacitive touch, on an ESP32-P4 with 32 MB of flash and PSRAM and an
ESP32-C6 for Wi-Fi, running on a 2500 mAh battery. Board key `reterminald1001`, status experimental, board file
`packages/boards/reterminald1001.yaml`. The pins come from Seeed's BSP
([Seeed-Studio/reTerminal-D1001](https://github.com/Seeed-Studio/reTerminal-D1001), `esp32_p4_re_terminal_d1001.h`).

## What it has, and where Tessera configures it

| Part | Chip, pins | In Tessera |
|---|---|---|
| Panel | JD9365, 2 MIPI-DSI lanes | ESPHome's `mipi_dsi` preset `SEEED-RETERMINAL-D1001` |
| Touch | GSL3670 on GPIO37/38 (`touch_bus`) | ESPHome's `gsl3670` preset of the same name |
| Wi-Fi | ESP32-C6 over SDIO, GPIO6-11, reset GPIO13 | `hardware/esp32p4-c6.yaml` with this board's pins |
| Power, resets | XL9535 expander on GPIO20/21 (`board_bus`) | the board file |
| Backlight | PWM on GPIO14, at 1220 Hz | `features/backlight.yaml` |
| Battery | voltage on GPIO18 through a divider of two, charging on GPIO15 | `features/battery-adc.yaml` with Seeed's discharge curve |
| Speaker | ES8311 and an NS4150B, on its own I2S bus | `features/audio.yaml`, with its volume under Extras |
| Microphones | two, through an ES7210, on a second I2S bus | `features/audio.yaml` |
| Motion | LSM6DS3TR-C at 0x6A | its temperature, and Wake when moved |
| Clock | PCF8563 at 0x51 | keeps the time while Home Assistant is away |
| Button | GPIO3, high while pressed | the standby key, `features/standby-key.yaml` |
| RGB LED | GPIO22, 36, 23, lit low | `features/rgb-led.yaml` |
| Camera | SC2356, 1 MIPI-CSI lane, SCCB 0x36 on `touch_bus`, power on expander pins 1, 3 and 11 | powered by the board file, driven by the Screen camera plugin (below) |
| SD card, LTE, LoRa | | not configured |

## Things to know

- **The expander's numbers.** ESPHome numbers the XL9535's two ports 0-7 and 10-17, Seeed's BSP its sixteen lines 0-15.
  The BSP's line 8 (the power hold) is pin 10 in ESPHome, its line 10 (the charger) pin 12, its line 12 (the touch
  reset) pin 14.
- **The power hold.** On the battery, the board turns itself off unless pin 10 stays high; the board file holds it on.
- **The touch starts after the display.** The panel's power on expander pins 0 and 7 also feeds the touch chip, and
  the display switches it on. From no power at all (a flat battery, the first start) the expander starts with every
  pin off, so a touch that started first found no chip: its firmware writes failed (`I2C write reg ... failed (2)` in
  the USB log) and the screen never saw a finger. A restart hid it, as the expander keeps its pins. The board file
  gives the touch `setup_priority: 500`, after the display's 600 and before LVGL's 395.
- **The battery is measured only while nothing charges it.** The level comes from the cell's voltage and Seeed's
  curve, and a charging cell reads above what it holds: about 0.1 V from the charge current at once, and more that
  fades over minutes, so after half an hour on the charger the level ran 15 % ahead. Pausing the charger for a reading
  (pin 12) takes away only the first part: on the bench 3.704 V while charging, 3.586 V 0.2 s into a pause and still
  3.570 V after a minute. So while the battery charges the board file gives no level (Home Assistant shows it as
  unknown, the top bar the charging bolt without a number), and measures again, once a minute, two minutes after
  charging stops: against the steady fall of the screen's use, the cell read 48 mV high a minute after unplugging,
  6 mV at two minutes and nothing at three. On the battery the level only goes down.
- **The log is on USB.** `hardware/esp32p4-c6.yaml` puts the log on UART0, whose pins on the ESP32-P4 are GPIO37 and
  GPIO38, the touch bus on this board; UART0 there crashed the first boot. The board file moves the log to the USB port.
- **16 MB of the 32.** ESPHome takes OTA on 32 MB of flash only with ESP-IDF's experimental features, so the firmware
  uses the first 16 MB, as the other P4 boards do.
- **Wake when moved** feels the board itself: picked up, tilted, turned or knocked. It does not see someone walking
  past. The board reads its LSM6DS3TR-C ten times a second and hands every reading to
  `features/wake-when-moved.yaml`, whose detector (`components/smart_display/moved.h`, `tests/test_moved.cpp`) keeps a
  resting value per axis and says the board moved when one turns by more than 3 degrees a second or moves by more
  than 0.06 g. Both come from a D1001 on a desk (`tests/data/moved_d1001.csv`): at rest it read at most 0.86 degrees a
  second and 0.021 g, picked up gently at least 22 degrees a second and 0.17 g. With Debug mode on, the log shows the
  largest movement of each second, to measure another board the same way.
  ESPHome's `motion` reports acceleration in g, not in m/s²: the first version compared two readings with 1.0, a whole
  g, which only shaking reached. The log names the axis and how far it moved (tag `moved`, at most once in two seconds).

## The camera

The SC2356 answers with the chip id and the address of the SC202CS (0xEB52 at 0x36), so the SC202CS driver of
Espressif's own `esp_cam_sensor` finds it, and its colour tuning for this sensor gives a neutral picture once the
exposure has settled. The board file powers the sensor at start as Seeed's BSP does and names its bus in `CAMERA_I2C`:
that is the feature `camera_sensor` (docs/PLUGINS.md). Until ESPHome has a MIPI-CSI camera of its own (pull request
#16944), the Screen camera plugin brings the driver (`esp_video_camera`) and makes it a camera of the screen's device in
Home Assistant: a 1280 x 720 picture in about half a second, a stream at up to five pictures a second.

- **One supply for both MIPI ports.** The camera input takes its PHY supply from the same internal regulator as the
  display (channel 3, 2.5 V). ESP-IDF shares a channel only when nobody may change its voltage, so
  `hardware/esp32p4-c6.yaml` claims it as not adjustable, ESPHome's default.
- **A protective film** comes on the lens of a new board and makes the picture hazy.

## Tried on the glass

Picture, colours, the way up, touch in every corner, a card held open, the settings strip, Wi-Fi, the battery, the
button, the LED, Home Assistant's TTS through the speaker, the Extras page and card, the camera in Home Assistant with
the Screen camera plugin, and the Voice assistant plugin end to end. Firmware 0.53.0 from the `d1001`
branch, chip revision v1.3.
