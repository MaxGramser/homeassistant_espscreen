# Buttons and sensors on spare pins

Every screen is an ESPHome device, so you can add something wired to one of its free pins: a push button on the wall,
a temperature sensor, a motion sensor. Tessera doesn't set these up. A board's profile only touches the pins its
display, touch and backlight use. You add your own hardware to the screen's **Override YAML**, the small file of its
own that loads after the shared package and stays in place through every update (docs/EASY_SETUP.md,
"Hardware-specific YAML overrides").

What you add shows up in Home Assistant as an entity of the screen's device, next to **Auto standby** and **Wifi Signal**. From there it
works like any other entity: in automations, on a dashboard, and as a tile on this screen or another one.

The Tessera manual has the same recipes with wiring drawings, plus a motion sensor and a relay:
[Buttons, sensors and other hardware](https://tessera-maxgramser.on-forge.com/docs/extra-hardware).

## How to add it

1. Wire the part to a free pin (see "Which pins are free" below), with the screen unplugged.
2. In Tessera, open the screen, press `···` and choose **Override YAML** (advanced).
3. Paste the snippet and change the pin, the names and the entity ids to match your setup. If the file already has
   something in it, add the new blocks next to it. Each key (`binary_sensor:`, `sensor:`, ...) appears only once.
4. Press **Save & check**. ESPHome checks the whole profile, and a pin that is taken or a typo shows up here, before
   anything is built. The full log is under **Firmware & USB**.
5. Press **Update firmware**. The screen builds and installs over Wi-Fi, no USB cable needed.

## Which pins are free

A pin the board's profile uses is taken. Those are the pins in `packages/boards/<board>.yaml` and in the hardware
file it includes from `packages/hardware/`. Reusing one breaks the display, the touch or the backlight. A board's own
doc in docs/ names its spare pins where they are known.

On the CYD (ESP32-2432S028), the two small connectors carry these:

| Connector | Pins | Use |
|---|---|---|
| CN1 | GND, GPIO22, GPIO27, 3.3V | free: buttons, a one-wire sensor, anything that needs an input or an output |
| P3 | GND, GPIO35, GPIO22, GPIO21 | GPIO35 is input only and has no internal pull-up: it needs a resistor to 3.3V. GPIO21 drives the backlight: leave it alone |

GPIO22 appears on both connectors, so it is one pin, not two.

On any ESP32 board, keep in mind:

- GPIO34 to GPIO39 on the classic ESP32 are input only, without internal pull-ups.
- Strapping pins decide how the chip starts. Something that pulls one high or low at power-on can keep the screen from
  booting: GPIO0, GPIO2, GPIO5, GPIO12 and GPIO15 on the classic ESP32, GPIO0, GPIO3, GPIO45 and GPIO46 on the
  ESP32-S3.

## A wall button that switches a light

Wire a push button between the pin and GND. The pin's internal pull-up holds it high, a press pulls it low.

```yaml
binary_sensor:
  - platform: gpio
    id: hallway_button
    name: "Hallway button"
    pin:
      number: GPIO22
      mode:
        input: true
        pullup: true
      inverted: true
    filters:
      - delayed_on_off: 30ms
    on_press:
      - homeassistant.action:
          action: light.toggle
          data:
            entity_id: light.hallway
```

- `inverted: true` makes the entity read **On** while the button is held down.
- `delayed_on_off: 30ms` debounces it: the contacts of a button bounce for a few milliseconds, and without the filter
  one press can toggle the light twice.
- `on_press` asks Home Assistant to toggle the light. The screen needs **Allow the device to perform Home Assistant
  actions**. Tessera turns that on for every screen it knows (docs/EASY_SETUP.md, chapter 3); in Home Assistant it
  is the ESPHome integration's **Configure**.
- A second button is a second entry under `binary_sensor:`, with its own `id`, `name` and pin.
- For a rocker switch that stays where you flip it, write `on_state:` instead of `on_press:`, so every flip toggles
  the light whichever way it goes.

You can also leave out `on_press` and switch the light in a Home Assistant automation on the button's entity. Either
way the button only works while Home Assistant is running, because the screen asks Home Assistant to switch the light.

## A DS18B20 temperature sensor

Wire the sensor's data line to the pin, and its other two wires to 3.3V and GND. Put a 4.7 kΩ resistor between data
and 3.3V. Some modules sold for the DS18B20 have that resistor on board already.

```yaml
one_wire:
  - platform: gpio
    pin: GPIO27

sensor:
  - platform: dallas_temp
    name: "Temperature"
    update_interval: 60s
```

- The entity takes the screen's name in front, for example "Hallway screen Temperature".
- With more than one sensor on the same wire, each needs its own `address:`. The screen's log lists the addresses it
  finds when it starts.
- The screen's board and backlight get warm. A sensor on the board, or inside the case, reads a few degrees too high.
  Put it on a short cable outside the case.

## Room in the firmware

A button or a sensor costs a few kilobytes of flash. That's fine on every board, the CYD and the Hosyond with their
4 MB too, but don't add whole libraries of extras to a 4 MB board. If the firmware no longer fits, the build says so
and the screen keeps the firmware it has.
