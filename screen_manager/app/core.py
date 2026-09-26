"""Pure validation, firmware generation and bounded display protocol."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
import re
import secrets

from i18n import english, screen_t, t
import tile_icons

DOMAINS = frozenset('light switch input_boolean scene script climate vacuum fan cover sensor binary_sensor input_select select number input_number weather media_player button input_button sun timer person screen camera image alarm_control_panel'.split())
# Built-in cards without a Home Assistant entity; firmware 0.2.14+ renders them. The names in English: a screen gets them in
# its language and the editor in its own (builtin_name, app 0.2.90).
BUILTIN = {'screen.clock': 'Clock', 'screen.settings': 'Settings', **{f'screen.page_{n}': f'Go to page {n}' for n in range(1, 9)}}
# A navigation tile (firmware 0.2.62+): screen.page_<n> goes to page n. Firmware 0.2.65+ takes the same one on several
# pages (a "Back to page 1" on every page); every other entity still appears once on a screen.
PAGE_TILE = 'screen.page_'
PAGE_TILE_REPEAT_MIN_FIRMWARE = (0, 2, 65)

def page_target(entity):
    """The page a navigation tile opens, counted from one; 0 for any other entity."""
    return int(entity[len(PAGE_TILE):]) if isinstance(entity, str) and entity in BUILTIN and entity.startswith(PAGE_TILE) else 0

def builtin_name(entity, text=screen_t):
    """A built-in card's name in the screens' language, for the tile on the screen; `text=t` gives the editor's."""
    page = page_target(entity)
    if page:
        return text('addon.screen.builtin.page', page=page)
    # The settings tile is named like the settings page it opens.
    return text('screen.settings.title' if entity == 'screen.settings' else 'addon.screen.builtin.clock')
NEW_DOMAINS = frozenset('sun timer person screen'.split())
# A camera or an image entity opens full screen on a Guition with firmware 0.2.57+ (camera_feed.py).
CAMERA_DOMAINS = frozenset(('camera', 'image'))
CAMERA_MIN_FIRMWARE = (0, 2, 57)
# A live picture on a camera tile ("display": "live", app 0.2.91): firmware from here asks for the page's strip.
LIVE_MIN_FIRMWARE = (0, 2, 77)
LIVE_REFRESH = (15, 30)  # the paces a live tile may choose, in seconds; the first is the default
# A media tile's album cover in the icon's place ("display": "cover", app 0.2.92): the same strip, firmware from here.
COVER_TILE_MIN_FIRMWARE = (0, 2, 78)
# The calm dial and the flip clock (firmware 0.3.6+). An older screen draws either as the digital clock, so a layout
# with one is sent as it is; the editor says so.
CLOCK_FACES_MIN_FIRMWARE = (0, 3, 6)
CLOCK_DEFAULT_DISPLAY = 'dial'

# The media card with its cover (app 0.2.77): firmware from here draws it and asks for the cover.
COVER_MIN_FIRMWARE = (0, 2, 64)
# One tile per slot, a tile over the whole page and the screen.page tile (firmware 0.2.62+). How many tiles a
# screen holds follows from its grid (Grid.max_tiles below): 48 on the boards that shipped first.
LEGACY_MAX_TILES = 20
FULL_PAGE_MIN_FIRMWARE = (0, 2, 62)
# Twenty tiles from firmware 0.2.7, ten before.
TWENTY_TILES_MIN_FIRMWARE = (0, 2, 7)
FIRST_MAX_TILES = 10
REPO = 'https://github.com/MaxGramser/homeassistant_espscreen'
# The branch a screen's YAML builds its board package from. Which boards there are is boards.json's (BOARD_KEYS).
REF = 'main'
# Firmware shipped with this app release; screens below it get an update offer.
FIRMWARE_VERSION = '0.3.6'
# The Auto standby switch a screen offers Home Assistant automations.
AUTO_STANDBY_MIN_FIRMWARE = '0.2.41'
# The settings page the screen opens itself, and the screen.settings tile that opens it.
SETTINGS_PAGE_MIN_FIRMWARE = '0.2.44'
# The Wake and Sleep buttons a screen offers Home Assistant automations.
WAKE_SLEEP_MIN_FIRMWARE = '0.2.45'
# Every screen setting as an entity of the screen, which owns them (see SETTING_ENTITIES).
SETTING_ENTITIES_MIN_FIRMWARE = '0.2.49'
# Dark mode: the screen's dark look, a setting and entity of its own (components/smart_display/theme.h).
DARK_MODE_MIN_FIRMWARE = '0.2.54'
# Page buttons: the Previous and Next bar under the tiles, a setting and entity of its own; off, the tiles take its room.
PAGE_BUTTONS_MIN_FIRMWARE = '0.2.69'
# The house at the far left of the top bar, and a swipe up from the bottom edge: both go back to page 1.
HOME_BUTTON_MIN_FIRMWARE = '0.2.100'
# Open a page from Home Assistant (esphome.<node>_show_page), the way a Go to page tile does.
SHOW_PAGE_MIN_FIRMWARE = '0.2.87'
# An alarm panel as a tile with its card and keypad (components/smart_display/alarm_panel.h); older firmware refuses the
# domain, so a layout with one waits for the update.
ALARM_MIN_FIRMWARE = (0, 3, 3)
ATTRS = frozenset('brightness percentage current_position current_tilt_position current_temperature temperature current_humidity min_temp max_temp target_temp_step supported_color_modes hvac_modes hvac_action hs_color color_temp_kelvin min_color_temp_kelvin max_color_temp_kelvin fan_speed_list unit_of_measurement battery_level fan_speed volume_level is_volume_muted media_title options min max step temperature_unit supported_features device_class next_rising next_setting finishes_at duration remaining humidity wind_speed wind_speed_unit apparent_temperature fan_modes swing_modes fan_mode swing_mode effect code_format code_arm_required changed_by'.split())
# Attributes whose boolean value the screen needs; every other bool stays behind.
BOOL_ATTRS = frozenset(['is_volume_muted', 'code_arm_required'])


# The labels in English, as the Claude skill writes them; the editor gets them in its language (backgrounds()).
TILE_BACKGROUNDS = {
    'auto': {'label': 'Default', 'color': None},
    # No card behind the tile: contents keep their size and place on the screen background.
    'none': {'label': 'None', 'color': None},
    'red': {'label': 'Red', 'color': '#FADADD'},
    'orange': {'label': 'Orange', 'color': '#FFE1C6'},
    'yellow': {'label': 'Yellow', 'color': '#FFF0C2'},
    'green': {'label': 'Green', 'color': '#D9EEDC'},
    'mint': {'label': 'Mint', 'color': '#D5F0EA'},
    'blue': {'label': 'Blue', 'color': '#D9EAFB'},
    'purple': {'label': 'Purple', 'color': '#E9DDF5'},
    'pink': {'label': 'Pink', 'color': '#F7DDEC'},
    'gray': {'label': 'Gray', 'color': '#E5E7EB'},
}

def backgrounds():
    """TILE_BACKGROUNDS with their labels in the editor's language (app 0.2.90)."""
    return {name: {**item, 'label': t(f'addon.labels.backgrounds.{name}')} for name, item in TILE_BACKGROUNDS.items()}

# Display modes per domain; everything else offers standard and watch (large value).
DISPLAYS = {'weather': ('standard', 'watch', 'forecast'), 'sensor': ('standard', 'watch', 'graph'), 'screen': ('digital', 'analog', 'dial', 'flip'), 'sun': ('standard', 'watch', 'sunpath'),
            'camera': ('standard', 'live'), 'image': ('standard', 'live'), 'media_player': ('standard', 'watch', 'cover')}
# A live picture on a 1x2 or 2x2 tile fills the card (app 0.3.8, firmware 0.3.3): cut to fill it or whole on black, with
# its name on it or nothing. The first choice of each is the default and is never stored.
PICTURE_OPTIONS = {'fit': ('fill', 'contain'), 'overlay': ('name', 'none')}
# Displays that only work on a double-width card.
WIDE_ONLY = ('forecast', 'sunpath')

# ----- The grid of a screen's pages -----
# A page is a grid of cells, and each screen has its own: two columns of three on the boards that shipped first,
# three by three on a 800 x 480 panel, whatever a later board's glass asks for. A tile's `slot` is its absolute
# cell (page * cells + row * columns + column); a wide tile starts in a column that has a cell to its right and
# covers both; a full tile (firmware 0.2.62+) starts a page and covers every cell of it. Empty cells are allowed.
#
# The rules are the firmware's (components/smart_display/runtime_model.h): at most eight pages, and never more
# than 64 tiles on one screen (one dirty bit each), so a page of nine cells gives seven pages. Everything that
# counts cells, rows, pages or tiles goes through the screen's Grid (`grid_of(screen)`); DEFAULT_GRID is the two
# by three of the first boards, which is also what every layout stored before app 0.2.94 was made on.
FIRMWARE_MAX_PAGES = 8
FIRMWARE_MAX_TILES = 64

class Grid:
    __slots__ = ('columns', 'rows')

    def __init__(self, columns=2, rows=3):
        columns, rows = int(columns), int(rows)
        if columns < 1 or rows < 1 or columns * rows > FIRMWARE_MAX_TILES:
            raise ValueError(f'no screen holds a page of {columns} x {rows} cells')
        self.columns, self.rows = columns, rows

    def __eq__(self, other):
        return isinstance(other, Grid) and (self.columns, self.rows) == (other.columns, other.rows)

    def __hash__(self):
        return hash((self.columns, self.rows))

    def __repr__(self):
        return f'Grid({self.columns}x{self.rows})'

    @property
    def slots(self):
        """The cells of one page."""
        return self.columns * self.rows

    @property
    def pages(self):
        return min(FIRMWARE_MAX_PAGES, FIRMWARE_MAX_TILES // self.slots)

    @property
    def max_slots(self):
        return self.pages * self.slots

    max_tiles = max_slots

    @property
    def wide_span(self):
        """A wide tile takes two cells, or the one there is on a single-column screen."""
        return min(2, self.columns)

    def dimensions(self, size):
        """Width and height in grid cells, independent of the tile's content."""
        if size == 'full': return self.columns, self.rows
        if size in ('wide', True): return self.wide_span, 1
        if size == 'tall': return 1, 2
        if size == 'square': return 2, 2
        return 1, 1

    def cells(self, size):
        columns, rows = self.dimensions(size)
        return columns * rows

    def fits(self, slot, size):
        columns, rows = self.dimensions(size)
        return (type(slot) is int and 0 <= slot < self.max_slots
                and (size != 'full' or slot % self.slots == 0)
                and slot % self.columns + columns <= self.columns
                and slot % self.slots // self.columns + rows <= self.rows)

    def page_start(self, slot):
        return slot - slot % self.slots

    def row_start(self, slot):
        return slot - slot % self.columns

    def wide_fits(self, slot):
        """Whether a wide tile may start here: a cell beside it in the same row, or a single column."""
        return self.columns == 1 or slot % self.columns <= self.columns - 2

    def footprint(self, slot, size):
        """The cells a tile of `size` takes from `slot` (True still means wide)."""
        if size == 'full':
            return tuple(range(self.page_start(slot), self.page_start(slot) + self.slots))
        columns, rows = self.dimensions(size)
        return tuple(slot + row * self.columns + column for row in range(rows) for column in range(columns))

    def pack(self, tiles):
        """In-order packing, the rule before explicit positions and what firmware without `slots` still does:
        fill left to right, a wide card that would straddle two rows starts the next, a full one a new page."""
        position, slots, taken = 0, [], set()
        for tile in tiles:
            size = tile_size(tile)
            columns, rows = self.dimensions(size)
            if columns > self.columns or rows > self.rows:
                raise ValueError(t('addon.errors.layout.eight_pages'))
            while not self.fits(position % self.slots, size) or taken.intersection(self.footprint(position, size)):
                position += 1
            slots.append(position)
            taken.update(self.footprint(position, size))
            position += self.dimensions(size)[0]
        return slots

    def holds(self, tiles):
        """Whether every stored position is a cell of this grid that a tile of its size may start in."""
        for tile in tiles:
            slot, size = tile.get('slot'), tile_size(tile)
            if type(slot) is not int or not 0 <= slot < self.max_slots:
                return False
            if not self.fits(slot, size):
                return False
        return True

    def page_of(self, slot):
        return slot // self.slots

    def row_of(self, slot):
        """The row within its page, counted from 1 as people do."""
        return slot % self.slots // self.columns + 1

    def column_of(self, slot):
        """The column, counted from 1."""
        return slot % self.columns + 1

    def column_word(self, slot):
        """The column as the layout sensor names it: left and right on a two-column screen, the number elsewhere."""
        return ('left', 'right')[slot % 2] if self.columns == 2 else self.column_of(slot)

    def slot_at(self, page, row, column):
        """The cell at `row` and `column` of `page`, all three counted from the first."""
        return page * self.slots + (row - 1) * self.columns + (column - 1)

DEFAULT_GRID = Grid(2, 3)
# The first boards' numbers, for what has no screen in hand (the store, a test); anything per screen asks its grid.
SLOTS_PER_PAGE = DEFAULT_GRID.slots
MAX_PAGES = DEFAULT_GRID.pages
MAX_SLOTS = DEFAULT_GRID.max_slots
MAX_TILES = DEFAULT_GRID.max_tiles

TILE_SIZES_ON_SCREEN = ('single', 'wide', 'tall', 'square', 'full')

def tile_size(tile):
    """The symbolic presentation size; dimensions are resolved by the screen's grid."""
    size = tile.get('options', {}).get('size', 'single')
    return size if size in TILE_SIZES_ON_SCREEN else 'single'

def is_wide(tile):
    """Double width or the whole page: the card spans two columns."""
    return tile_size(tile) != 'single'

def is_full(tile):
    return tile_size(tile) == 'full'

def cells_of(size, grid=DEFAULT_GRID):
    return grid.cells(size)

def page_start(slot, grid=DEFAULT_GRID):
    return grid.page_start(slot)

def footprint(slot, size, grid=DEFAULT_GRID):
    """The cells a tile of `size` takes from `slot` (True still means wide)."""
    return grid.footprint(slot, size)

def pack_slots(tiles, grid=DEFAULT_GRID):
    """In-order packing on the screen's grid (Grid.pack)."""
    return grid.pack(tiles)

def packed_slots(tiles, grid=DEFAULT_GRID):
    """pack_slots for tiles that must fit on the screen: ValueError when the packing runs past the last page (48
    tiles with one of them double-width, or 43 with one full-page tile, on a two by three screen), before a save or
    an event stores it (app 0.2.78; the save used to fail later with "Invalid tile position")."""
    slots = grid.pack(tiles)
    if any(grid.footprint(slot, tile_size(tile))[-1] >= grid.max_slots for tile, slot in zip(tiles, slots)):
        raise ValueError(t('addon.errors.layout.eight_pages'))
    return slots

def has_gaps(tiles, grid=DEFAULT_GRID):
    """True when the stored positions differ from the in-order packing, so firmware
    before 0.2.26 (which ignores `slots`) would show another arrangement."""
    return [t.get('slot') for t in tiles] != grid.pack(tiles)

# Direct controls on the right half of a double-width card (firmware 0.2.19+), like
# Home Assistant's own entity rows. The first choice is what a wide card shows
# when the tile has no explicit choice; 'none' keeps the plain card. The labels in English,
# as the Claude skill writes them; the editor gets them in its language (controls_catalogue).
CONTROLS = {
    'climate': (('setpoint', 'Temperature − / +'), ('mode', 'Mode keys'), ('setpoint_mode', 'Temperature − / + and mode keys')),
    'switch': (('toggle', 'On/off switch'),),
    'input_boolean': (('toggle', 'On/off switch'),),
    'light': (('toggle', 'On/off switch'), ('brightness', 'Brightness slider')),
    'fan': (('toggle', 'On/off switch'), ('speed', 'Speed slider')),
    'vacuum': (('buttons', 'Start, stop, dock'),),
    'cover': (('buttons', 'Open, stop, close'), ('position', 'Position slider'),
              ('tilt', 'Slat tilt'), ('buttons_tilt', 'Open, stop, close and slat tilt'),
              ('position_tilt', 'Position and slat tilt')),
    'media_player': (('volume', 'Volume and mute'), ('playback', 'Previous, play/pause, next')),
    'number': (('stepper', 'Value − / +'), ('slider', 'Slider')),
    'input_number': (('stepper', 'Value − / +'), ('slider', 'Slider')),
    'select': (('stepper', 'Previous / next choice'),),
    'input_select': (('stepper', 'Previous / next choice'),),
    'timer': (('buttons', 'Start/pause and cancel'),),
    'scene': (('run', 'Activate button'),),
    'script': (('run', 'Run button'),),
    'button': (('run', 'Press button'),),
    'input_button': (('run', 'Press button'),),
}

def controls_catalogue():
    """Editor choices per domain: the default first, then 'none'; labels in the editor's language (app 0.2.90)."""
    return {domain: {'default': choices[0][0], 'choices': [{'key': key, 'label': t(f'addon.labels.controls.{domain}.{key}')} for key, _ in choices]
                     + [{'key': 'none', 'label': t('addon.labels.controls.none')}]}
            for domain, choices in CONTROLS.items()}

def resolve_controls(tile):
    """Control set a card shows on the screen, or None: only wide cards in the standard layout have room for one."""
    options = tile.get('options', {})
    domain = tile['entity'].split('.')[0]
    # The album cover in the icon's place (app 0.2.92) is the standard layout with a picture: the controls stay.
    if domain not in CONTROLS or options.get('size') not in ('wide', 'tall', 'square', 'full') or options.get('display', 'standard') not in ('standard', 'cover') or options.get('inline') == 'slider':
        return None
    # A full-page card is one big button unless a control was chosen for it; a wide card shows its usual one.
    choice = options.get('controls', 'none' if options.get('size') in ('tall', 'full') else CONTROLS[domain][0][0])
    if domain == 'cover' and options.get('size') == 'wide':
        choice = 'none' if choice == 'tilt' else choice.removesuffix('_tilt')
    # A card one row high has room for one group: the setpoint (firmware 0.3.1 draws both on 1 x 2, 2 x 2 and full).
    if choice == 'setpoint_mode' and options.get('size') == 'wide':
        choice = 'setpoint'
    return None if choice == 'none' else choice

# Diagnostic entities every ESP Screens firmware exposes; the manager watches them for screens.
# Firmware built before the English translation still registers the Dutch originals, so both
# forms are recognised until every board has been reflashed with an English `name:`.
NAME_TILE_SETTINGS = ('Tile settings', 'Tegelinstellingen')
NAME_SCREEN_FIRMWARE = ('Screen firmware', 'Schermfirmware')
NAME_GUITION_TYPE = ('Guition screen type', 'Guition schermtype')
NAME_DEVICE_NAME = ('Device name', 'Apparaatnaam')
NAME_IP_ADDRESS = ('IP address', 'IP-adres')
# The language a screen's firmware was built in (firmware 0.2.76+, app 0.2.90); older firmware speaks English.
NAME_SCREEN_LANGUAGE = ('Screen language',)
# The shape of a screen (firmware 0.2.80, app 0.2.94): "800x480 3x2" is its canvas and the grid of cells a page
# holds. Firmware from before it says nothing, and then the board it was built for decides (LAYOUTS below).
NAME_SCREEN_LAYOUT = ('Screen layout',)
# Which board a screen is (firmware 0.2.80, app 0.2.94): the key of its file in packages/boards, the same key
# boards.json is written under. Firmware from before it says nothing, and then the Guition's own sensor or the
# YAML the screen is built from has to tell (board_of below).
NAME_SCREEN_BOARD = ('Screen board',)
# What a screen can do with its backlight (firmware 0.2.99, app 0.2.120): "dimmable", "standby", both, or "none".
# Firmware from before it says nothing, and then the board's own row in boards.json decides (dimmable/can_standby below).
NAME_SCREEN_FEATURES = ('Screen features',)
SCREEN_ENTITY_NAMES = frozenset(NAME_TILE_SETTINGS + NAME_SCREEN_FIRMWARE + NAME_GUITION_TYPE + NAME_DEVICE_NAME + NAME_IP_ADDRESS
                                + NAME_SCREEN_LANGUAGE + NAME_SCREEN_LAYOUT + NAME_SCREEN_BOARD + NAME_SCREEN_FEATURES)

# What a board looks like: the glass it draws on and the cells of one page, for each way the board can hang. These
# come straight from the board files (tools/generate_board_shapes.py writes boards.json from PANEL_W, GRID_COLS and
# the rest), so the numbers live in one place: the YAML a screen is built from. A screen that is online reports its
# own shape as well (firmware 0.2.80) and that one wins, because it knows how it was built and turned.
def _board_shapes():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'boards.json'), encoding='utf-8') as file:
            return json.load(file)
    except (OSError, ValueError):
        return {}
SHAPES = _board_shapes()
# The boards New screen offers, in the catalog's order (boards.yaml, through boards.json): the entries keyed by a
# board's own word, not the entry files that share its shape.
BOARD_KEYS = tuple(sorted((board for board, shape in SHAPES.items() if shape.get('board') == board),
                          key=lambda board: SHAPES[board].get('catalog', {}).get('order', len(SHAPES))))
DEFAULT_SHAPE = SHAPES.get('cyd', {'width': 320, 'height': 240, 'columns': 2, 'rows': 3})

# The two ways a screen can hang (app 0.2.107). Which one it is, is chosen when the screen is built: the canvas, the
# grid and every size on it follow from the angle LVGL draws at, so it is not something a screen can be told later.
ORIENTATIONS = ('landscape', 'portrait')

def board_shape(board, orientation=None):
    """A board's shape the way the screen hangs: its entry with the width, the height and the grid of that
    orientation. The table of both stays out, because it says something about the board and a shape is about one
    screen. Anything but the two words, and a board file from before they existed, reads as lying down."""
    shape = {key: value for key, value in board.items() if key != 'orientations'}
    side = (board.get('orientations') or {}).get(orientation if orientation in ORIENTATIONS else 'landscape')
    if side:
        # The angle is how the board file gets there; what a screen looks like is the canvas and the grid.
        shape.update({key: value for key, value in side.items() if key != 'rotation'})
    return shape

def orientation_shown(board, reported):
    """Which of a board's two orientations a screen is reporting, by the canvas it says it has, or None when that is
    neither of them (a board this app has never heard of, a canvas nothing matches). A screen that is online knows
    better than any YAML here, and what side it is on decides more than the grid: the camera boxes differ too."""
    if not isinstance(reported, dict):
        return None
    for name in ORIENTATIONS:
        side = (board.get('orientations') or {}).get(name) or {}
        if side.get('width') == reported.get('width') and side.get('height') == reported.get('height'):
            return name
    return None

def orientation_at(board, rotation):
    """Which way a board hangs at this LVGL angle. A half turn keeps the canvas and the grid (turns_of offers it on
    any glass), so an angle counts as the orientation it is a half turn away from. Square glass answers lying down
    for every angle, its two orientations being the same thing. Landscape when the angle says nothing, which is what
    a profile without an LVGL_ROTATION line means: the board file's own default."""
    try:
        angle = int(rotation) % 360
    except (TypeError, ValueError):
        return 'landscape'
    for name in ORIENTATIONS:
        side = (board.get('orientations') or {}).get(name) or {}
        if 'rotation' in side and (angle - int(side['rotation'])) % 180 == 0:
            return name
    return 'landscape'

# The text of the "Screen layout" sensor: the canvas, the grid and, since firmware 0.2.80, the density and the look.
SHAPE_TEXT = r'(\d{2,5})x(\d{2,5}) (\d{1,2})x(\d{1,2})(?: (\d{2,4})dpi)?(?: (standard|compact))?'

def parse_shape(text):
    """The screen's own "<width>x<height> <columns>x<rows>", followed since firmware 0.2.80 by its density and its
    look ("800x480 3x3 217dpi standard"); None for anything else. The density and the look are kept when given, so
    a board this app has never heard of still draws right in the editor."""
    match = re.fullmatch(SHAPE_TEXT, str(text or '').strip())
    if not match:
        return None
    width, height, columns, rows = (int(value) for value in match.groups()[:4])
    if not (1 <= columns <= 12 and 1 <= rows <= 12 and columns * rows <= FIRMWARE_MAX_TILES):
        return None
    shape = {'width': width, 'height': height, 'columns': columns, 'rows': rows}
    if match[5]:
        shape['dpi'] = int(match[5])
    if match[6]:
        shape['look'] = match[6]
    return shape

def board_of(screen):
    """Which board a screen is, in the order of what knows best: what it reported itself (firmware 0.2.80, or
    the Guition's own sensor), else the board package the YAML of its profile includes. 'unknown' for a screen
    that says nothing and has no profile here, which is what a screen flashed by hand looks like."""
    if not isinstance(screen, dict):
        return 'unknown'
    board = screen.get('board')
    if board in SHAPES:
        return board
    package = screen.get('package')
    if isinstance(package, str) and package in SHAPES:
        return SHAPES[package].get('board', 'unknown')
    return board or 'unknown'

# ---- what a screen can do
# One row per ability (app 0.2.120): the word a screen reports for it in its "Screen features" sensor, and the key
# boards.json carries for a screen that cannot report yet. Adding an ability is a row here and a line in
# settings_screen::features() on the firmware side; the sensor, the reading of it and the fallback stay as they are.
# Nothing asks about a word that is not in this table, so a screen may report one an older app has never heard of,
# and a word may be retired here without the firmware having to stop sending it. Whether a board draws pictures is
# the obvious next one: it is still read from boards.json alone (camera_feed.BOXES), because the memory for a
# picture is the board's and not this screen's.
FEATURES = {
    # The backlight takes levels, not just lit or dark (app 0.2.105). One board so far says no: the Waveshare's
    # backlight is a single line on an I2C expander, and there a brightness percentage is a number that lies.
    'dimmable': 'dimmable',
    # The screen can go dark and come back (app 0.2.106). The Waveshare's backlight line also enables the boost
    # converter behind its LEDs, and switching that on from a dark screen pulls the 3.3 V rail under the brownout
    # level: measured on 2026-09-21, every wake from a dark standby reset the board or left its I2C bus dead.
    'standby': 'can_standby',
}
# How a screen writes them: lower case words, space separated, or "none" for a screen that can do none of them.
# Wide enough for words this app does not know yet, and bounded so a sensor full of something else is no answer.
FEATURES_TEXT = r'[a-z][a-z0-9_]{0,15}(?: [a-z][a-z0-9_]{0,15}){0,7}'

def features_of(screen):
    """What a screen said it can do, as a set of words, or None when it never said so.

    A screen reports this itself from firmware 0.2.99, because a board can be changed: a Waveshare whose backlight
    was rewired to a PWM pin (docs/WAVESHARE7.md) really does dim, and a table per board would keep saying it cannot.
    None is silence, which is firmware from before that sensor or a screen that is offline, and then the board's own
    row in boards.json decides. "none" is an answer: a screen that can do none of them.
    """
    if not isinstance(screen, dict):
        return None
    words = screen.get('features')
    if not isinstance(words, str) or not re.fullmatch(FEATURES_TEXT, words):
        return None
    return {word for word in words.split() if word != 'none'}

def able(screen, feature):
    """Whether this screen can do `feature` (a key of FEATURES): its own word when it said one, else the board's row
    in boards.json, which is the same fact its firmware was built with (settings_screen::dimmable and can_standby),
    so the settings panel and the screen's own page agree. A board this app has never heard of can do everything,
    which is what every board but one does."""
    words = features_of(screen)
    if words is not None:
        return feature in words
    return bool(SHAPES.get(board_of(screen), {}).get(FEATURES[feature], True))

def dimmable(screen):
    """Whether this screen's backlight takes levels: no normal brightness without it, and standby and night as the
    switch they really are."""
    return able(screen, 'dimmable')

# The settings that only mean something on a screen that can go dark: standby, night (standby with a clock) and
# going back to page 1 when standby starts.
STANDBY_KEYS = ('standby_enabled', 'standby_seconds', 'standby_brightness', 'night_enabled', 'night_start',
                'night_end', 'night_brightness', 'home_on_standby')

def can_standby(screen):
    """Whether this screen can go dark at all: without it there is no standby and no night, on the screen, in Home
    Assistant or in the settings panel, and the editor drops a group that has no rows left."""
    return able(screen, 'standby')

def shape_of(screen):
    """The shape of a screen as the editor needs it: its canvas, the cells of one page, its density, its look and,
    for a board that draws pictures, the camera sizes. What the screen reported itself (firmware 0.2.80+) wins,
    because that is the canvas after its rotation; the board it is (board_of: reported, or the YAML its profile
    builds from) fills in the rest from boards.json, the way that screen was built to hang ('orientation', which
    the manager reads from the profile for a screen that is not online); a screen that says nothing at all is taken
    for the smallest screen there is."""
    if not isinstance(screen, dict):
        return DEFAULT_SHAPE
    board = SHAPES.get(board_of(screen), DEFAULT_SHAPE)
    reported = screen.get('shape')
    reported = reported if isinstance(reported, dict) and reported.get('columns') else None
    # Which way it hangs, in the order of what knows best as well: the canvas the screen reports is one of its
    # board's two, and only when it says nothing does the word from its own profile decide.
    shape = board_shape(board, orientation_shown(board, reported) or screen.get('orientation'))
    if reported:
        shape = {**shape, **reported}
    return shape

def grid_of(screen):
    """The grid of a screen's pages (shape_of), on which every slot of its layout is counted."""
    shape = shape_of(screen)
    try:
        return Grid(shape.get('columns', DEFAULT_GRID.columns), shape.get('rows', DEFAULT_GRID.rows))
    except (TypeError, ValueError):
        return DEFAULT_GRID

def parse_firmware(text):
    """(major, minor, patch) of a screen firmware version such as "0.2.63"; None for anything else. Strict on purpose:
    the firmware reports exactly its project version, and anything with a suffix is not a release."""
    match = re.fullmatch(r'([0-9]+)\.([0-9]+)\.([0-9]+)', text) if isinstance(text, str) else None
    return tuple(int(part) for part in match.groups()) if match else None

# Home Assistant's device registry keeps an ESPHome device's version while the device is offline or restarting. With
# `esphome: project:` (both board profiles) the ESPHome integration writes "<project version> (ESPHome <version>)".
REGISTRY_FIRMWARE = re.compile(r'^([0-9]+\.[0-9]+\.[0-9]+) \(ESPHome ')

def registry_firmware(sw_version):
    """The screen firmware in a device registry sw_version, or None. Firmware built without a project has only
    ESPHome's own version there, which must never read as a screen firmware."""
    match = REGISTRY_FIRMWARE.match(sw_version) if isinstance(sw_version, str) else None
    return match.group(1) if match else None

def known_firmware(sensor, sw_version):
    """The version text discover_screens gives a screen as `firmware_known`: the "Screen firmware" sensor when it holds
    one, else the device registry's; None when neither does."""
    return sensor if parse_firmware(sensor) else registry_firmware(sw_version)

def screen_firmware(screen):
    """The firmware a screen's feature gates go by (app 0.2.78): its "Screen firmware" sensor, or while that has no
    version (the screen is offline or restarting) the one Home Assistant's device registry kept; None when neither
    says. Before, an offline screen counted as firmware 0.0.0 and a save of more than ten tiles was refused."""
    screen = screen or {}
    return parse_firmware(screen.get('firmware_known')) or parse_firmware(screen.get('firmware'))

def version_text(version):
    """"0.2.65" for (0, 2, 65); None for None."""
    return '.'.join(str(part) for part in version) if version else None

def tile_limit(version, grid=DEFAULT_GRID):
    """How many tiles firmware `version` (a tuple, or None when unknown) takes on a screen with this grid: one per
    cell of its pages (firmware 0.2.62+), twenty from 0.2.7, ten before."""
    version = version or (0, 0, 0)
    return grid.max_tiles if version >= FULL_PAGE_MIN_FIRMWARE else LEGACY_MAX_TILES if version >= TWENTY_TILES_MIN_FIRMWARE else FIRST_MAX_TILES

def firmware_features(version, grid=DEFAULT_GRID):
    """What the editor may offer a screen with firmware `version` (a tuple, or None): the tile limit, full-page and
    navigation tiles, and the same navigation tile on several pages."""
    version = version or (0, 0, 0)
    return {'tile_limit': tile_limit(version, grid), 'full_page': version >= FULL_PAGE_MIN_FIRMWARE,
            'page_tiles_repeat': version >= PAGE_TILE_REPEAT_MIN_FIRMWARE}

def entity_slug(name):
    """The end of an entity id Home Assistant derives from an entity name (ASCII names)."""
    return re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')

# An inbox entity id is text.<device>_tile_settings, or text.<device>_tegelinstellingen before firmware 0.2.34.
INBOX_SUFFIXES = tuple('_' + entity_slug(name) for name in NAME_TILE_SETTINGS)

def inbox_prefix(entity):
    """The device part of an inbox entity id ('office_1' for text.office_1_tile_settings), or None."""
    if isinstance(entity, str) and entity.startswith('text.'):
        for suffix in INBOX_SUFFIXES:
            if entity.endswith(suffix) and len(entity) > len('text.') + len(suffix):
                return entity[len('text.'):-len(suffix)]
    return None

def name_clash(node, friendly, taken):
    """Why a new screen cannot carry this name, or None (app 0.2.123).

    Home Assistant cannot tell two devices of one name apart. It names a device's actions after the ESPHome node
    (`esphome.<node>_screen_message`, the one this app hands a layout to) and the start of its entity ids after the
    name the device carries (`switch.<screen>_show_home_button`, what an automation types), so a second screen of
    the same name takes the first one's actions and gets its entities numbered. `taken` is what the screens this
    app knows already carry: `nodes` their ESPHome names, `prefixes` the starts of their entity ids.
    """
    nodes = {str(name).lower() for name in taken.get('nodes') or ()}
    if isinstance(node, str) and node.strip().lower() in nodes:
        return t('addon.errors.firmware.name_taken', name=node.strip())
    prefix = entity_slug(friendly) if isinstance(friendly, str) else ''
    if prefix and prefix in {str(name) for name in taken.get('prefixes') or ()}:
        return t('addon.errors.firmware.friendly_taken', name=friendly.strip())
    return None

def device_prefixes(registry, device_id):
    """Entity id prefixes Home Assistant gave the ESPHome entities of one device: the device name when each
    entity was created. Entities whose name never changed keep the prefix an older inbox id carried."""
    prefixes = set()
    for item in registry:
        name = item.get('original_name')
        if item.get('device_id') != device_id or item.get('platform') != 'esphome' or not isinstance(name, str):
            continue
        object_id, suffix = item['entity_id'].split('.', 1)[-1], '_' + entity_slug(name)
        if len(suffix) > 1 and object_id.endswith(suffix) and len(object_id) > len(suffix):
            prefixes.add(object_id[:-len(suffix)])
    return prefixes

# Additive schema 1 extension. An absent object retains old firmware/YAML defaults.
SETTING_RULES = {
    'standby_enabled': (True, None, None),
    'standby_seconds': (600, 60, 86400),
    'brightness': (100, 5, 100),
    'standby_brightness': (20, 0, 100),
    'night_enabled': (True, None, None),
    'night_start': (1320, 0, 1439),
    'night_end': (420, 0, 1439),
    'night_brightness': (10, 0, 100),
    'show_clock': (True, None, None),
    'clock_24h': (True, None, None),
    'home_on_standby': (False, None, None),
    'swipe_pages': (False, None, None),
    'rotation': (0, 0, 270),
    # Back to page 1 by itself (firmware 0.2.44+): closes an open card and any page but the first
    # after this many seconds without a touch. Older firmware ignores both keys.
    'auto_home': (True, None, None),
    'auto_home_seconds': (120, 30, 3600),
    # The dark look for a screen beside a bed (firmware 0.2.54+). Only a screen that owns its settings has it: it
    # never travels in the layout message.
    'dark_mode': (False, None, None),
    # The Previous and Next bar under the tiles (firmware 0.2.69+); off, the tiles grow into its room. Only a screen
    # that owns its settings has it, like dark_mode.
    'page_buttons': (True, None, None),
    # The house at the far left of the top bar (firmware 0.2.100+), which takes the screen back to page 1. Page 1
    # draws none. Only a screen that owns its settings has it, like dark_mode.
    'home_button': (True, None, None),
}
# Firmware before 0.2.44 accepts a `settings` object with exactly its own eleven keys and refuses any
# other size, so everything added after it travels as its own key in the layout message. Old firmware
# ignores a key it does not know; a new screen with an old add-on keeps what it saved itself.
# docs/SETTINGS.md walks through adding one.
SETTINGS_BESIDE_BLOCK = ('swipe_pages', 'rotation', 'auto_home', 'auto_home_seconds', 'dark_mode', 'page_buttons',
                         'home_button')

# ----- The screen owns its settings (firmware 0.2.49+) -----
# A screen offers every setting as an entity of its own device, and the settings page on the screen, Home
# Assistant and ESP Screens all change them there. ESP Screens reads them from those entities, changes them
# with the entity's own action, and leaves them out of the layout message, so it never overwrites what
# someone changed on the screen or in an automation. A screen without these entities (older firmware) gets
# its settings in the layout message as before. `show_clock` has no entity: the top bar decides the clock.
# key: (Home Assistant domain, the entity's name in the board profiles)
SETTING_ENTITIES = {
    'brightness': ('number', 'Normal brightness'),
    'standby_enabled': ('switch', 'Auto standby'),
    'standby_seconds': ('number', 'Standby after'),
    'standby_brightness': ('number', 'Standby brightness'),
    'night_enabled': ('switch', 'Night mode'),
    'night_start': ('time', 'Night starts'),
    'night_end': ('time', 'Night ends'),
    'night_brightness': ('number', 'Night brightness'),
    'auto_home': ('switch', 'Back to page 1'),
    'auto_home_seconds': ('number', 'Back to page 1 after'),
    'home_on_standby': ('switch', 'Back to page 1 on standby'),
    'swipe_pages': ('switch', 'Swipe between pages'),
    'rotation': ('select', 'Rotation'),
    'dark_mode': ('switch', 'Dark mode'),
    'page_buttons': ('switch', 'Page buttons'),
    'home_button': ('switch', 'Show home button'),
}
# Entities firmware 0.2.49 added; one of them on a device means the screen owns its settings. The first five
# existed before, so they cannot tell.
# The 12 or 24 hours is Settings -> Language & region's since app 0.2.90, for every screen at once: firmware 0.2.76 has no
# "24-hour clock" entity any more, and the one of older firmware is only a marker.
OWNED_SETTINGS_MARKERS = frozenset(('Night mode', 'Night starts', 'Night ends', '24-hour clock', 'Back to page 1',
                                    'Back to page 1 after', 'Back to page 1 on standby', 'Swipe between pages'))
ROTATION_OPTIONS = ('0°', '90°', '180°', '270°')
# Every board turns since this firmware; the Guition turned since 0.2.9.
ROTATION_MIN_FIRMWARE = (0, 2, 80)
# The button that starts a screen's calibration wizard again (app 0.2.117). Only a board whose glass is one you
# calibrate builds it, so the button being on the device is what says this screen can be calibrated at all: no
# board list here, and a board added later needs nothing of this app. A resistive panel reads a voltage off the
# film and has to be told what that voltage means in pixels; a capacitive one reports the point it was touched on.
CALIBRATE_BUTTON = ('button', 'Calibrate touch')

def turns_of(shape):
    """The angles a screen of this shape may be turned to: a half turn on any glass (its canvas, its grid and its size
    table stay), the quarter turns as well on a square one."""
    return (0, 90, 180, 270) if shape.get('width') == shape.get('height') else (0, 180)


def setting_entities(items):
    """{key: entity_id} of a screen's setting entities, from the registry entries of its device (disabled ones
    included), or None when the screen does not own its settings yet (firmware before 0.2.49)."""
    found, owned = {}, False
    for item in items:
        if item.get('platform') != 'esphome':
            continue
        name, domain = item.get('original_name'), item['entity_id'].split('.', 1)[0]
        owned = owned or name in OWNED_SETTINGS_MARKERS
        for key, (wanted_domain, wanted_name) in SETTING_ENTITIES.items():
            if name == wanted_name and domain == wanted_domain and key not in found:
                found[key] = item['entity_id']
    return found if owned else None


def calibrate_entity(items):
    """The entity id of a screen's Calibrate touch button, from the registry entries of its device, or None when
    this screen's panel has no calibration wizard (every capacitive board, and firmware before 0.2.44)."""
    domain, name = CALIBRATE_BUTTON
    for item in items:
        if (item.get('platform') == 'esphome' and item.get('original_name') == name
                and item['entity_id'].split('.', 1)[0] == domain):
            return item['entity_id']
    return None


def setting_from_state(key, state):
    """The value of one setting from its entity's state, or None while Home Assistant has none."""
    value = (state or {}).get('state')
    if not isinstance(value, str) or value in ('', 'unknown', 'unavailable'):
        return None
    domain = SETTING_ENTITIES[key][0]
    try:
        if domain == 'switch':
            return {'on': True, 'off': False}.get(value)
        if domain == 'number':
            number = float(value)
            return int(round(number)) if math.isfinite(number) else None
        if domain == 'time':
            hour, minute = (int(part) for part in value.split(':')[:2])
            return hour * 60 + minute if 0 <= hour < 24 and 0 <= minute < 60 else None
        if domain == 'select':
            return int(value.rstrip('°')) if value in ROTATION_OPTIONS else None
    except ValueError:
        return None
    return None


def setting_action(key, entity, value):
    """(action, data) that gives one setting entity `value`."""
    domain = SETTING_ENTITIES[key][0]
    if domain == 'switch':
        return ('switch.turn_on' if value else 'switch.turn_off'), {'entity_id': entity}
    if domain == 'number':
        return 'number.set_value', {'entity_id': entity, 'value': value}
    if domain == 'time':
        return 'time.set_value', {'entity_id': entity, 'time': f'{value // 60:02d}:{value % 60:02d}:00'}
    return 'select.select_option', {'entity_id': entity, 'option': f'{value}°'}


def validate_settings(data):
    if not isinstance(data, dict) or set(data) - SETTING_RULES.keys():
        raise ValueError(t('addon.errors.settings.unknown'))
    clean = {}
    for key, (default, minimum, maximum) in SETTING_RULES.items():
        value = data.get(key, default)
        if minimum is None:
            valid = type(value) is bool
        else:
            valid = type(value) is int and minimum <= value <= maximum
        if key == "rotation": valid = valid and value in (0, 90, 180, 270)
        if not valid:
            raise ValueError(t('addon.errors.settings.invalid_value', setting=key))
        clean[key] = value
    if max(clean['standby_brightness'], clean['night_brightness']) > clean['brightness']:
        raise ValueError(t('addon.errors.settings.dim_above_normal'))
    return clean

def entity_id(value):
    if not (isinstance(value, str) and len(value) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', value)):
        return False
    return value in BUILTIN if value.startswith('screen.') else value.split('.')[0] in DOMAINS

# ----- Top bar (firmware 0.2.32+): the screen name on the left, up to six items on the right.
# Without a `header` the screen keeps its name and the clock of `show_clock`. -----
HEADER_MIN_FIRMWARE = (0, 2, 32)
# Firmware 0.2.33+ takes a whole message in one API action (esphome.<node>_screen_message)
# and answers a keepalive ping with its layout revision; older firmware gets base64
# chunks in the text inbox and a full repeat every keepalive.
TRANSPORT_MIN_FIRMWARE = (0, 2, 33)
MESSAGE_ACTION = 'screen_message'
HEADER_MAX_ITEMS = 6
# Items the screen draws on its own clock, without Home Assistant; their labels are in the translations (header_bar.catalogue,
# app 0.2.90).
HEADER_BUILTIN = ('clock', 'analog', 'date')
# Only shown, never controlled: the top bar takes these besides every tile domain.
HEADER_ONLY_DOMAINS = frozenset('device_tracker zone lock counter event input_datetime input_text water_heater humidifier'.split())
HEADER_CONTENTS = ('state', 'last_changed')
HEADER_SHOWS = ('always', 'active')

def header_entity(value):
    return (isinstance(value, str) and len(value) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', value) is not None
            and value.split('.')[0] in (DOMAINS - {'screen'} - CAMERA_DOMAINS) | HEADER_ONLY_DOMAINS)

def header_items(layout):
    """Items the top bar shows: the stored ones, else what firmware before the top bar drew (the clock)."""
    if 'header' in layout:
        return layout['header']['items']
    return [{'type': 'clock'}] if layout.get('settings', {}).get('show_clock', True) else []

def validate_header(data):
    if not isinstance(data, dict) or set(data) - {'items'} or not isinstance(data.get('items'), list):
        raise ValueError(t('addon.errors.top_bar.invalid'))
    if len(data['items']) > HEADER_MAX_ITEMS:
        raise ValueError(t('addon.errors.top_bar.full', n=HEADER_MAX_ITEMS))
    items, seen = [], set()
    for item in data['items']:
        kind = item.get('type') if isinstance(item, dict) else None
        if kind in HEADER_BUILTIN:
            if set(item) != {'type'}:
                raise ValueError(t('addon.errors.top_bar.invalid_setting'))
            clean = {'type': kind}
        elif kind == 'entity':
            if set(item) - {'type', 'entity', 'content', 'icon', 'show'}:
                raise ValueError(t('addon.errors.top_bar.unknown_setting'))
            if not header_entity(item.get('entity')):
                raise ValueError(t('addon.errors.top_bar.entity'))
            clean = {'type': 'entity', 'entity': item['entity'], 'content': item.get('content', 'state'),
                     'icon': item.get('icon', 'auto'), 'show': item.get('show', 'always')}
            if clean['content'] not in HEADER_CONTENTS or clean['show'] not in HEADER_SHOWS:
                raise ValueError(t('addon.errors.top_bar.invalid_setting'))
            if not (clean['icon'] in ('auto', 'none') or isinstance(clean['icon'], str) and clean['icon'] in tile_icons.ICONS):
                raise ValueError(t('addon.errors.choose_icon'))
        else:
            raise ValueError(t('addon.errors.top_bar.unknown_item'))
        key = json.dumps(clean, sort_keys=True)
        if key in seen:
            raise ValueError(t('addon.errors.top_bar.twice'))
        seen.add(key)
        items.append(clean)
    return {'items': items}

def repeated_page_tiles(tiles):
    """True when a navigation tile to the same page is on the screen more than once (firmware 0.2.65+)."""
    pages = [tile['entity'] for tile in tiles if page_target(tile['entity'])]
    return len(pages) != len(set(pages))

def min_firmware(layout):
    """Oldest firmware that still accepts this layout; None when any version works."""
    if any(tile.get('options', {}).get('controls') in ('tilt', 'buttons_tilt', 'position_tilt', 'setpoint_mode')
           for tile in layout['tiles']):
        return (0, 3, 1)
    if any(t['entity'].split('.')[0] == 'alarm_control_panel' for t in layout['tiles']):
        return ALARM_MIN_FIRMWARE
    if repeated_page_tiles(layout['tiles']):
        return PAGE_TILE_REPEAT_MIN_FIRMWARE
    if len(layout['tiles']) > LEGACY_MAX_TILES or any(is_full(t) or page_target(t['entity']) for t in layout['tiles']):
        return FULL_PAGE_MIN_FIRMWARE
    if any(t.get('options', {}).get('display') == 'cover' for t in layout['tiles']):
        return COVER_TILE_MIN_FIRMWARE
    if any(t.get('options', {}).get('display') == 'live' for t in layout['tiles']):
        return LIVE_MIN_FIRMWARE
    if any(t['entity'].split('.')[0] in CAMERA_DOMAINS for t in layout['tiles']):
        return CAMERA_MIN_FIRMWARE
    if any(t['entity'] == 'screen.settings' for t in layout['tiles']):
        return (0, 2, 44)
    if any(t.get('options', {}).get('background') == 'none' for t in layout['tiles']):
        return (0, 2, 16)
    if any(t['entity'].split('.')[0] in NEW_DOMAINS for t in layout['tiles']):
        return (0, 2, 14)
    if len(layout['tiles']) > FIRST_MAX_TILES:
        return TWENTY_TILES_MIN_FIRMWARE
    return None

def one_mu(text):
    """The Greek small letter mu (U+03BC), which Home Assistant writes in "μg/m³", as the micro sign (U+00B5) the
    screens have a glyph for. ESPHome's "µs" and most integrations already use the micro sign."""
    return str(text).replace('μ', 'µ')

def short(value, limit):
    return one_mu(value).encode('utf-8')[:limit].decode('utf-8', errors='ignore')

# ----- Tiles from a Home Assistant event (app 0.2.51) -----
# Claude in Home Assistant, or any automation, can put something on a screen without opening the editor:
# it fires one of these events and the app changes that screen's layout, with the same validation and the
# same push. The app answers with TILE_RESULT_EVENT, and publishes every layout as a sensor
# (layout_snapshot) so an assistant can see what is where before it changes anything.
TILE_EVENTS = {'esp_screens_add_tile': 'add', 'esp_screens_remove_tile': 'remove',
               'esp_screens_move_tile': 'move', 'esp_screens_order_tiles': 'order'}
TILE_RESULT_EVENT = 'esp_screens_tile_result'
# What an event may set on a tile: the editor's own settings, with `color` as a friendlier name for the
# pastel background.
TILE_EVENT_OPTIONS = {'size': 'size', 'controls': 'controls', 'display': 'display', 'icon': 'icon',
                      'color': 'background', 'background': 'background', 'tap': 'tap', 'inline': 'inline',
                      'history_hours': 'history_hours', 'refresh': 'refresh', 'fit': 'fit', 'overlay': 'overlay'}
TILE_SIZES = {'full': 'full', 'fullscreen': 'full', 'full screen': 'full', 'full-screen': 'full', 'page': 'full', 'whole page': 'full',
              'wide': 'wide', 'double': 'wide', 'large': 'wide', 'big': 'wide',
              'single': 'single', 'small': 'single', 'normal': 'single'}

def loose(text):
    """A name as people write it: case, spaces, dashes and underscores don't matter."""
    return re.sub(r'[\s_-]+', ' ', str(text or '')).strip().casefold()

def match_screen(screens, wanted, layouts=None):
    """The screen an event means: by its device name, the name Home Assistant shows, or its title.
    With one screen paired, an event doesn't have to name it."""
    listing = ', '.join(sorted(screen['name'] for screen in screens)) or t('addon.errors.events.none_paired')
    if not loose(wanted):
        if len(screens) == 1:
            return screens[0]
        raise ValueError(t('addon.errors.events.name_the_screen', screens=listing))
    key = loose(wanted)
    def names(screen):
        title = (layouts or {}).get(screen['id'], {}).get('title', '')
        return [loose(value) for value in (screen.get('node'), screen.get('name'), screen.get('device'), title, screen.get('area')) if value]
    found = [s for s in screens if key in names(s)] or [s for s in screens if any(key in name for name in names(s))]
    if not found:
        raise ValueError(t('addon.errors.events.no_such_screen', name=wanted, screens=listing))
    if len(found) > 1:
        raise ValueError(t('addon.errors.events.several_screens', name=wanted, screens=', '.join(sorted(s['name'] for s in found))))
    return found[0]

def occupied_cells(tiles, skip=None, grid=DEFAULT_GRID):
    cells = set()
    for tile in tiles:
        if tile is skip or 'slot' not in tile:
            continue
        cells.update(grid.footprint(tile['slot'], tile_size(tile)))
    return cells

def free_slot(tiles, size, page=None, skip=None, grid=DEFAULT_GRID):
    """The first cell a tile of this size fits in, on `page` or anywhere; None when there is no room."""
    cells = occupied_cells(tiles, skip, grid)
    size = 'wide' if size is True else size
    first = 0 if page is None else page * grid.slots
    last = grid.max_slots if page is None else min(grid.max_slots, first + grid.slots)
    for slot in range(first, last):
        if size == 'full' and slot % grid.slots:
            continue
        if not grid.fits(slot, size):
            continue
        if not set(grid.footprint(slot, size)) & cells:
            return slot
    return None

def place_tile(tile, tiles, page=None, slot=None, grid=DEFAULT_GRID):
    """Give a tile its cell: the one asked for when it is free, else the first free one (on `page`)."""
    size = tile_size(tile)
    if slot is not None:
        if size == 'full':
            slot = grid.page_start(slot)
        elif size in ('wide', 'square') and not grid.wide_fits(slot):
            # The last column has no cell beside it: the tile starts one column earlier, in the same row.
            slot -= 1
        if not grid.fits(slot, size):
            raise ValueError(t('addon.errors.layout.position'))
        wanted = set(grid.footprint(slot, size))
        taken = next((t for t in tiles if t is not tile and 'slot' in t and wanted & set(grid.footprint(t['slot'], tile_size(t)))), None)
        if taken:
            raise ValueError(t('addon.errors.events.spot_taken', entity=taken['entity']))
        tile['slot'] = slot
        return
    free = free_slot(tiles, size, page, skip=tile, grid=grid)
    if free is None:
        if size == 'full':
            raise ValueError(t('addon.errors.events.page_not_empty', page=page + 1) if page is not None
                             else t('addon.errors.events.no_empty_page'))
        raise ValueError(t('addon.errors.events.page_full', page=page + 1) if page is not None else t('addon.errors.events.no_room'))
    tile['slot'] = free

def tile_options(data, current=None):
    """The settings an event asks for, on top of what the tile already has. A direct control, a forecast
    and a sun path only fit a double-width card, so they widen the tile themselves."""
    options = dict(current or {})
    for key, name in TILE_EVENT_OPTIONS.items():
        if key not in data or data[key] in (None, ''):
            continue
        value = data[key]
        if name in ('history_hours', 'refresh'):
            options[name] = int(value) if str(value).isdigit() else value
        elif name == 'size':
            options[name] = TILE_SIZES.get(loose(value), str(value))
        else:
            options[name] = str(value).strip()
    # Perform action (app 0.2.67): `action` names Home Assistant's action and `data` its fields; the tap follows.
    if data.get('action') not in (None, ''):
        options['action'] = {'action': str(data['action']).strip(), **({'data': data['data']} if isinstance(data.get('data'), dict) and data['data'] else {})}
        if data.get('tap') in (None, ''):
            options['tap'] = 'action'
    if (options.get('controls', 'none') != 'none' or options.get('display') in WIDE_ONLY) and options.get('size') not in ('tall', 'square', 'full'):
        options['size'] = 'wide'
    return {key: value for key, value in options.items() if value not in (None, '')}

def event_page(data, grid=DEFAULT_GRID):
    """The page an event names, counted from one as people do; None when it doesn't name one."""
    page = data.get('page')
    if page in (None, ''):
        return None
    if not str(page).strip().isdigit() or not 1 <= int(page) <= grid.pages:
        raise ValueError(t('addon.errors.events.page_range', last=grid.pages))
    return int(page) - 1

def event_column(value, grid):
    """The column an event names, counted from 1: a number, or `left` and `right` for the first and the last (and
    `middle` on a screen with an odd number of columns), as the layout sensor names them."""
    word = loose(value)
    if word in ('left', 'first'):
        return 1
    if word in ('right', 'last'):
        return grid.columns
    if word in ('middle', 'centre', 'center') and grid.columns % 2:
        return grid.columns // 2 + 1
    if word.isdigit() and 1 <= int(word) <= grid.columns:
        return int(word)
    raise ValueError(t('addon.errors.events.column') if grid.columns == 2
                     else t('addon.errors.events.column_range', last=grid.columns))

def event_slot(data, page, grid=DEFAULT_GRID):
    """An exact spot: `slot` as the editor counts it, or `row` and `column` within a page."""
    if data.get('slot') not in (None, ''):
        if not str(data['slot']).strip().isdigit() or not 0 <= int(data['slot']) < grid.max_slots:
            raise ValueError(t('addon.errors.events.spot_range', last=grid.max_slots - 1))
        return int(data['slot'])
    if data.get('row') in (None, '') and data.get('column') in (None, ''):
        return None
    if page is None:
        raise ValueError(t('addon.errors.events.row_needs_page'))
    row = str(data.get('row', 1)).strip()
    if not row.isdigit() or not 1 <= int(row) <= grid.rows:
        raise ValueError(t('addon.errors.events.row_range', last=grid.rows))
    column = event_column(data.get('column') or 'left', grid)
    return grid.slot_at(page, int(row), column)

def page_of(tile, grid=DEFAULT_GRID):
    return grid.page_of(tile.get('slot', 0))

def copies_of(tiles, entity):
    """The tiles of one entity in slot order: one, or several copies of a navigation tile (firmware 0.2.65+)."""
    return sorted((tile for tile in tiles if tile['entity'] == entity), key=lambda tile: tile.get('slot', 0))

def pick_copy(found, page=None, slot=None, grid=DEFAULT_GRID):
    """The copy an event means: the one covering `slot`, else the first on `page`, else the first; None when none is
    there. Only a navigation tile has several; an event that doesn't say which acts on the first (app 0.2.78)."""
    if slot is not None:
        return next((tile for tile in found if 'slot' in tile and slot in grid.footprint(tile['slot'], tile_size(tile))), None)
    if page is not None:
        return next((tile for tile in found if page_of(tile, grid) == page), None)
    return found[0] if found else None

def event_source(data, grid=DEFAULT_GRID):
    """(page, slot) of the copy a move event means: `from_page` counted from one, or `from_slot`; None when not named."""
    page = event_page({'page': data.get('from_page')}, grid)
    slot = event_slot({'slot': data.get('from_slot')}, None, grid)
    return (grid.page_of(slot) if slot is not None else page), slot

def not_there(entity, page, slot):
    """The answer to an event that named a place where the tile isn't: "... is not on spot 12" or "... on page 3"."""
    if slot is not None:
        return t('addon.errors.events.not_on_spot', entity=entity, slot=slot)
    return t('addon.errors.events.not_on_page', entity=entity, page=page + 1)

def pack_page(tiles, page, grid=DEFAULT_GRID):
    """Give these tiles the cells of one page, in the order they are in."""
    if len(tiles) > 1 and any(tile_size(tile) == 'full' for tile in tiles):
        raise ValueError(t('addon.errors.events.full_page_alone', page=page + 1))
    for tile, slot in zip(tiles, grid.pack(tiles)):
        if slot >= grid.slots:
            raise ValueError(t('addon.errors.events.does_not_fit', page=page + 1))
        tile['slot'] = page * grid.slots + slot

def run_tile_event(layout, action, data, repeat_pages=False, grid=DEFAULT_GRID):
    """(layout, tile): the layout after one tile event and the tile it placed, changed, moved or removed (None for an
    order), on the screen's own grid. Raises ValueError with the sentence the log and the answer show.

    Only a navigation tile can be on a screen more than once, and only when its firmware takes that (`repeat_pages`,
    0.2.65+). An event then names the copy it means by a spot it covers or by its page: `slot` or `page` for add and
    remove, `from_slot` or `from_page` for a move (whose `slot` and `page` say where to), and each mention in an order
    takes the next copy. Without that it acts on the first copy in spot order (app 0.2.78)."""
    result = {key: value for key, value in layout.items() if key != 'tiles'}
    tiles = [dict(tile) for tile in layout.get('tiles', [])]
    entity = str(data.get('entity') or '').strip()
    page = event_page(data, grid)
    slot = event_slot(data, page, grid)
    if slot is not None and page is None:
        page = grid.page_of(slot)
    if action == 'order':
        wanted = data.get('entities') or data.get('order') or []
        if isinstance(wanted, str):
            wanted = [part.strip() for part in wanted.split(',')]
        wanted = [str(item).strip() for item in wanted if str(item).strip()]
        if not wanted:
            raise ValueError(t('addon.errors.events.order_needed'))
        picked, taken, missing, elsewhere, extra = [], set(), [], [], []
        for name in wanted:
            copies = copies_of(tiles, name)
            here = [tile for tile in copies if page is None or page_of(tile, grid) == page]
            free = [tile for tile in here if id(tile) not in taken]
            if not copies:
                missing.append(name)
            elif not here:
                elsewhere.append(name)
            elif not free:
                extra.append(name)
            else:
                picked.append(free[0])
                taken.add(id(free[0]))
        if missing:
            raise ValueError(t('addon.errors.events.order_not_on_screen', entities=', '.join(missing)))
        if elsewhere:
            raise ValueError(t('addon.errors.events.order_not_on_page', page=page + 1, entities=', '.join(elsewhere)))
        if extra:
            extra = ', '.join(dict.fromkeys(extra))
            raise ValueError(t('addon.errors.events.named_too_often', entities=extra) if page is None
                             else t('addon.errors.events.named_too_often_page', page=page + 1, entities=extra))
        if page is None:
            tiles = picked + [tile for tile in tiles if id(tile) not in taken]
            for tile, cell in zip(tiles, packed_slots(tiles, grid)):
                tile['slot'] = cell
        else:
            pack_page(picked + [tile for tile in tiles if page_of(tile, grid) == page and id(tile) not in taken], page, grid)
        result['tiles'] = tiles
        return result, None
    if not entity:
        raise ValueError(t('addon.errors.events.name_the_entity'))
    copies = copies_of(tiles, entity)
    found = copies[0] if copies else None
    if action == 'remove':
        source_page, source_slot = event_source(data, grid)
        if source_page is None:
            source_page, source_slot = page, slot
        if not found:
            raise ValueError(t('addon.errors.events.not_on_screen', entity=entity))
        found = pick_copy(copies, source_page, source_slot, grid)
        if not found:
            raise ValueError(not_there(entity, source_page, source_slot))
        # The copy that was named itself, not the first tile equal to it.
        tiles = [tile for tile in tiles if tile is not found]
    elif action == 'move':
        if not found:
            raise ValueError(t('addon.errors.events.add_it_first', entity=entity))
        source_page, source_slot = event_source(data, grid)
        found = pick_copy(copies, source_page, source_slot, grid)
        if not found:
            raise ValueError(not_there(entity, source_page, source_slot))
        if page is None and slot is None:
            raise ValueError(t('addon.errors.events.move_where'))
        found.pop('slot', None)
        place_tile(found, tiles, page, slot, grid)
    else:
        if not entity_id(entity) and entity not in BUILTIN:
            raise ValueError(t('addon.errors.events.not_for_a_screen', entity=entity))
        # A navigation tile the firmware takes more than once: the copy on the named spot or page changes, and anywhere
        # else a new copy goes (app 0.2.78). Every other tile, or one without a place, is the one that is there.
        chosen = False
        if copies and repeat_pages and page_target(entity) and (page is not None or slot is not None):
            found = pick_copy(copies, page, slot, grid)
            chosen = found is not None
        was_size, had_slot = tile_size(found) if found else 'single', (found or {}).get('slot')
        options = tile_options(data, (found or {}).get('options'))
        # A new clock starts with the calm dial, as in the editor (app 0.3.12); an older screen draws it as the digital clock.
        if found is None and entity == 'screen.clock' and 'display' not in options:
            options['display'] = CLOCK_DEFAULT_DISPLAY
        tile = found or {'entity': entity, 'name': ''}
        if data.get('name') not in (None, ''):
            tile['name'] = str(data['name']).strip()
        if options:
            tile['options'] = options
        elif found:
            tile.pop('options', None)
        if found is None:
            if len(tiles) >= grid.max_tiles:
                raise ValueError(t('addon.errors.events.screen_full', n=grid.max_tiles))
            tiles.append(tile)
        size = tile_size(tile)
        move = found is None or had_slot is None or (not chosen and (page is not None or slot is not None))
        if not move and size != was_size:
            # A tile that just grew keeps its spot when the cells it needs are free.
            start = grid.page_start(had_slot) if size == 'full' else had_slot - (0 if grid.wide_fits(had_slot) else 1) if size in ('wide', 'square') else had_slot
            move = not grid.fits(start, size) or start != had_slot or bool(set(grid.footprint(start, size)) & occupied_cells([t for t in tiles if t is not tile], grid=grid))
        if move:
            tile.pop('slot', None)
            if size == 'full' and had_slot is not None and ((page is None and slot is None) or chosen):
                # A tile that grew to the whole page stays on its page when the page is otherwise empty.
                try:
                    place_tile(tile, tiles, grid.page_of(had_slot), grid=grid)
                except ValueError:
                    place_tile(tile, tiles, grid=grid)
            elif chosen:
                place_tile(tile, tiles, grid.page_of(had_slot), grid=grid)
            else:
                place_tile(tile, tiles, page, slot, grid)
        found = tile
    result['tiles'] = tiles
    return result, found

def apply_tile_event(layout, action, data, repeat_pages=False, grid=DEFAULT_GRID):
    """The layout after one tile event (run_tile_event without the tile it acted on)."""
    return run_tile_event(layout, action, data, repeat_pages, grid)[0]

def layout_snapshot(screen, layout, grid=None):
    """What a screen shows, for the sensor the app publishes in Home Assistant: the grid of its pages and one entry
    per tile with the page and the spot it is in, so an assistant can read the screen before it changes it. The
    column is `left` or `right` on a two-column screen and the column's number, counted from 1, on any other."""
    grid = grid or grid_of(screen)
    tiles = []
    for tile in sorted(layout.get('tiles', []), key=lambda item: item.get('slot', 0)):
        slot, options = tile.get('slot', 0), tile.get('options', {})
        tiles.append({'entity': tile['entity'], 'name': tile.get('name') or '',
                      'page': grid.page_of(slot) + 1, 'row': grid.row_of(slot), 'column': grid.column_word(slot), 'slot': slot,
                      'size': options.get('size', 'single'), 'controls': options.get('controls', ''),
                      'display': options.get('display', 'standard'), 'tap': options.get('tap', 'auto'),
                      **({'action': options['action']} if options.get('tap') == 'action' and 'action' in options else {}),
                      **({'to_page': page_target(tile['entity'])} if page_target(tile['entity']) else {})})
    return {'screen': screen.get('name', ''), 'node': screen.get('node') or '', 'title': layout.get('title', ''),
            'columns': grid.columns, 'rows': grid.rows, 'max_pages': grid.pages,
            'pages': max([tile['page'] for tile in tiles], default=1), 'tiles': tiles}

# A tap's own action (app 0.2.67): Home Assistant's `domain.action` with data for its fields. It always acts on the tile's
# entity, so the keys that name a target stay out of the data. Text travels as data and every other value as a template
# Home Assistant renders back into that value (ESPHome's action data is text only); both stay small for the CYD.
ACTION_NAME = re.compile(r'[a-z0-9_]+\.[a-z0-9_]+')
ACTION_FIELD = re.compile(r'[a-z0-9_]{1,32}')
TARGET_KEYS = frozenset(('entity_id', 'device_id', 'area_id', 'floor_id', 'label_id'))
ACTION_MAX_FIELDS = 8
ACTION_MAX_VALUE = 400
ACTION_MAX_BYTES = 800

def action_for_screen(value):
    """A tap's own action as the firmware sends it (0.2.58+): {"s": action, "d": [[key, text]], "t": [[key, template]]}."""
    pairs, templates = [], []
    for key, item in (value.get('data') or {}).items():
        if isinstance(item, str):
            pairs.append([key, item])
        else:
            templates.append([key, '{{ %s | from_json }}' % json.dumps(json.dumps(item, ensure_ascii=False, separators=(',', ':'), allow_nan=False), ensure_ascii=False)])
    act = {'s': value['action']}
    if pairs:
        act['d'] = pairs
    if templates:
        act['t'] = templates
    return act

def validate_tap_action(value):
    """The stored form of a tap's own action; ValueError with what to change."""
    if not isinstance(value, dict) or set(value) - {'action', 'data'}:
        raise ValueError(t('addon.errors.tap_action.choose'))
    name, data = value.get('action'), value.get('data', {})
    if not isinstance(name, str) or len(name) > 64 or not ACTION_NAME.fullmatch(name):
        raise ValueError(t('addon.errors.tap_action.choose'))
    if not isinstance(data, dict) or len(data) > ACTION_MAX_FIELDS:
        raise ValueError(t('addon.errors.tap_action.fields_max', n=ACTION_MAX_FIELDS))
    for key in data:
        if not isinstance(key, str) or not ACTION_FIELD.fullmatch(key) or key in TARGET_KEYS:
            raise ValueError(t('addon.errors.tap_action.field_not_allowed', field=key))
    clean = {'action': name, **({'data': dict(data)} if data else {})}
    try:
        act = action_for_screen(clean)
        size = len(json.dumps(act, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode())
    except (TypeError, ValueError):
        raise ValueError(t('addon.errors.tap_action.unsendable')) from None
    if size > ACTION_MAX_BYTES or any(len(item[1].encode()) > ACTION_MAX_VALUE for item in act.get('d', []) + act.get('t', [])):
        raise ValueError(t('addon.errors.tap_action.too_long'))
    return clean

def validate_layout(data, stored=False, grid=DEFAULT_GRID):
    """A layout as the editor, a tile event or the storage gives it. `stored`: loaded from the app's own data, where a
    tile setting this version doesn't know (saved by a newer app) stays as it is instead of stopping the app.

    `grid` is the screen's (grid_of): every position is checked against its cells, as a save or an event does. `None`
    is for when no screen is in hand (the store at start-up, a setting kept beside the tiles of an offline screen):
    the positions are then only kept within what any screen holds, because which grid they were made on is only
    known once the screen is."""
    if not isinstance(data, dict):
        raise ValueError(t('addon.errors.layout.invalid'))
    title, tiles = data.get('title'), data.get('tiles')
    most = grid.max_tiles if grid else FIRMWARE_MAX_TILES
    if not isinstance(title, str) or not title.strip() or len(title.encode()) > 96:
        raise ValueError(t('addon.errors.layout.title'))
    if not isinstance(tiles, list) or len(tiles) > most:
        raise ValueError(t('addon.errors.layout.tiles_max', n=most))
    clean, seen = [], set()
    for tile in tiles:
        if not isinstance(tile, dict) or not entity_id(tile.get('entity')):
            raise ValueError(t('addon.errors.layout.unsupported'))
        # A navigation tile may go on several pages (min_firmware asks 0.2.65 for that); anything else appears once.
        if tile['entity'] in seen and not page_target(tile['entity']):
            raise ValueError(t('addon.errors.layout.once'))
        name = tile.get('name', '')
        if not isinstance(name, str) or len(name.encode()) > 80:
            raise ValueError(t('addon.errors.layout.tile_name'))
        seen.add(tile['entity'])
        item = {'entity': tile['entity'], 'name': name.strip()}
        if stored and 'options' in tile:
            try:
                validate_layout({'title': 'stored', 'tiles': [{'entity': tile['entity'], 'options': tile['options']}]})
            except ValueError:
                # The screen ignores what its firmware doesn't know either.
                item['options'] = dict(tile['options']) if isinstance(tile['options'], dict) else {}
                clean.append(item)
                continue
        if 'options' in tile:
            options = tile['options']
            if not isinstance(options, dict) or set(options) - {'tap', 'display', 'inline', 'history_hours', 'background', 'size', 'icon', 'controls', 'action', 'refresh', 'sub', 'fit', 'overlay'}:
                raise ValueError(t('addon.errors.layout.unknown_settings'))
            # A navigation tile (screen.page_<n>, firmware 0.2.62+) has a name, an icon, a colour and a width; never the page.
            if page_target(tile['entity']):
                if options.get('size') == 'full':
                    raise ValueError(t('addon.errors.layout.navigation_size'))
                options = {k: v for k, v in options.items() if k not in ('display', 'inline', 'controls', 'history_hours')}
            if 'background' in options and (not isinstance(options['background'],str) or options['background'] not in TILE_BACKGROUNDS):
                raise ValueError(t('addon.errors.layout.background'))
            if 'icon' in options and not (options['icon'] == 'auto' or isinstance(options['icon'], str) and options['icon'] in tile_icons.ICONS):
                raise ValueError(t('addon.errors.choose_icon'))
            domain = tile['entity'].split('.')[0]
            displays = DISPLAYS.get(domain, ('standard', 'watch'))
            choices = {'tap': ('auto', 'detail', 'toggle', 'none', 'action'), 'display': displays, 'inline': ('none', 'slider'), 'size': TILE_SIZES_ON_SCREEN}
            for key, allowed in choices.items():
                if key in options and options[key] not in allowed:
                    raise ValueError(t('addon.errors.layout.invalid_setting', setting=key))
            # The second line of a tile (app 0.2.105): the line the screen works out itself, nothing at all, words
            # of your own, or a value of the entity that Home Assistant names. Which values those are is Home
            # Assistant's answer and changes with it, so the name is only checked for its shape here; a value that
            # is not there any more simply leaves the line to the screen again.
            sub = options.get('sub')
            if sub is not None:
                if not isinstance(sub, str) or len(sub.encode()) > 96:
                    raise ValueError(t('addon.errors.layout.invalid_setting', setting='sub'))
                if sub.startswith('text:'):
                    # Words of your own keep the words, not the space around them: a line that starts with a blank
                    # is a line that looks indented on the tile, and every other line starts at the same place.
                    words = sub[5:].strip()
                    sub = f'text:{words}' if words else 'none'
                    options = {**options, 'sub': sub}
                if sub not in ('auto', 'none') and not re.fullmatch(r'text:.+|attr:[a-z_0-9]+', sub):
                    raise ValueError(t('addon.errors.layout.invalid_setting', setting='sub'))
                if sub == 'auto':
                    options = {k: v for k, v in options.items() if k != 'sub'}
            # The five-day strip and the sun path only fit a double-width card (or the whole page).
            if options.get('display') in WIDE_ONLY and options.get('size') not in ('wide', 'square', 'full'):
                options = {**options, 'size': 'wide'}
            # On / off sends <domain>.toggle. Whether Home Assistant offers that for the entity is checked when saving
            # (Manager.check_supported, app 0.2.67); the built-in cards have nothing to switch.
            if options.get('tap') == 'toggle' and domain == 'screen':
                raise ValueError(t('addon.errors.layout.no_toggle'))
            # Perform action (app 0.2.67) keeps its action; another tap choice leaves a stale one behind.
            if options.get('tap') == 'action':
                if domain == 'screen':
                    raise ValueError(t('addon.errors.layout.builtin_action'))
                options = {**options, 'action': validate_tap_action(options.get('action'))}
            elif 'action' in options:
                options = {key: value for key, value in options.items() if key != 'action'}
            if options.get('inline') == 'slider' and domain not in {'light','fan','cover','number','input_number','media_player'}:
                raise ValueError(t('addon.errors.layout.no_mini_slider'))
            if 'history_hours' in options and (type(options['history_hours']) is not int or options['history_hours'] not in (1,6,24)):
                raise ValueError(t('addon.errors.layout.history_hours'))
            # A live picture's pace (app 0.2.91) belongs to the live display; another display leaves a stale one behind.
            # So does how its picture fills a taller card and whether its name is on it (app 0.3.8); the defaults are
            # not stored, so a layout without them means what it always meant.
            if options.get('display') == 'live':
                if 'refresh' in options and (type(options['refresh']) is not int or options['refresh'] not in LIVE_REFRESH):
                    raise ValueError(t('addon.errors.layout.refresh'))
                for key, allowed in PICTURE_OPTIONS.items():
                    if key in options and options[key] not in allowed:
                        raise ValueError(t('addon.errors.layout.invalid_setting', setting=key))
                options = {key: value for key, value in options.items() if key not in PICTURE_OPTIONS or value != PICTURE_OPTIONS[key][0]}
            elif set(options) & {'refresh', *PICTURE_OPTIONS}:
                options = {key: value for key, value in options.items() if key not in ('refresh', *PICTURE_OPTIONS)}
            if options.get('display') == 'watch' and options.get('inline') == 'slider':
                raise ValueError(t('addon.errors.layout.watch_or_slider'))
            if 'controls' in options:
                allowed = ('none',) + tuple(key for key, _ in CONTROLS.get(domain, ()))
                if not isinstance(options['controls'], str) or options['controls'] not in allowed:
                    raise ValueError(t('addon.errors.layout.no_direct_control'))
            item['options'] = dict(options)
        clean.append(item)
    # Positions: every tile or none (an older editor sends none and keeps its order).
    given = [tile.get('slot') for tile in tiles]
    if any(slot is not None for slot in given):
        occupied = set()
        for item, slot in zip(clean, given):
            if type(slot) is not int or not 0 <= slot < (grid.max_slots if grid else FIRMWARE_MAX_TILES):
                raise ValueError(t('addon.errors.layout.position'))
            item['slot'] = slot
            if grid is None:
                continue
            size = tile_size(item)
            if size == 'full' and slot % grid.slots:
                raise ValueError(t('addon.errors.layout.full_page_top'))
            if size == 'wide' and not grid.wide_fits(slot):
                raise ValueError(t('addon.errors.layout.wide_left'))
            if not grid.fits(slot, size):
                raise ValueError(t('addon.errors.layout.position'))
            for cell in grid.footprint(slot, size):
                if cell in occupied:
                    raise ValueError(t('addon.errors.layout.same_spot'))
                occupied.add(cell)
        clean.sort(key=lambda item: item['slot'])
    else:
        for item, slot in zip(clean, packed_slots(clean, grid or DEFAULT_GRID)):
            item['slot'] = slot
    result = {'title': title.strip(), 'tiles': clean}
    # Pages kept on purpose, empty ones included; the screen shows at least what the tiles need.
    if 'pages' in data:
        pages = grid.pages if grid else FIRMWARE_MAX_PAGES
        if type(data['pages']) is not int or not 1 <= data['pages'] <= pages:
            raise ValueError(t('addon.errors.layout.pages', n=pages))
        result['pages'] = data['pages']
    # A title of its own for a page (app 0.2.105). The screen's title stands on every page, which is what most
    # screens want; a page that should say something else says it here, and an empty entry means the screen's.
    # Trailing empty entries are dropped, so a layout where nobody set one carries nothing at all.
    # Page 1 carries its own like any other page (app 0.2.123): the firmware falls back to the screen's title per
    # page (runtime_model.h, title_of), and a title that belongs to its page survives a reorder of the row. The
    # editor asks for both there: the screen's title, and what page 1 itself says.
    if 'page_titles' in data:
        names = data['page_titles']
        pages = grid.pages if grid else FIRMWARE_MAX_PAGES
        if not isinstance(names, list) or len(names) > pages:
            raise ValueError(t('addon.errors.layout.page_titles', n=pages))
        clean_names = []
        for name in names:
            if not isinstance(name, str) or len(name.encode()) > 96:
                raise ValueError(t('addon.errors.layout.page_title'))
            clean_names.append(name.strip())
        while clean_names and not clean_names[-1]:
            clean_names.pop()
        if clean_names:
            result['page_titles'] = clean_names
    if 'settings' in data:
        result['settings'] = validate_settings(data['settings'])
    if 'header' in data:
        result['header'] = validate_header(data['header'])
    return result

def local_clock(value, tz):
    """HH:MM in the home's time zone for an ISO timestamp; '' when unusable."""
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return ''
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz or timezone.utc).strftime('%H:%M')

def forecast_kinds(attributes):
    """The forecasts a weather entity offers, from its supported_features (WeatherEntityFeature: 1 daily,
    2 hourly). Asking for one it lacks makes Home Assistant log an error; an entity that reports no features
    (unavailable) is asked for both, as before."""
    features = (attributes or {}).get('supported_features')
    if not isinstance(features, int) or isinstance(features, bool):
        return frozenset(('daily', 'hourly'))
    return frozenset(kind for kind, bit in (('daily', 1), ('hourly', 2)) if features & bit)

def forecast_number(entry, name):
    value = entry.get(name)
    return round(value, 1) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

def forecast_time(entry, tz):
    try:
        return datetime.fromisoformat(str(entry.get('datetime')).replace('Z', '+00:00')).astimezone(tz or timezone.utc)
    except (ValueError, TypeError):
        return None

def alarm_extras(state, entry):
    """What an alarm panel's card needs beside its attributes (firmware 0.3.3+): `dc` 1 when Home Assistant keeps a default
    code in the entity's registry options (it then fills the code in itself and the screen asks for none, as Home
    Assistant's own dialogs do; the code itself never leaves Home Assistant), and during an exit or entry delay the moment
    it ends (`ae`, epoch) and its length (`ad`, seconds), where the integration reports it (Alarmo's `delay` attribute)."""
    result = {}
    options = (entry or {}).get('options') if isinstance(entry, dict) else None
    panel = options.get('alarm_control_panel') if isinstance(options, dict) else None
    if isinstance(panel, dict) and isinstance(panel.get('default_code'), str) and panel['default_code']:
        result['dc'] = 1
    state = state if isinstance(state, dict) else {}
    delay = (state.get('attributes') or {}).get('delay')
    if state.get('state') in ('arming', 'pending') and isinstance(delay, (int, float)) and not isinstance(delay, bool) \
            and math.isfinite(delay) and 0 < delay <= 86400:
        start = epoch(state.get('last_changed'))
        if start:
            result['ae'] = start + int(delay)
            result['ad'] = int(delay)
    return result

def epoch(value):
    """Unix time of an ISO timestamp (a scene's state, a script's last_triggered); None when unusable."""
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())

# Vacuum cards (app 0.2.46, firmware 0.2.39+): how a robot cleans is often a select on its own device,
# not an attribute. Roborock has "Cleaning mode" (vacuum, vac_and_mop, mop, custom, smart_mode) and
# "Mop intensity" since HA 2026.8; Ecovacs calls its mode work_mode. They are found by translation key
# or by the end of their entity id. HA 2026.8 also dropped battery_level from vacuum entities, so the
# battery comes from the device's battery sensor.
VACUUM_MODE_KEYS = ('cleaning_mode', 'work_mode', 'clean_mode')
VACUUM_WATER_KEYS = ('mop_intensity', 'water_flow', 'water_amount', 'water_flow_level', 'water_volume', 'mop_water_level')
# Short chip labels, by the key of their words in the screens' language (app 0.2.90); anything else shows its own words.
# The suction speeds the screen names itself, and Off, are the screen's own words.
VACUUM_CHIP = 'addon.screen.vacuum.'
VACUUM_LABELS = {
    'vacuum': VACUUM_CHIP + 'vacuum', 'sweeping': VACUUM_CHIP + 'vacuum', 'vac_and_mop': VACUUM_CHIP + 'vac_and_mop',
    'vacuum_and_mop': VACUUM_CHIP + 'vac_and_mop', 'sweeping_and_mopping': VACUUM_CHIP + 'vac_and_mop',
    'mop_after_vacuum': VACUUM_CHIP + 'vac_then_mop', 'mopping_after_sweeping': VACUUM_CHIP + 'vac_then_mop',
    'mop': VACUUM_CHIP + 'mop', 'mopping': VACUUM_CHIP + 'mop', 'custom': VACUUM_CHIP + 'custom', 'smart_mode': VACUUM_CHIP + 'smart',
    'off': 'screen.ha.off', 'min': VACUUM_CHIP + 'min', 'slight': VACUUM_CHIP + 'slight', 'low': VACUUM_CHIP + 'low',
    'mild': VACUUM_CHIP + 'mild', 'medium': VACUUM_CHIP + 'medium', 'moderate': VACUUM_CHIP + 'moderate',
    'standard': VACUUM_CHIP + 'standard', 'high': VACUUM_CHIP + 'high', 'intense': VACUUM_CHIP + 'intense',
    'extreme': VACUUM_CHIP + 'extreme', 'ultrahigh': VACUUM_CHIP + 'ultra_high', 'quiet': 'screen.vacuum.speed_quiet',
    'silent': VACUUM_CHIP + 'silent', 'gentle': VACUUM_CHIP + 'gentle', 'balanced': 'screen.vacuum.speed_balanced',
    'turbo': 'screen.vacuum.speed_turbo', 'strong': VACUUM_CHIP + 'strong', 'max': 'screen.vacuum.speed_max',
    'max_plus': VACUUM_CHIP + 'max_plus', 'auto': VACUUM_CHIP + 'auto',
}
# What a cleaning mode does, one letter per option for the firmware: v vacuum only, m mop only, b both,
# a automatic (the robot or its app picks suction and water). Unknown modes count as both.
VACUUM_ROLES = {'vacuum': 'v', 'sweeping': 'v', 'mop': 'm', 'mopping': 'm', 'custom': 'a', 'smart_mode': 'a'}
# With a cleaning mode select these speeds and water levels belong to a mode: suction off is mop only,
# water off is vacuum only, and custom or smart settings are the Custom and Smart modes.
MODE_COVERED = frozenset(('off', 'off_raise_main_brush', 'custom', 'custom_water_flow', 'smart_mode', 'vac_followed_by_mop'))
VACUUM_CHOICES = 6

def vacuum_label(value):
    key = VACUUM_LABELS.get(value)
    return short(screen_t(key) if key else str(value).replace('_', ' ').capitalize(), 24)

def vacuum_related(entity, device, states):
    """Entities on the vacuum's device that its card reads, by role: the 'mode' and 'water' selects, the
    'battery' and 'room' sensors and the 'charging' binary sensor; absent roles are left out.

    `device` holds the registry entries of the vacuum's device. Entity ids follow Home Assistant's
    language (select.s8_intensiteit_van_dweilen), so translation keys come first."""
    found = {}
    for item in device or ():
        eid = item.get('entity_id') or ''
        if eid == entity or item.get('disabled_by'):
            continue
        key = item.get('translation_key') or ''
        attrs = states.get(eid, {}).get('attributes', {})
        role = None
        if eid.startswith('select.'):
            if key in VACUUM_MODE_KEYS or eid.endswith(tuple('_' + k for k in VACUUM_MODE_KEYS)):
                role = 'mode'
            elif key in VACUUM_WATER_KEYS or eid.endswith(tuple('_' + k for k in VACUUM_WATER_KEYS)):
                role = 'water'
        elif eid.startswith('sensor.'):
            if attrs.get('device_class') == 'battery':
                role = 'battery'
            elif key == 'current_room' or eid.endswith('_current_room'):
                role = 'room'
        elif eid.startswith('binary_sensor.') and attrs.get('device_class') == 'battery_charging':
            role = 'charging'
        if role and role not in found:
            found[role] = eid
    return found

def device_power(attrs, related, states):
    """`bat` from the device's battery sensor when the entity has no battery_level of its own, and `chg` while its
    charging sensor is on; empty without them."""
    result = {}
    if not isinstance(attrs.get('battery_level'), (int, float)) and 'battery' in related:
        try:
            level = float(states[related['battery']].get('state'))
        except (TypeError, ValueError, KeyError):
            level = math.nan
        if math.isfinite(level):
            result['bat'] = max(0, min(100, round(level)))
    if states.get(related.get('charging'), {}).get('state') == 'on':
        result['chg'] = 1
    return result

def cover_related(entity, device, states):
    """A cover's battery and charging sensors on its device (app 0.2.58): battery-powered blinds such as
    Motionblinds report the battery there."""
    return {role: eid for role, eid in vacuum_related(entity, device, states).items() if role in ('battery', 'charging')}

def vacuum_extras(tile, states, device):
    """The vacuum card's rows and details: the mode and water selects (`e` entity, `s` state, `o` options,
    `l` labels, `r` a role per mode), the suction speeds to offer (`fan`), the battery (`bat`), charging
    (`chg`) and the room the robot is in (`room`)."""
    entity = tile['entity']
    attrs = states.get(entity, {}).get('attributes', {})
    related = vacuum_related(entity, device, states)
    result = {}
    def row(values):
        values = [short(v, 48) for v in values][:VACUUM_CHOICES]
        return {'o': values, 'l': [vacuum_label(v) for v in values]} if values else None
    def select(eid, keep):
        state = states.get(eid) or {}
        options = state.get('attributes', {}).get('options')
        current = state.get('state') if isinstance(state.get('state'), str) else ''
        found = row([o for o in options if isinstance(o, str) and keep(o, current)]) if isinstance(options, list) else None
        return {'e': eid, 's': short(current, 48), **found} if found else None
    # Custom runs the per-room settings made in the robot's app: listed only while it is in use.
    mode = select(related['mode'], lambda o, current: o != 'custom' or o == current) if 'mode' in related else None
    covered = MODE_COVERED if mode else frozenset()
    if mode:
        mode['r'] = ''.join(VACUUM_ROLES.get(v, 'b') for v in mode['o'])
        result['mode'] = mode
    water = select(related['water'], lambda o, current: o not in covered) if 'water' in related else None
    if water:
        result['water'] = water
    speeds = attrs.get('fan_speed_list')
    fan = row([s for s in speeds if isinstance(s, str) and s not in covered]) if isinstance(speeds, list) else None
    if fan:
        result['fan'] = fan
    result.update(device_power(attrs, related, states))
    room = states.get(related.get('room'), {}).get('state')
    if isinstance(room, str) and room not in ('', 'unknown', 'unavailable', 'none'):
        result['room'] = short(room, 32)
    return result or None

def media_extras(attrs):
    """The media card (app 0.2.77, firmware 0.2.64+): the artist and the album, the track's length and where it was
    when Home Assistant last said so (seconds; that moment as an epoch), and a short mark of the cover picture. The
    mark changes with the picture and says nothing else: the screen asks the app for the picture itself."""
    result = {}
    for key, name in (('artist', 'media_artist'), ('album', 'media_album_name')):
        value = attrs.get(name)
        if isinstance(value, str) and value.strip():
            result[key] = short(value.strip(), 80)
    for key, name in (('dur', 'media_duration'), ('pos', 'media_position')):
        value = attrs.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 10_000_000:
            if key == 'dur' and value <= 0:
                continue
            result[key] = int(value)
    moment = attrs.get('media_position_updated_at')
    if isinstance(moment, str) and moment:
        try:
            parsed = datetime.fromisoformat(moment.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            result['at'] = int(parsed.timestamp())
        except ValueError:
            pass
    picture = attrs.get('entity_picture') or attrs.get('entity_picture_local')
    if isinstance(picture, str) and picture:
        # Without Home Assistant's access token (app 0.3.7): it changes every few minutes on its own while the picture
        # stays, and each new token made every screen fetch the same cover again. The link's `cache` part is the
        # picture's own hash, so the mark still changes with the picture.
        stable = re.sub(r'([?&])token=[^&]*(&|$)', lambda m: m.group(1) if m.group(2) else '', picture)
        result['pic'] = hashlib.sha1(stable.encode()).hexdigest()[:10]
    return result or None


def extras(tile, states, forecast=None, tz=None, hourly=None, now=None, device=None, entries=None, words=None, icon_of=None, device_name=None):
    """Small, pre-computed values the firmware cannot derive itself (time zones, forecasts, a vacuum's device, the rows of
    a light's effects page)."""
    domain = tile['entity'].split('.')[0]
    attrs = states.get(tile['entity'], {}).get('attributes', {})
    if domain == 'light':
        # The effects page (app 0.2.83): the select and number entities of the light's device, named as Home Assistant
        # names them; the effect itself travels as the `effect` attribute.
        import light_effects
        return light_effects.rows(tile['entity'], device, states, entries, words, icon_of, device_name) or None
    if domain == 'vacuum':
        return vacuum_extras(tile, states, device)
    if domain == 'cover':
        return device_power(attrs, cover_related(tile['entity'], device, states), states) or None
    if domain == 'media_player':
        return media_extras(attrs)
    if domain == 'weather' and (forecast or hourly):
        result = {}
        days = []
        for entry in forecast or []:
            if not isinstance(entry, dict) or len(days) == 5:
                continue
            day = forecast_time(entry, tz)
            if day is None:
                continue
            # The day's short name in the screens' language (app 0.2.90); the list starts on Sunday, Python's week on Monday.
            item = {'d': screen_t(f'screen.date.weekdays_min.{(day.weekday() + 1) % 7}'), 'c': short(entry.get('condition') or '', 20)}
            # h/l: high and low; p: chance of rain in %; r: rain in the entity's unit (mm).
            for key, name in (('h', 'temperature'), ('l', 'templow'), ('p', 'precipitation_probability'), ('r', 'precipitation')):
                value = forecast_number(entry, name)
                if value is not None:
                    item[key] = value
            days.append(item)
        if days:
            result['days'] = days
        # The next eight hours from now, for the weather card's hourly strip.
        hours = []
        # The running hour still counts: an entry stays until its hour has passed.
        start = (now or datetime.now(timezone.utc)) - timedelta(minutes=59)
        for entry in hourly or []:
            if not isinstance(entry, dict) or len(hours) == 8:
                continue
            moment = forecast_time(entry, tz)
            if moment is None or moment < start:
                continue
            item = {'t': moment.strftime('%H:%M'), 'c': short(entry.get('condition') or '', 20)}
            for key, name in (('h', 'temperature'), ('p', 'precipitation_probability'), ('r', 'precipitation')):
                value = forecast_number(entry, name)
                if value is not None:
                    item[key] = value
            hours.append(item)
        if hours:
            result['hours'] = hours
        return result or None
    if domain in ('scene', 'script', 'button', 'input_button', 'image'):
        # When it last ran: scripts report last_triggered; scenes and buttons carry the time as their state, and so does
        # an image entity (when its picture last changed).
        last = epoch(attrs.get('last_triggered') if domain == 'script' else states.get(tile['entity'], {}).get('state'))
        return {'last': last} if last else None
    if domain == 'sun':
        rise, down = local_clock(attrs.get('next_rising'), tz), local_clock(attrs.get('next_setting'), tz)
        return {'rise': rise, 'set': down} if rise or down else None
    if domain == 'timer':
        result = {}
        try:
            end = datetime.fromisoformat(str(attrs.get('finishes_at')).replace('Z', '+00:00'))
            result['end'] = int(end.timestamp())
        except (ValueError, TypeError):
            pass
        for key, name in (('dur', 'duration'), ('rem', 'remaining')):
            if isinstance(attrs.get(name), str):
                result[key] = short(attrs[name], 16)
        return result or None
    return None

def tile_icon(tile, attrs, state=None, entry=None):
    """Codepoint the screen shows: the chosen icon, else HA's own mdi icon, else the icon Home Assistant's frontend shows
    for this state (app 0.2.67); None keeps the firmware default."""
    choice = tile.get('options', {}).get('icon', 'auto')
    if choice in tile_icons.ICONS:
        return tile_icons.ICONS[choice][0]
    return tile_icons.ha_icon(attrs) or tile_icons.default_glyph(tile['entity'], state, attrs, entry)

def screen_options(tile, attrs, state=None, entry=None):
    """Stored options on the wire; `icon` travels as the resolved codepoint (firmware 0.2.18+, ignored before)
    and `controls` only as the set the card really shows (firmware 0.2.19+, ignored before)."""
    options = {k: v for k, v in tile.get('options', {}).items() if k not in ('icon', 'controls', 'action')}
    icon = tile_icon(tile, attrs, state, entry)
    if icon:
        options['icon'] = icon
    controls = resolve_controls(tile)
    if controls:
        options['controls'] = controls
    # Perform action travels in the firmware's compact form (0.2.58+); older firmware taps automatically.
    action = tile.get('options', {}).get('action')
    if options.get('tap') == 'action' and isinstance(action, dict):
        try:
            options['act'] = action_for_screen(validate_tap_action(action))
        except ValueError:
            pass
    return options if options or 'options' in tile else None

def rounded_state(value, precision):
    """A sensor's state as Home Assistant shows it with a display precision (app 0.2.67): "21.456" at 1 becomes "21.5".
    No thousands separators, so the screen still reads the number; anything that isn't a number stays as it is."""
    if type(precision) is not int or not 0 <= precision <= 6:
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(number):
        return value
    from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
    try:
        text = format(Decimal(str(value)).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP), 'f')
    except InvalidOperation:  # more digits than Decimal's context holds, such as 1e30: the value is fine as it is
        return value
    return text[1:] if text.startswith('-') and not text.strip('-0.') else text

def ha_word(entity_id, suffix, attributes, entry, words):
    """Home Assistant's English word for `suffix` (`state.<state>`, or `state_attributes.<attribute>.state.<value>`) as its
    frontend picks it: the integration's word for the entity's translation key, then the domain's word for the state's
    device class, then the domain's. None when Home Assistant has none (frontend/get_translations `entity` and
    `entity_component`, app 0.2.67)."""
    if not isinstance(words, dict) or not words or not isinstance(entity_id, str):
        return None
    domain = entity_id.split('.', 1)[0]
    entry = entry if isinstance(entry, dict) else {}
    device_class = attributes.get('device_class') if isinstance(attributes, dict) else None
    keys = []
    if entry.get('platform') and entry.get('translation_key'):
        keys.append(f"component.{entry['platform']}.entity.{domain}.{entry['translation_key']}.{suffix}")
    if isinstance(device_class, str) and device_class:
        keys.append(f'component.{domain}.entity_component.{device_class}.{suffix}')
    keys.append(f'component.{domain}.entity_component._.{suffix}')
    return next((words[key] for key in keys if isinstance(words.get(key), str) and words[key]), None)

def state_word(entity_id, state, attributes, entry, words):
    """Home Assistant's word for a state ("rinsing" is "Rinsing", "heat_cool" is "Heat/Cool"), or None."""
    return ha_word(entity_id, f'state.{state}', attributes, entry, words) if isinstance(state, str) and state else None

def attribute_word(entity_id, attribute, value, attributes, entry, words):
    """Home Assistant's word for an attribute's value, such as a robot's suction level, or None."""
    if not isinstance(value, str) or not value:
        return None
    return ha_word(entity_id, f'state_attributes.{attribute}.state.{value}', attributes, entry, words)

def state_message(index, tile, states, extra=None, precision=None, entry=None):
    if tile['entity'] in BUILTIN:
        message = {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'],
                   'name': short(tile['name'] or builtin_name(tile['entity']), 80), 'state': 'ok', 'a': {}}
        # The same wire form as any tile, so a chosen icon travels as its codepoint (app 0.2.74+).
        options = screen_options(tile, {})
        if options is not None:
            message['o'] = options
        return message
    state = states.get(tile['entity'], {})
    attrs = state.get('attributes', {})
    bounded = {}
    for key in ATTRS:
        value = attrs.get(key)
        if isinstance(value, bool):
            if key in BOOL_ATTRS:
                bounded[key] = value
            continue
        if value is None:
            continue
        if isinstance(value, (int, float)):
            # supported_features is a bit field (media players exceed 8 million); other numbers are display values.
            if math.isfinite(value) and abs(value) <= (2**31 if key == 'supported_features' else 1000000):
                bounded[key] = value
        elif isinstance(value, str):
            bounded[key] = short(value, 48)
        elif isinstance(value, list):
            # Attribute lists have bounded lengths, strings and numeric ranges.
            # A select's options run to sixteen (firmware 0.3.3 pages through them; older firmware keeps the first eight).
            limit = 2 if key == 'hs_color' else 4 if key == 'fan_speed_list' else 16 if key == 'options' else 8
            bounded[key] = [short(v, 48) if isinstance(v, str) else v for v in value[:limit]
                            if isinstance(v, str) or isinstance(v, (float, int)) and math.isfinite(v) and abs(v) <= 1000000]
    options = screen_options(tile, attrs, state.get('state'), entry)
    return {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'],
            'name': short(tile['name'] or attrs.get('friendly_name') or tile['entity'], 80),
            'state': short(rounded_state(state.get('state', 'unavailable'), precision) if tile['entity'].startswith('sensor.') else state.get('state', 'unavailable'), 160), 'a': bounded,
            **({'o': options} if options is not None else {}), **({'x': extra} if extra else {})}

def encode(message):
    """The message as the firmware parses it: compact JSON, at most 4096 bytes."""
    raw = json.dumps(message, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(raw.encode()) > 4096:
        raise ValueError('The screen message is too large.')
    return raw

def revision(message):
    """Short fingerprint of a layout message; the screen echoes it back on every ping."""
    return hashlib.sha256(json.dumps(message, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:12]

def packets(message, token=None):
    """The message as base64 chunks for the 255-character text inbox (firmware before 0.2.33)."""
    encoded = base64.b64encode(encode(message).encode()).decode('ascii')
    token = token or secrets.token_hex(8)
    chunks = [encoded[i:i+200] for i in range(0, len(encoded), 200)]
    return [f'{token}|{i}|{int(i == len(chunks)-1)}|{part}' for i, part in enumerate(chunks)]

def message_action(node):
    """Home Assistant action that hands a screen one whole message, or None without a node name."""
    return alert_service(node, MESSAGE_ACTION)

# ----- Alerts (firmware 0.2.31+): the reference the cheatsheet shows. tests/test_alerts_reference.py
# keeps every value here equal to what the board profiles compile. The texts in English, as the Claude skill
# writes them; the cheatsheet gets them in the editor's language (alert_reference, app 0.2.90). -----
ALERT_MIN_FIRMWARE = '0.2.31'
ALERT_EVENT = 'esphome.screen_alert'
ALERT_ENDINGS = (('ok', 'The button was pressed'), ('button2', 'The second button was pressed'), ('timeout', 'The timeout ran out'),
                 ('replaced', 'A new alert came over it'), ('remote', 'dismiss_alert from Home Assistant'))
ALERT_FALLBACK_ICON = 'alert-outline'
# (field, ESPHome type, label, explanation, example) in the order Home Assistant shows them.
ALERT_FIELDS = (
    ('title', 'string', 'Title', 'A single line at the top of the card; what doesn\'t fit gets an ellipsis. Empty becomes "Notification".', 'Someone is at the door'),
    ('subtitle', 'string', 'Subtitle', 'Explanation under the title, across multiple lines; a line break is fine. Empty is fine.', 'Door 3, back'),
    ('icon', 'string', 'Icon', 'A name from the list, also as mdi:name or as a hex codepoint (F12E6). Unknown or empty gives the warning triangle.', 'doorbell'),
    ('color', 'string', 'Color', 'One of the nine pastel colors of the tiles. Empty gives the white card.', 'orange'),
    ('button_text', 'string', 'Button text', 'The text on the button. Empty is "OK".', 'Coming'),
    ('timeout', 'int', 'Timeout', 'Seconds after which the card disappears on its own. 0 waits for the button, however long that takes. The button always closes it immediately, even with a timeout.', 0),
    ('flash', 'bool', 'Blinking', 'On makes the backlight blink four times when the alert arrives; the screen then just stays on.', True),
)
# Examples that are words for people, which the cheatsheet shows in the editor's language; an icon, a colour or a number
# is a value to type as it is.
ALERT_TEXT_EXAMPLES = frozenset(('title', 'subtitle', 'button_text'))
# Bytes per field the firmware keeps, per look (ALERT_*_MAX in packages/looks/); an accented letter takes two.
ALERT_LIMITS = {'compact': {'title': 48, 'subtitle': 160, 'button_text': 12}, 'standard': {'title': 64, 'subtitle': 240, 'button_text': 16}}
ALERT_SUGGESTED_ICONS = ('doorbell', 'bell', 'bell-ring', 'alert-outline', 'alarm-light', 'lock', 'lock-open-variant', 'door-open',
                         'window-closed-variant', 'motion-sensor', 'cctv', 'smoke-detector', 'water-alert', 'fire', 'mailbox', 'car',
                         'account', 'account-group', 'washing-machine', 'robot-vacuum', 'timer-outline', 'check')
# Not an argument of show_alert: the app sends the image itself to screens that can draw it (app 0.2.66, a Guition with
# firmware 0.2.57+) and leaves it out for the others. (name, label, explanation, example) like ALERT_FIELDS.
ALERT_CAMERA_FIELD = ('camera', 'Camera', 'A camera or image entity. Every screen but the CYD, with firmware 0.2.57+, shows its picture of that moment on the card, in the proportions of the camera itself (above the words, or beside them on a wide, low screen); a tap on it opens the camera full screen. The CYD shows the alert without it. Only through the esp_screens_show_alert event.', 'camera.front_door')
# An action behind the button (app 0.2.91): the event names a Home Assistant action, with data for its fields, that the
# app performs when the button is pressed on any screen, once per alert. Not an argument of show_alert either: the
# screen only reports the press (ALERT_EVENT, action "ok") and the app does the rest, so every firmware from 0.2.31 has it.
ALERT_ACTION_FIELD = ('action', 'Action', 'A Home Assistant action, such as script.open_gate or light.turn_off, performed once when the button is pressed on any screen. `data` gives its fields (entity_id, brightness, ...). A timeout or a new alert leaves it unperformed. Only through the esp_screens_show_alert event.', 'script.open_gate')
ALERT_ACTION_MAX_BYTES = 4096
# Who gets it (app 0.2.133): without a `screen` the event goes to every screen, as it always did; with one, only to the
# screens it names. That is how one screen gets a camera picture or a button action, which its own show_alert action cannot
# take: Home Assistant makes every field of a device's action required, so show_alert keeps its seven. A name is the
# device name, the name Home Assistant shows, or a room (every screen in it), written loosely (case, spaces, dashes and
# underscores don't matter); a list names several. A name that matches no screen sends nothing, never to everyone.
ALERT_SCREEN_FIELD = ('screen', 'Screen', 'Which screen gets the alert: its device name (such as kitchen-screen), the name Home Assistant shows, or a room, which reaches every screen in it. A list, such as [kitchen-screen, hallway], reaches several. Leave it out for every screen. A name that matches no screen sends nothing; the ESP Screen Manager log names the screens it knows. Only through the esp_screens_show_alert and esp_screens_dismiss_alert events.', 'kitchen-screen')
# A second button and a colour per button (firmware 0.3.3+): the screen's own show_alert_choice action, which takes the seven
# fields of show_alert and these three. Through the event they are optional: an alert that uses any of them goes to a screen
# with that firmware as show_alert_choice, and to an older one as show_alert, with its one button. (field, ESPHome type,
# label, explanation, example) like ALERT_FIELDS, in the order show_alert_choice declares them after button_text.
ALERT_CHOICE_MIN_FIRMWARE = '0.3.3'
ALERT_CHOICE_ACTION = 'show_alert_choice'
ALERT_CHOICE_FIELDS = (
    ('button_color', 'string', 'Button color', 'The button in a color of its own: red, orange, yellow, green, mint, blue, purple, pink or gray, as a full key color with white words. Empty keeps the dark button.', 'green'),
    ('button2_text', 'string', 'Second button text', 'A second button on the left of the first, for a choice such as Decline and Accept. Empty gives one button.', 'Not now'),
    ('button2_color', 'string', 'Second button color', 'The second button in one of the same colors. Empty keeps the light button.', 'red'),
)
ALERT_CHOICE_ORDER = ('title', 'subtitle', 'icon', 'color', 'button_text', 'button_color', 'button2_text', 'button2_color', 'timeout', 'flash')
# What the second button does, like `action` and `data` for the first (app 0.3.8): performed once when it is pressed.
ALERT_ACTION2_FIELD = ('button2_action', 'Second button action', 'A Home Assistant action performed once when the second button is pressed on any screen, like `action` for the first. `button2_data` gives its fields. Only through the esp_screens_show_alert event.', 'script.snooze_reminder')
# The firmware's MAX_TIMEOUT_SECONDS.
ALERT_MAX_TIMEOUT = 86400
# One alert for every screen (app 0.2.45): an automation fires one of these Home Assistant events and the
# app calls the matching action on each screen that can show it, screens added later included.
BROADCAST_SHOW, BROADCAST_DISMISS = 'esp_screens_show_alert', 'esp_screens_dismiss_alert'
BROADCAST_EVENTS = {BROADCAST_SHOW: 'show_alert', BROADCAST_DISMISS: 'dismiss_alert'}

def alert_service(node, action='show_alert'):
    """Home Assistant registers a device's actions as esphome.<node>_<action>, dashes as underscores."""
    return f"esphome.{node.replace('-', '_')}_{action}" if isinstance(node, str) and node else None

def limit_boards():
    """{look: the catalog's names of the boards with that look} (boards.json), so whatever shows the alert limits
    says whose limit is whose without naming a board itself."""
    return {look: list(dict.fromkeys(SHAPES[board].get('catalog', {}).get('name', board) for board in BOARD_KEYS
                                     if SHAPES[board].get('look') == look)) for look in ALERT_LIMITS}

def alert_reference():
    """Everything the Alerts cheatsheet shows besides the screens themselves, in the editor's language (app 0.2.90)."""
    def example(name, value):
        return t(f'addon.alerts.fields.{name}.example') if name in ALERT_TEXT_EXAMPLES else value
    camera = ALERT_CAMERA_FIELD[0]
    return {'min_firmware': ALERT_MIN_FIRMWARE, 'event': ALERT_EVENT,
            'broadcast': {'show': BROADCAST_SHOW, 'dismiss': BROADCAST_DISMISS},
            'endings': [{'action': action, 'label': t(f'addon.alerts.endings.{action}')} for action, _ in ALERT_ENDINGS],
            'fallback_icon': ALERT_FALLBACK_ICON, 'fallback_cp': tile_icons.GLYPHS[ALERT_FALLBACK_ICON],
            'fields': [{'name': name, 'type': kind, 'label': t(f'addon.alerts.fields.{name}.label'),
                        'help': t(f'addon.alerts.fields.{name}.help'), 'example': example(name, value)}
                       for name, kind, _, _, value in ALERT_FIELDS],
            'camera': {'name': camera, 'label': t(f'addon.alerts.fields.{camera}.label'), 'help': t(f'addon.alerts.fields.{camera}.help'),
                       'example': ALERT_CAMERA_FIELD[3]},
            'screen': {'name': ALERT_SCREEN_FIELD[0], 'label': t(f'addon.alerts.fields.{ALERT_SCREEN_FIELD[0]}.label'),
                       'help': t(f'addon.alerts.fields.{ALERT_SCREEN_FIELD[0]}.help'), 'example': ALERT_SCREEN_FIELD[3]},
            'action': {'name': ALERT_ACTION_FIELD[0], 'label': t(f'addon.alerts.fields.{ALERT_ACTION_FIELD[0]}.label'),
                       'help': t(f'addon.alerts.fields.{ALERT_ACTION_FIELD[0]}.help'), 'example': ALERT_ACTION_FIELD[3]},
            'choice': {'min_firmware': ALERT_CHOICE_MIN_FIRMWARE, 'action': ALERT_CHOICE_ACTION,
                       'fields': [{'name': name, 'type': kind, 'label': t(f'addon.alerts.fields.{name}.label'),
                                   'help': t(f'addon.alerts.fields.{name}.help'),
                                   'example': t(f'addon.alerts.fields.{name}.example') if name == 'button2_text' else value}
                                  for name, kind, _, _, value in ALERT_CHOICE_FIELDS],
                       'action2': {'name': ALERT_ACTION2_FIELD[0], 'label': t(f'addon.alerts.fields.{ALERT_ACTION2_FIELD[0]}.label'),
                                   'help': t(f'addon.alerts.fields.{ALERT_ACTION2_FIELD[0]}.help'), 'example': ALERT_ACTION2_FIELD[3]}},
            'limits': ALERT_LIMITS,
            'limit_boards': limit_boards(),
            'colors': [{'name': name, 'label': item['label'], 'color': item['color']} for name, item in backgrounds().items() if item['color']],
            'suggested_icons': [{'name': name, 'cp': tile_icons.GLYPHS[name]} for name in ALERT_SUGGESTED_ICONS],
            'extra_icons': [{'name': name, 'cp': cp} for name, cp in tile_icons.FIXED]}

def _whole(value):
    """A whole number from an int, a finite float or a numeric string; None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, float):
        return int(value) if math.isfinite(value) else None
    return value if isinstance(value, int) else None

def _flag(value):
    """True/False from a bool, 0/1 or the words Home Assistant accepts; None for anything else."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = value.strip().lower() if isinstance(value, str) else None
    return True if text in ('true', 'on', 'yes', '1') else False if text in ('false', 'off', 'no', '0') else None

def alert_data(data):
    """(service data, unusable field names): the seven show_alert fields from an event's data, typed the way
    Home Assistant validates ESPHome actions. A missing field is empty; so is an unusable one (YAML turns a bare
    `Yes` into a boolean), so one bad value never loses the whole alert. The firmware clips texts itself."""
    data = data if isinstance(data, dict) else {}
    service, unusable = {}, []
    for name, kind, *_ in ALERT_FIELDS:
        value = data.get(name)
        missing = value is None or value == ''
        if kind == 'string':
            usable = isinstance(value, (str, int, float)) and not isinstance(value, bool)
            service[name] = str(value) if usable and not missing else ''
        elif kind == 'int':
            number = _whole(value)
            usable = number is not None
            service[name] = min(max(number, 0), ALERT_MAX_TIMEOUT) if usable else 0
        else:
            flag = _flag(value)
            usable = flag is not None
            service[name] = bool(flag)
        if not usable and not missing:
            unusable.append(name)
    return service, unusable

def alert_choice(data):
    """(choice fields, unusable field names): the second button's text and the buttons' colours from an event's data, as
    strings; {} when the event uses none of them, so the alert goes out as show_alert."""
    data = data if isinstance(data, dict) else {}
    fields, unusable = {}, []
    for name, *_ in ALERT_CHOICE_FIELDS:
        value = data.get(name)
        if value is None or value == '':
            continue
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            fields[name] = str(value)
        else:
            unusable.append(name)
    if not fields:
        return {}, unusable
    return {name: fields.get(name, '') for name, *_ in ALERT_CHOICE_FIELDS}, unusable

def choice_service(service_data, choice):
    """show_alert_choice's ten fields in the order it declares them."""
    merged = {**service_data, **choice}
    return {name: merged[name] for name in ALERT_CHOICE_ORDER}

def alert_camera(data):
    """(entity, usable): the alert's `camera` field when it names a camera or image entity; ('', True) without one."""
    value = data.get(ALERT_CAMERA_FIELD[0]) if isinstance(data, dict) else None
    if value is None or value == '':
        return '', True
    usable = isinstance(value, str) and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', value.strip()) is not None and value.strip().split('.')[0] in CAMERA_DOMAINS
    return (value.strip(), True) if usable else ('', False)

def alert_action(data, name=ALERT_ACTION_FIELD[0], data_name='data'):
    """((action, data), usable): the alert's `action` and `data` (or `button2_action` and `button2_data`) when they name a
    Home Assistant action with a mapping of fields; (None, True) without one, (None, False) when it is unusable."""
    value = data.get(name) if isinstance(data, dict) else None
    if value is None or value == '':
        return None, True
    fields = data.get(data_name)
    if not isinstance(value, str) or not ACTION_NAME.fullmatch(value.strip()) or len(value) > 64 or (fields is not None and not isinstance(fields, dict)):
        return None, False
    try:
        if len(json.dumps(fields or {}, ensure_ascii=False, allow_nan=False).encode()) > ALERT_ACTION_MAX_BYTES:
            return None, False
    except (TypeError, ValueError):
        return None, False
    return (value.strip(), dict(fields or {})), True

def alert_screen_names(data):
    """(names, usable): what the event's `screen` field asks for, as a list; ([], True) without one, ([], False) when it is
    neither a name nor a list of names."""
    value = data.get(ALERT_SCREEN_FIELD[0]) if isinstance(data, dict) else None
    if value is None or value == '' or value == []:
        return [], True
    values = value if isinstance(value, list) else [value]
    if not all(isinstance(item, (str, int)) and not isinstance(item, bool) and loose(item) for item in values):
        return [], False
    return [str(item).strip() for item in values], True

def alert_screen_choice(screens, names):
    """(chosen, unknown): the screens `names` mean, in the order of `screens`, and the names that match none. A name
    matches a screen's device name, the name Home Assistant shows for it, or its room, whole and loosely written; a room
    matches every screen in it."""
    def names_of(screen):
        return {loose(value) for value in (screen.get('node'), screen.get('name'), screen.get('device'), screen.get('area')) if value}
    wanted = [(name, loose(name)) for name in names]
    chosen = [screen for screen in screens if any(key in names_of(screen) for _, key in wanted)]
    unknown = [name for name, key in wanted if not any(key in names_of(screen) for screen in screens)]
    return chosen, unknown

def alert_targets(screens):
    """(ready, skipped): the paired screens that can show an alert now, and the others with the reason, in English for the
    log (the editor shows it in its own language, app 0.2.90).

    One call per device: a screen that shows up twice (an old inbox next to a renamed one) counts once."""
    minimum = parse_firmware(ALERT_MIN_FIRMWARE)
    ready, skipped, nodes = [], [], set()
    for screen in screens:
        version = screen_firmware(screen)
        node = screen.get('node')
        if node in nodes:
            continue
        if not node:
            skipped.append((screen, english('addon.errors.alerts.no_device_name')))
        elif not screen.get('online'):
            skipped.append((screen, english('addon.errors.alerts.offline')))
        elif version is None or version < minimum:
            # The sensor's own "unknown" reads as ours, which translates.
            firmware = screen.get('firmware')
            if firmware in (None, '', 'unknown'):
                firmware = english('addon.errors.alerts.unknown_version')
            skipped.append((screen, english('addon.errors.alerts.firmware', version=firmware)))
        else:
            ready.append(screen)
            nodes.add(node)
    return ready, skipped

def screen_items(registry):
    """The ESPHome entities that describe a screen; the subset `discover_screens` needs."""
    return [item for item in registry if item.get('platform') == 'esphome' and item.get('original_name') in SCREEN_ENTITY_NAMES]

def discover_screens(registry, states, devices, areas):
    """Paired screens: every enabled ESPHome inbox with the diagnostics of its device."""
    device_map = {d['id']: d for d in devices}
    area_map = {a['area_id']: a['name'] for a in areas}
    versions = {item.get('device_id'): states.get(item['entity_id'], {}).get('state', 'unknown') for item in registry
                if item.get('platform') == 'esphome' and item.get('original_name') in NAME_SCREEN_FIRMWARE}
    boards = {item.get("device_id"): "guition" for item in registry
              if item.get("platform") == "esphome" and item.get("original_name") in NAME_GUITION_TYPE}
    def diagnostic(names, pattern):
        found = {}
        for item in registry:
            if item.get('platform') == 'esphome' and item.get('original_name') in names:
                value = states.get(item['entity_id'], {}).get('state', '')
                # A screen that restarts reports "unavailable", which reads like a device name.
                if isinstance(value, str) and value not in ('unknown', 'unavailable') and re.fullmatch(pattern, value):
                    found[item.get('device_id')] = value
        return found
    # The screen's own word about its board wins over the Guition-only sensor; anything this app has never
    # heard of is ignored, so a screen cannot name a board that has no shape here.
    boards.update({device: board for device, board in diagnostic(NAME_SCREEN_BOARD, r'[a-z0-9][a-z0-9-]{0,30}').items()
                   if board in SHAPES})
    nodes = diagnostic(NAME_DEVICE_NAME, r'[a-z0-9][a-z0-9-]{0,30}')
    shapes = diagnostic(NAME_SCREEN_LAYOUT, SHAPE_TEXT)
    # What the screen says its backlight can do (firmware 0.2.99): nothing here for older firmware, and nothing
    # while it is offline either, which is when the board's row in boards.json decides (features_of).
    features = diagnostic(NAME_SCREEN_FEATURES, FEATURES_TEXT)
    addresses = diagnostic(NAME_IP_ADDRESS, r'\d{1,3}(\.\d{1,3}){3}')
    languages = diagnostic(NAME_SCREEN_LANGUAGE, r'[a-z]{2,3}(-[A-Za-z0-9]{2,8})?')
    # Firmware from before the languages (0.2.75 and older) has no such sensor: it speaks English, with fewer letters.
    speaks = {item.get('device_id') for item in registry
              if item.get('platform') == 'esphome' and item.get('original_name') in NAME_SCREEN_LANGUAGE}
    screens = []
    for item in registry:
        eid = item['entity_id']
        if not (item.get('platform') == 'esphome' and eid.startswith('text.') and item.get('original_name') in NAME_TILE_SETTINGS and not item.get('disabled_by')):
            continue
        device = device_map.get(item.get('device_id'), {})
        state = states.get(eid, {})
        area = area_map.get(item.get('area_id') or device.get('area_id'), '')
        firmware = versions.get(item.get('device_id'), 'unknown')
        screens.append({'id': eid, 'name': device.get('name_by_user') or device.get('name') or eid,
                        'device_id': item.get('device_id'),
                        'firmware': firmware,
                        # What feature gates go by: the sensor, or Home Assistant's device registry while the screen is
                        # offline or restarting (app 0.2.78).
                        'firmware_known': known_firmware(firmware, device.get('sw_version')),
                        'board': boards.get(item.get('device_id'), 'unknown'),
                        # What the screen says it looks like (firmware 0.2.80): the canvas and the cells of a
                        # page. The editor draws its mockup from this instead of guessing from the board.
                        # (`layout` is taken: that is the screen's tiles.)
                        'shape': parse_shape(shapes.get(item.get('device_id'))),
                        # What this screen can do with its backlight, in its own words (firmware 0.2.99).
                        'features': features.get(item.get('device_id')),
                        'node': nodes.get(item.get('device_id')), 'ip': addresses.get(item.get('device_id')),
                        'language': languages.get(item.get('device_id')),
                        'language_sensor': item.get('device_id') in speaks,
                        'device': device.get('name') or '',
                        'area': area, 'online': state.get('state') not in (None, 'unknown', 'unavailable'),
                        # What the screen reports (a word of the firmware's protocol), or ours in English, which the editor
                        # shows in its own language (app 0.2.90).
                        'status': state.get('state', english('screen.settings.not_connected'))})
    return screens

def discover(registry, states, devices, areas):
    """(screens, entities): the paired screens and every entity a tile or the top bar can show."""
    device_map = {d['id']: d for d in devices}
    area_map = {a['area_id']: a['name'] for a in areas}
    screens = discover_screens(registry, states, devices, areas)
    entities = []
    for item in registry:
        eid = item['entity_id']
        tile = entity_id(eid)
        if not (tile or header_entity(eid)) or item.get('disabled_by'):
            continue
        device = device_map.get(item.get('device_id'), {})
        state = states.get(eid, {})
        area = area_map.get(item.get('area_id') or device.get('area_id'), '')
        entities.append({'id': eid, 'name': state.get('attributes', {}).get('friendly_name') or item.get('name') or item.get('original_name') or eid,
                         'device': device.get('name_by_user') or device.get('name') or '', 'area': area,
                         'state': state.get('state', 'unavailable'),
                         'icon': tile_icons.ha_icon(state.get('attributes')) or tile_icons.default_glyph(eid, state.get('state'), state.get('attributes'), item),
                         # Top-bar-only domains (a phone's tracker, a lock) stay out of the tile picker.
                         **({} if tile else {'tile': False})})
    # YAML entities may not have an entity-registry entry.
    registered = {e['id'] for e in entities}
    in_registry = {r['entity_id'] for r in registry}
    for eid, state in states.items():
        tile = entity_id(eid)
        if (tile or header_entity(eid)) and eid not in registered and eid not in in_registry:
            entities.append({'id': eid, 'name': state.get('attributes', {}).get('friendly_name', eid), 'device': '', 'area': '', 'state': state['state'],
                             'icon': tile_icons.ha_icon(state.get('attributes')), **({} if tile else {'tile': False})})
    return screens, sorted(entities, key=lambda e: e['name'].casefold())

def installation_yaml(data):
    board, name, friendly = data.get('board'), data.get('name'), data.get('friendly_name')
    if board not in BOARD_KEYS or not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,29}', name):
        raise ValueError(t('addon.errors.firmware.board_and_name'))
    if not isinstance(friendly, str) or not friendly.strip() or len(friendly) > 60:
        raise ValueError(t('addon.errors.firmware.friendly_name'))
    quote = lambda s: json.dumps(s, ensure_ascii=False)
    # The language of the screen's texts (app 0.2.90): Settings -> Language & region, which ESP Screens passes in.
    language = data.get('language') if isinstance(data.get('language'), str) and re.fullmatch(r'[a-z]{2,3}(-[A-Za-z0-9]{2,8})?', data.get('language')) else 'en'
    # Which way the screen hangs (app 0.2.107). The board file already lays its panel out lying down, so only a
    # screen that stands up needs a line: a landscape profile then reads exactly like every profile written before
    # this choice existed, and there is one less number in the file that can go stale when a board file changes.
    # Square glass has no second way to hang, and its two orientations carry the same angle, so asking for portrait
    # there writes nothing and builds the same screen.
    orientation = data.get('orientation', 'landscape')
    if orientation not in ORIENTATIONS:
        raise ValueError(t('addon.errors.firmware.orientation'))
    sides = (SHAPES.get(board, {}).get('orientations') or {})
    turn = (sides.get(orientation) or {}).get('rotation')
    lying = (sides.get('landscape') or {}).get('rotation')
    rotation_line = f'  LVGL_ROTATION: {quote(str(turn))}\n' if turn is not None and turn != lying else ''
    # The board's other choices (app 0.2.129): a part that differs between boards sold under one name, like the CYD's
    # display controller, offered in boards.yaml with the board file's own value first. That one writes nothing, like
    # lying down; another is a line of the screen's own substitutions, which win over the board file's.
    offered = SHAPES[board].get('catalog', {}).get('choices') or {}
    chosen = data.get('choices') or {}
    if not isinstance(chosen, dict) or any(key not in offered or value not in offered[key] for key, value in chosen.items()):
        raise ValueError(t('addon.errors.firmware.choice'))
    choice_lines = ''.join(f'  {key}: {quote(chosen[key])}\n' for key in offered if chosen.get(key, offered[key][0]) != offered[key][0])
    # An OTA password, not yet `ota: encryption:` with the api key: ESPHome before 2026.9 refuses that, and the owner's
    # ESPHome Device Builder may still be older (docs/RELEASING.md, Compatibility 0.2.89).
    key, ota, ap = base64.b64encode(secrets.token_bytes(32)).decode(), secrets.token_urlsafe(24), secrets.token_urlsafe(12)
    return f'''# Keep this file safe: it contains the unique keys for this screen.
# Wi-Fi comes from the secrets.yaml of ESPHome Device Builder.
substitutions:
  DEVICE_NAME: {quote(name)}
  DEVICE_FRIENDLY_NAME: {quote(friendly.strip())}
  LANGUAGE: {quote(language)}
{rotation_line}{choice_lines}
esphome:
  name: {quote(name)}
  friendly_name: {quote(friendly.strip())}

packages:
  display:
    url: {REPO}
    ref: {REF}
    files: [packages/{board}.yaml]
    refresh: 0s
  local_overrides: !include {name}.local.yaml

api:
  encryption:
    key: {quote(key)}
ota:
  - platform: esphome
    password: {quote(ota)}
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  power_save_mode: none
  ap:
    ssid: {quote(name + ' Setup')}
    password: {quote(ap)}
captive_portal:
'''
