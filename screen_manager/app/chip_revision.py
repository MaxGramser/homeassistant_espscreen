"""The silicon revision of a screen's chip, in the screen's own YAML (docs/CHIP_REVISIONS.md).

A chip family can change its silicon in a way one firmware cannot cross: an ESP32-P4 before revision 3 and one of
revision 3 need different builds, and boards sold under one name, label included, carry either (GitHub #336, #397,
#462). So the app does not guess it from a board: it reads the chip, and writes one fact into the screen's YAML,
`CHIP_REVISION`, ESP-IDF's full revision (major x 100 + minor, "302" for v3.2). The packages decide what a revision
needs (packages/hardware/esp32p4-core.yaml for the P4); this file knows no rule of any chip family, only where the
number comes from. The most certain first:

1. The chip on the USB cable while the app installs: the editor's installer reads it with esptool-js and sends it with
   the request (`chip_revision`), a port on Home Assistant's own machine is read with esptool before the build.
2. A screen that runs says it itself: its "Screen chip" sensor, "ESP32-P4 v3.2" (components/smart_display/chip_revision.h).
3. A screen's Override YAML that sets `engineering_sample: false` by hand, what owners of rev3 boards were told before
   the app read the chip: that line says rev3 as plainly as the chip does.

Nothing known: the YAML keeps what it says, and a YAML without the line builds the board's own default. tests/test_chip_revision.py
proves the readings.
"""
import asyncio
import logging
import re
import sys

import yaml

LOG = logging.getLogger('screen_manager')

KEY = 'CHIP_REVISION'
# The highest number this takes: ESP-IDF's revisions are major x 100 + minor, with both well below 100.
LIMIT = 9999
# The first revision of the ESP32-P4 that a pre-v3 firmware does not boot (CONFIG_ESP32P4_SELECTS_REV_LESS_V3). An
# override that says rev3 without saying which gets this: the widest rev3 build, from v3.0 on, which runs on every v3.x
# until the screen reports its own revision (packages/hardware/esp32p4-core.yaml, CONFIG_ESP32P4_REV_MIN_300).
P4_REV3 = 300
# The "Screen chip" sensor's words: the chip as esptool names it and the revision.
SENSOR = re.compile(r'(ESP32(?:-[A-Z0-9]+)?) v(\d{1,2})\.(\d{1,2})')
# esptool's line on connecting: "Chip type: ESP32-P4 (revision v3.2)" (esptool 5), "Chip is ESP32-P4 (revision v3.2)"
# (esptool 4), which ESPHome's own upload log carries as well.
ESPTOOL = re.compile(r'\(revision v(\d{1,2})\.(\d{1,2})\)')
# How long reading the chip on a USB port of Home Assistant's machine may take before the build goes on without it.
READ_SECONDS = 45


def valid(value):
    """A revision as a whole number, or None: what a request or a YAML hands in, checked before it goes into a YAML."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and re.fullmatch(r'\d{1,4}', value.strip()):
        value = int(value.strip())
    return value if isinstance(value, int) and 0 <= value <= LIMIT else None


def full(major, minor):
    """ESP-IDF's full revision of v<major>.<minor>."""
    return int(major) * 100 + int(minor)


def from_sensor(text):
    """The revision a screen's "Screen chip" sensor says ("ESP32-P4 v3.2" -> 302), or None ("unknown", older firmware)."""
    match = SENSOR.fullmatch(text.strip()) if isinstance(text, str) else None
    return full(match.group(2), match.group(3)) if match else None


def from_esptool(text):
    """The revision in esptool's output, or None when it found no chip."""
    match = ESPTOOL.search(text or '')
    return full(match.group(1), match.group(2)) if match else None


def from_override(text):
    """What a screen's Override YAML says about its chip: P4_REV3 when it sets `engineering_sample: false`, the hand-made
    rev3 switch of an ESP32-P4 (only the P4 has it). None for anything else, which says nothing about the chip."""
    try:
        data = yaml.safe_load(text) if isinstance(text, str) else None
    except yaml.YAMLError:
        return None
    esp32 = data.get('esp32') if isinstance(data, dict) else None
    return P4_REV3 if isinstance(esp32, dict) and esp32.get('engineering_sample') is False else None


async def read_usb(port, python=sys.executable):
    """The revision of the chip on a USB port of Home Assistant's machine, read with esptool (the one ESPHome brings),
    or None when it does not answer in time. The chip is reset into its download mode and back, as an upload does."""
    try:
        process = await asyncio.create_subprocess_exec(python, '-m', 'esptool', '--port', port, 'chip-id',
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    except OSError as error:
        LOG.warning('Could not read the chip on %s: %s', port, error)
        return None
    try:
        out, _ = await asyncio.wait_for(process.communicate(), READ_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        LOG.warning('The chip on %s did not answer within %d s; the build goes on without its revision', port, READ_SECONDS)
        return None
    revision = from_esptool(out.decode('utf-8', 'replace'))
    if revision is None:
        LOG.warning('esptool found no chip revision on %s', port)
    return revision


def known(screen, override_text):
    """What the app knows of a screen's chip without a cable: its own sensor, else its Override YAML. None for nothing."""
    revision = from_sensor((screen or {}).get('chip'))
    return revision if revision is not None else from_override(override_text)
