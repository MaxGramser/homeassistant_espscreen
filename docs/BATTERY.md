# A battery in the top bar

A screen with a battery can show it in its top bar (firmware 0.41.0): the icon Home Assistant draws for a battery, at
its level and with a lightning bolt while it charges, and the percentage beside it if you want. The screen reads the
battery itself, so the item stays right while Home Assistant is away, which is when you most want to know how long the
screen keeps going.

In the editor, click the top bar and choose **Add → Battery**. It is offered only on a screen that has a battery. Two
choices: **Icon only** or **Percentage**, and **Always** or **Only when low** (20 % or less).

## How a screen knows it has a battery

The firmware follows Home Assistant's own convention. At boot it looks for:

- the first sensor in the **`battery`** device class, in percent: the level;
- the first binary sensor in the **`battery_charging`** device class: on while the battery charges. This one is
  optional; without it the icon never shows the lightning bolt.

That is all. The firmware does not care how the level is measured, so every way ESPHome has works: a fuel gauge or
power chip that gives a percentage, a voltage on a pin and a formula, or a curve of your own. A screen with such a
sensor has the word `battery` in its **Screen features** sensor and says it when it connects, and Tessera then offers the
item. A board whose files have a battery (`boards.json` `battery`, today the Tab5) is offered it before it ever
connected. A screen without one never shows it, also when a layout copied from another screen has the item: Tessera
leaves it out for that screen.

The same sensors show up in Home Assistant as the screen's **Battery Level** and **Battery Charging**, so you can use them
in automations as well.

## The ways to measure it

### A chip that knows the percentage

Fuel gauges and power chips work out the level themselves. Their level sensor needs the `battery` device class, which
any ESPHome sensor takes with `device_class: battery`. ESPHome's MAX17043 (also the MAX17048) on the I2C bus:

```yaml
sensor:
  - platform: max17043
    battery_level:
      name: "Battery Level"
      device_class: battery
```

Power chips such as the AXP2101 of the M5Stack Core2 v1.1 and CoreS3 come as community components with a level and a
charging flag of their own: give the level `device_class: battery` and, when the charging flag is a binary sensor,
`device_class: battery_charging`.

### A voltage and a formula

Many boards put the battery on an ADC pin through a voltage divider of two resistors, because a pin takes at most about
3.1 V and a charged lithium cell has 4.2 V. Two packages turn that into a level:

- `packages/features/battery-adc.yaml` reads the pin. You name it in `BATTERY_PIN` and give the divider's ratio in
  `BATTERY_DIVIDER`: the battery's voltage over the pin's, `2.0` for two equal resistors.
- `packages/features/battery-voltage.yaml` turns the voltage into a level with a formula of `v`, the voltage in volts.
  The default is a straight line from `BATTERY_EMPTY_VOLTS` (3.3) to `BATTERY_FULL_VOLTS` (4.2), clamped to 0 to 100 %.
  `BATTERY_LEVEL_FORMULA` replaces it with any C++ expression of `v`.

A board file in this repository includes both and sets the pin:

```yaml
packages:
  battery_voltage: !include ../features/battery-voltage.yaml
  battery_adc: !include ../features/battery-adc.yaml

substitutions:
  BATTERY_PIN: GPIO4
  BATTERY_DIVIDER: "2.0"
  BATTERY_EMPTY_VOLTS: "3.4"
```

`battery-voltage.yaml` works with any voltage, not only a pin: a board with an INA219 or INA226, or a fuel gauge that
only gives the voltage, names that sensor `screen_battery_voltage` and leaves `battery-adc.yaml` out.

**Pins.** On the ESP32 and the ESP32-S3 only an ADC1 pin works while Wi-Fi is on, because ADC2 belongs to the radio. ADC1
is GPIO32 to GPIO39 on the ESP32, GPIO1 to GPIO10 on the ESP32-S3, GPIO16 to GPIO23 on the ESP32-P4 and GPIO0 to GPIO6
on the ESP32-C6 ([ESPHome's ADC sensor](https://esphome.io/components/sensor/adc/)). With `attenuation: 12db` a pin
measures up to about 3.1 V, so choose the divider so a full battery stays under that.

**A curve instead of a straight line.** A lithium cell's voltage does not fall evenly: it stays near 3.7 V for most of
its charge and drops fast at the end. A straight line is a fair start; for a better level, measure the voltage at a few
points of a discharge on your own battery and give them to ESPHome's `calibrate_linear` with `method: exact`, which draws
straight lines between them. The Tab5 does this for its pack (some of its points):

```yaml
sensor:
  - platform: template
    name: "Battery Level"
    device_class: battery
    unit_of_measurement: "%"
    lambda: return id(my_battery_voltage).state;
    filters:
      - calibrate_linear:
          method: exact
          datapoints:
            - 6.00 -> 0
            - 7.00 -> 15
            - 7.40 -> 45
            - 7.80 -> 72
            - 8.40 -> 100
      - clamp:
          min_value: 0
          max_value: 100
```

### Whether it charges

A binary sensor in the `battery_charging` class, from whatever the board has:

- a charger's status pin, as a `gpio` binary sensor (`inverted: true` when the pin is low while charging, as most are);
- a power chip's charging flag;
- the current into the battery, with ESPHome's `analog_threshold`, as the Tab5 does:

```yaml
binary_sensor:
  - platform: analog_threshold
    name: "Battery Charging"
    device_class: battery_charging
    sensor_id: my_battery_current
    threshold:
      upper: 0.05   # amps into the battery: charging
      lower: 0.02   # and back under this: not charging
```

## A battery on a screen of your own

A screen from Tessera Screen Manager takes extra hardware in its **Override YAML** (More → Override YAML), which may not
include packages. Put the sensors there directly. This is a CYD with a lithium cell on GPIO35 through two equal
resistors, the same case `tests/fixtures/overrides/cyd-battery.yaml` keeps working:

```yaml
sensor:
  - platform: adc
    id: my_battery_voltage
    name: "Battery Voltage"
    pin: GPIO35
    attenuation: 12db
    samples: 16
    update_interval: 30s
    entity_category: diagnostic
    filters:
      - multiply: 2.0
  - platform: template
    name: "Battery Level"
    device_class: battery
    state_class: measurement
    unit_of_measurement: "%"
    accuracy_decimals: 0
    update_interval: 30s
    lambda: |-
      const float v = id(my_battery_voltage).state;
      if (std::isnan(v)) return {};
      return (v - 3.3f) / (4.2f - 3.3f) * 100.0f;
    filters:
      - clamp:
          min_value: 0
          max_value: 100
```

Save it with **Save & check** and update the screen. When it connects again, the editor offers the battery in its top
bar.

## The M5Stack Tab5

The Tab5 runs on a removable NP-F550 pack: two lithium cells in series, 7.4 V and 2000 mAh (14.8 Wh). M5Stack gives
about six hours from full at half brightness with Wi-Fi on. Its board file measures everything with parts M5Stack put on
the board:

- an **INA226** at I2C address 0x41 in the battery's path: its bus voltage is the pack's voltage, and its current is
  positive while the pack charges, the way M5Stack's own firmware reads it;
- **Battery Level** follows the pack's voltage from 6.0 V (empty) to 8.4 V (full) on a curve;
- **Battery Charging** is on while more than 50 mA flows into the pack and off again under 20 mA: the IP2326 charger
  stops at a full pack and the current falls to about nothing.

The charger only works when the firmware enables it: M5Stack's documentation says the Tab5 does not charge until it has
started. The board file switches it on at boot, together with quick charge and the Wi-Fi chip's power, on the second
I/O expander (docs/TAB5.md).

## Places a change touches

- `components/smart_display/battery_status.h`: Home Assistant's icon rules, "low", and the reading.
- `components/smart_display/header_bar.h` and `page_header.h`: the item and how it is drawn.
- `components/smart_display/runtime_tiles.h`: `find_battery()`, which finds the sensors at boot; `settings_screen.h`:
  the word `battery` in Screen features.
- `packages/core.yaml`: the call at boot, `battery` in the hello, and the charging and alert icons in the status font
  (the level icons are tile icons already).
- `packages/features/battery-voltage.yaml` and `battery-adc.yaml`: the recipe for a voltage.
- `screen_manager/app/core.py` (`BATTERY_*`, `has_battery`), `header_bar.py` and `server.py`; `tools/profiles.py`
  (`battery`) for `boards.json`; `tools/generate_page_rules.py`.
- `web/src/model/topbar.ts`, `TopbarAdd.vue` and `TopbarInspector.vue`; the texts in every language.
- `tests/test_battery_status.cpp`, `tests/test_header_bar.py` and `tests/fixtures/page-conformance.json`.
