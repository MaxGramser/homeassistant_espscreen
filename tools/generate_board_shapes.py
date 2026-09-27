"""Write screen_manager/app/boards.json: what every board looks like, straight from its own YAML.

A board says what its panel is (PANEL_W, PANEL_H, the pixels the glass really has), which LVGL angle lays
that panel out lying down (ROTATION_LANDSCAPE), how a page is divided each way (GRID_COLS x GRID_ROWS lying down,
GRID_COLS_PORTRAIT x GRID_ROWS_PORTRAIT standing up), its density and its look. The manager needs the same numbers
to draw a screen in the editor before it has ever been flashed, so they are worked out here instead of typed a
second time; `--check` fails when the file is out of date, which tools/check.sh runs. A screen that is online
reports its own shape as well (firmware 0.2.80), and that one wins: it knows how it was built and turned.

Every board gets both orientations under `orientations`, and keeps the landscape numbers at the top level, so
everything that only ever knew one shape per board reads the same file as before.

usage: generate_board_shapes.py [--check]
"""
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager' / 'app'))
import alert_layout  # noqa: E402
import font_metrics  # noqa: E402
import profiles  # noqa: E402

OUT = profiles.ROOT / 'screen_manager' / 'app' / 'boards.json'


def orientations(values):
    """{'landscape': ..., 'portrait': ...}: the canvas, the grid and the LVGL angle of each way a board can hang.

    The canvas is the panel turned by that angle, because LVGL turns the picture and the touch together: a quarter
    turn swaps the sides, a half turn keeps them. Standing up is a quarter further than lying down, which is the
    one line that differs between the two builds (LVGL_ROTATION in the board file).

    Square glass has no second way to hang, so its portrait entry is its landscape entry, angle included: choosing
    to stand a square screen up then builds exactly the same firmware instead of turning the picture for nothing.
    """
    panel = (int(values['PANEL_W']), int(values['PANEL_H']))
    angle = int(values['ROTATION_LANDSCAPE']) % 360
    wide = (panel[1], panel[0]) if angle in (90, 270) else panel
    lying = {'width': wide[0], 'height': wide[1],
             'columns': int(values['GRID_COLS']), 'rows': int(values['GRID_ROWS']), 'rotation': angle}
    if wide[0] == wide[1]:
        return {'landscape': lying, 'portrait': dict(lying)}
    return {'landscape': lying,
            'portrait': {'width': wide[1], 'height': wide[0],
                         'columns': int(values['GRID_COLS_PORTRAIT']), 'rows': int(values['GRID_ROWS_PORTRAIT']),
                         'rotation': (angle + 90) % 360}}


def alert_lines(values):
    """The line heights of the alert card's two fonts on this board, which its layout needs (title and subtitle)."""
    core = profiles.CORE.read_text()
    return {'title_line': font_metrics.line_height(profiles.ROOT / font_metrics.font_file(core, 'headline'),
                                                   int(values['FONT_HEADLINE_SIZE'])),
            'line': font_metrics.line_height(profiles.ROOT / font_metrics.font_file(core, 'sublabel_big'),
                                             int(values['FONT_SUBLABEL_BIG_SIZE']))}


STATUSES = ('stable', 'new', 'experimental')


def catalog_of(board, values, lying):
    """What New screen and the screen list say about a board: its entry in boards.yaml, with what its files say.

    The size in inches is the glass's diagonal over its density, the touch controller the platform of its
    touchscreen, and a board that reads a resistive panel asks for a touch calibration on its first start
    (features/resistive-touch.yaml). A choice is a substitution the board file offers, whose first value is the one
    the board file sets; a choice that is not, or an unknown status, stops the build of this file.
    """
    entry = profiles.CATALOG[board]
    for key in ('name', 'model', 'status'):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            raise SystemExit(f'boards.yaml: {board} needs a {key}')
    if entry['status'] not in STATUSES:
        raise SystemExit(f'boards.yaml: {board} status is one of {", ".join(STATUSES)}')
    choices = {}
    for key, options in (entry.get('choices') or {}).items():
        options = [str(option) for option in options or []]
        if key not in values:
            raise SystemExit(f'boards.yaml: {board} offers {key}, which its board file does not have')
        if len(options) < 2 or len(set(options)) != len(options) or options[0] != values[key].strip('"'):
            raise SystemExit(f'boards.yaml: {board} {key} lists the board file\'s own value ({values[key]}) first, '
                             'then at least one other')
        choices[key] = options
    chain = profiles.chain(profiles.BOARDS[board])
    text = '\n'.join(path.read_text() for path in chain)
    touch = re.search(r'(?m)^touchscreen:\n\s*- platform: (\w+)', text)
    return {'order': list(profiles.CATALOG).index(board), 'name': entry['name'].strip(), 'model': entry['model'].strip(),
            'status': entry['status'],
            'inch': round(math.hypot(lying['width'], lying['height']) / float(values['DISPLAY_DPI']), 1),
            'touch': touch[1].upper() if touch else '',
            'calibrate': any(path.name == 'resistive-touch.yaml' for path in chain),
            'choices': choices}


def chip_of(board):
    """The chip a board's firmware is built for, as esptool names it ("ESP32", "ESP32-S3", "ESP32-P4"): the `variant`
    of the `esp32:` block in the board's files. The browser flasher under New screen and Firmware & USB
    compares it with the chip on the USB cable before anything is built, as ESPHome's own dashboard does, and refuses a
    board of another chip. Another block's variant (a P4 board's Wi-Fi co-processor under `esp32_hosted:`) is not it.
    """
    found = None
    for path in profiles.chain(profiles.BOARDS[board]):
        block = re.search(r'(?m)^esp32:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)*)', path.read_text())
        variant = re.search(r'(?m)^[ \t]+variant:[ \t]*"?(\w+)"?', block[1]) if block else None
        if variant:
            found = variant[1].lower()
    if not found or not re.fullmatch(r'esp32\w*', found):
        raise SystemExit(f'{board}: no esp32 variant in its files')
    return 'ESP32' + ('-' + found[5:].upper() if found[5:] else '')


def camera_of(values, side):
    """The pixel box of each picture a board draws, on the glass of one orientation.

    Full screen is that orientation's canvas: a screen standing up wants a picture standing up, and sending it the
    other one would letterbox it into a third of the glass. The alert's picture gets the frame the firmware makes for
    it on that canvas for a camera's 16:9 (screen_alert::layout, firmware 0.2.103+), which alert_layout.py works out
    the same way, from the look, the density and the two fonts of the card. ESP Screens works out the frame for a
    picture of other proportions itself (camera_feed.alert_box), with the line heights written here as `alert`.
    """
    lines = alert_lines(values)
    card = alert_layout.layout(side['width'], side['height'], lines['title_line'], lines['line'], True,
                               round(float(values['DISPLAY_DPI'])), values['LOOK'].strip('"'))
    boxes = {'full': [side['width'], side['height']]}
    # Glass too low for a picture in the alert leaves it out there, and ESP Screens then sends none (camera_feed.box).
    if card.image_w > 0 and card.image_h > 0:
        boxes['thumb'] = [card.image_w, card.image_h]
    return boxes


def shapes():
    """{entry file: shape} for every entry a screen's YAML can include, plus the board names themselves."""
    found = {}
    for board in profiles.BOARDS:
        # What a screen of this board sees: its board file over its look and features over the core's defaults.
        values = profiles.board_values(board)
        both = orientations(values)
        lying = both['landscape']
        shape = {'board': board,
                 # The landscape numbers stay the board's own: a screen that says nothing about itself is taken to
                 # hang the way its board file is written, and that is lying down.
                 'width': lying['width'], 'height': lying['height'],
                 'columns': lying['columns'], 'rows': lying['rows'],
                 'orientations': both,
                 'dpi': round(float(values['DISPLAY_DPI'])), 'look': values['LOOK'].strip('"'),
                 # Whether the backlight takes levels (app 0.2.105): on a board whose backlight is one line, a
                 # brightness percentage is a number that lies, so the settings panel shows a switch instead.
                 'dimmable': values.get('BACKLIGHT_DIMMABLE', 'true').strip('"') != 'false',
                 # Whether the screen can go dark at all (app 0.2.106): the Waveshare's backlight boost browns the
                 # board out when it switches on again, so that board has no standby and no night, and the settings
                 # panel leaves those out as the screen itself does.
                 'can_standby': values.get('CAN_STANDBY', 'true').strip('"') != 'false',
                 # The alert card's two line heights (firmware 0.2.103+): with the canvas, the density and the look they
                 # are what screen_alert::layout needs to size an alert's picture (camera_feed.alert_box).
                 'alert': alert_lines(values),
                 # What New screen offers and the screen list names (boards.yaml with what the board's files say).
                 'catalog': catalog_of(board, values, lying),
                 # The chip it is built for, for the browser flasher's check of the board on the cable.
                 'chip': chip_of(board),
                 # The firmware a screen of this board builds today: the core's version, or the board file's own when
                 # a fix for this board alone went out after it (docs/RELEASING.md, "Firmware for one board"). The
                 # update offer goes by it, so a fix for one board is not an update for every other one.
                 'firmware': values['SCREEN_FIRMWARE_VERSION'].strip('"')}
        # A board that draws camera pictures includes features/camera.yaml, which states the canvas they fill
        # (CAMERA_FULL_*). Without it the board has no camera at all, like the CYD: the manager then refuses a camera
        # tile instead of sending a picture that never arrives.
        if 'CAMERA_FULL_W' in values and 'CAMERA_FULL_H' in values:
            # Each orientation gets the boxes for its own glass, because a picture is shaped for the canvas it lands
            # on; the landscape boxes stay at the top level with the other landscape numbers.
            for side in both.values():
                side['camera'] = camera_of(values, side)
            shape['camera'] = dict(both['landscape']['camera'])
        found[board] = shape
    for entry, board in profiles.ENTRIES.items():
        found[entry] = found[board]
    return dict(sorted(found.items()))


def main():
    text = json.dumps(shapes(), indent=1, sort_keys=True) + '\n'
    if '--check' in sys.argv:
        current = OUT.read_text() if OUT.exists() else ''
        if current != text:
            print(f'{OUT.relative_to(profiles.ROOT)} is out of date; run tools/generate_board_shapes.py')
            return 1
        print(f'{OUT.relative_to(profiles.ROOT)} matches the board files')
        return 0
    OUT.write_text(text)
    print(f'wrote {OUT.relative_to(profiles.ROOT)}: {", ".join(sorted(profiles.BOARDS))}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
