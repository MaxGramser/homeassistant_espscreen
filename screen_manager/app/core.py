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
import catalogue
import tile_icons

# The entity types a tile shows, as the tile catalogue has them (catalogue/*.yaml, catalogue.py): a type exists here only
# where it has a file there, which comes after the firmware's UI for it (docs/CATALOGUE.md).
DOMAINS = catalogue.DOMAINS
# Built-in cards without a Home Assistant entity; firmware 0.2.14+ renders them. The names in English: a screen gets them in
# its language and the editor in its own (builtin_name, app 0.2.90).
BUILTIN = {'screen.clock': 'Clock', 'screen.nightstand': 'Bedside clock', 'screen.settings': 'Settings', 'screen.map': 'Map', 'screen.energy': 'Energy', **{f'screen.page_{n}': f'Go to page {n}' for n in range(1, 33)}}
# A navigation tile (firmware 0.2.62+): screen.page_<n> goes to page n, up to page 32 on a board that holds that many
# (firmware 0.34.0+); whether the screen has page n is the screen's Grid's to say. Firmware 0.2.65+ takes the same one on several
# pages (a "Back to page 1" on every page), firmware 0.16.0+ any entity on several tiles (GitHub #83) but the bedside
# clock, whose keys name it by its entity.
PAGE_TILE = 'screen.page_'
PAGE_TILE_REPEAT_MIN_FIRMWARE = (0, 2, 65)
ENTITY_REPEAT_MIN_FIRMWARE = (0, 16, 0)
# A screen without a title (firmware 0.17.0+): the top bar shows its home key alone. Older firmware said "Home" instead.
NO_TITLE_MIN_FIRMWARE = (0, 17, 0)
# Eight pages on every grid (firmware 0.18.0+), at most 64 tiles over all of them; older firmware had 64 / cells pages
# (Grid.legacy_pages), three on a 5 x 4 grid. It says so in its hello (`free_pages`, page_delivery.Sender).
FREE_PAGES_MIN_FIRMWARE = (0, 18, 0)

def page_target(entity):
    """The page a navigation tile opens, counted from one; 0 for any other entity."""
    return int(entity[len(PAGE_TILE):]) if isinstance(entity, str) and entity in BUILTIN and entity.startswith(PAGE_TILE) else 0

def builtin_name(entity, text=screen_t):
    """A built-in card's name in the screens' language, for the tile on the screen; `text=t` gives the editor's."""
    page = page_target(entity)
    if page:
        return text('addon.screen.builtin.page', page=page)
    # The settings tile is named like the settings page it opens.
    if entity == 'screen.nightstand':
        return text('addon.screen.builtin.nightstand')
    if entity == MAP_TILE:
        return text('addon.screen.builtin.map')
    if entity == ENERGY_TILE:
        return text('addon.screen.builtin.energy')
    return text('screen.settings.title' if entity == 'screen.settings' else 'addon.screen.builtin.clock')
# A camera or an image entity opens full screen on a Guition with firmware 0.2.57+ (camera_feed.py).
CAMERA_DOMAINS = frozenset(('camera', 'image'))
CAMERA_MIN_FIRMWARE = (0, 2, 57)
# A live picture on a camera tile ("display": "live", app 0.2.91): firmware from here asks for the page's strip.
LIVE_MIN_FIRMWARE = (0, 2, 77)
# The paces a live tile may choose, in seconds (5 and 10 since app 0.3.13; every firmware with live pictures takes
# 5 to 3600), and the one it has when it chose none.
LIVE_REFRESH = tuple(catalogue.of_type('camera')['picture']['refresh'])
LIVE_REFRESH_DEFAULT = 15
# A media tile's album cover in the icon's place ("display": "cover", app 0.2.92): the same strip, firmware from here.
COVER_TILE_MIN_FIRMWARE = (0, 2, 78)
# The calm dial and the flip clock (firmware 0.3.6+). An older screen draws either as the digital clock, so a layout
# with one is sent as it is; the editor says so.
CLOCK_FACES_MIN_FIRMWARE = (0, 3, 6)
CLOCK_DEFAULT_DISPLAY = 'dial'
# The bedside clock (firmware 0.8.0+): a clock that always takes the whole page, digits as large as the page allows and
# up to three keys under them, each a tile of its own (a lamp, a temperature, a lock). It starts without a card behind
# it, so the digits stand on the dark page at night; any background can still be chosen.
NIGHTSTAND = 'screen.nightstand'
NIGHTSTAND_MIN_FIRMWARE = (0, 8, 0)
NIGHTSTAND_KEYS = 3
# A key is a tile without a cell of its own (app 0.4.12): in the compiled tiles it names the tile it stands under
# (`in`, that tile's entity: the bedside clock, which is on a screen once) and its place there (`key`, from 0), and it follows the placed
# tiles. The tiles that hold keys and how many each holds; a key takes a tile's own settings but its size, and any
# domain but a picture, which has no round form.
KEY_HOLDERS = {NIGHTSTAND: NIGHTSTAND_KEYS}
# A key's name under its circle can be hidden (`overlay`: "none", firmware 0.17.0+), as a picture's name on it can.
KEY_OPTIONS = ('icon', 'tap', 'action', 'guard', 'overlay')
KEY_DOMAINS = catalogue.key_domains()

def is_key(tile):
    """A key of a bedside clock: a tile that stands under another instead of in a cell."""
    return 'in' in tile

def placed(tiles):
    """The tiles that have a cell: every tile but the keys."""
    return [tile for tile in tiles if 'in' not in tile]

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
# The shared firmware of this app release: packages/core.yaml's SCREEN_FIRMWARE_VERSION, what every board builds
# unless its own board file went ahead with a fix for that board alone (firmware_target, docs/BOARD_RELEASES.md). The
# middle number is the core: the feature gates below name a shared X.Y.0, so a feature always ships with a new core.
FIRMWARE_VERSION = '0.51.0'
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
# The first firmware of the three types below is the `firmware:` of their file in catalogue/, named here for the tests.
# An alarm panel as a tile with its card and keypad (components/smart_display/alarm_panel.h); older firmware refuses the
# domain, so a layout with one waits for the update.
ALARM_MIN_FIRMWARE = catalogue.parse_version(catalogue.of_type('alarm_control_panel')['firmware'])
# A lock as a tile with its card (components/smart_display/lock_panel.h): locks with one tap, unlocks after a second, the
# alarm panel's keypad for a code. Older firmware refuses the domain, so a layout with one waits for the update.
LOCK_MIN_FIRMWARE = catalogue.parse_version(catalogue.of_type('lock')['firmware'])
# How far a lock's tile may go (the `guard` option): unlock after a second tap, or lock only.
LOCK_GUARDS = tuple(catalogue.of_type('lock')['guards'])
# An automation as a tile (GitHub #62): a tap switches it on or off and holding runs its actions, or with the tap option
# `run` the other way round. Older firmware refuses the domain, so a layout with one waits for the update.
AUTOMATION_MIN_FIRMWARE = catalogue.parse_version(catalogue.of_type('automation')['firmware'])
ATTRS = frozenset('brightness percentage current_position current_tilt_position current_temperature temperature target_temp_low target_temp_high current_humidity min_temp max_temp target_temp_step supported_color_modes hvac_modes hvac_action hs_color color_temp_kelvin min_color_temp_kelvin max_color_temp_kelvin fan_speed_list unit_of_measurement battery_level fan_speed volume_level is_volume_muted media_title options min max step temperature_unit supported_features device_class next_rising next_setting finishes_at duration remaining humidity wind_speed wind_speed_unit apparent_temperature fan_modes swing_modes fan_mode swing_mode effect code_format code_arm_required changed_by assumed_state activity_list current_activity'.split())
# A humidifier's own (firmware 0.42.0+): the range of the humidity it may be set to, its modes and the one it is in,
# and what it is doing. Other domains use the same names for other things (an automation's `mode`), so only a humidifier
# sends them.
HUMIDIFIER_ATTRS = frozenset('min_humidity max_humidity target_humidity_step available_modes mode action'.split())
# Attributes whose boolean value the screen needs; every other bool stays behind.
BOOL_ATTRS = frozenset(['is_volume_muted', 'code_arm_required', 'assumed_state'])


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

# Display modes per domain, as the catalogue has them; a type that only has standard and watch (large value) is left out.
DISPLAYS = {domain: tuple(catalogue.display_keys(domain)) for domain in sorted(DOMAINS)
            if catalogue.display_keys(domain) != ['standard', 'watch']}
# A live picture on a 1x2 or 2x2 tile fills the card (app 0.3.8, firmware 0.3.3): cut to fill it or whole on black, with
# its name on it or nothing. The first choice of each is the default and is never stored.
PICTURE_OPTIONS = {key: tuple(catalogue.of_type('camera')['picture'][key]) for key in ('fit', 'overlay')}
# A map on a person tile ("display": "map", app 0.4.33, docs/MAP.md): the app draws the card and it travels in the page's
# picture strip like a live camera. How it frames its people and how far out it reaches; the first choice of each is the
# default and is never stored. `map` lists who rides along beside the tile's own person, people and device trackers.
# None of it reaches a screen (screen_options): the screen gets pixels, never a place.
MAP_CARD = catalogue.of_type('person')['map']
MAP_OPTIONS = {key: tuple(MAP_CARD[key]) for key in ('framing', 'distance', 'follow', 'markers', 'names', 'zones', 'streets', 'look')}
# The map of the screen's own cards (app 0.4.36, firmware 0.21.0): the same map without a person of its own, following
# everyone Home Assistant knows the place of or the people and trackers chosen (`follow`).
MAP_TILE = 'screen.map'
MAP_TILE_MIN_FIRMWARE = (0, 21, 0)
# The energy card (app 0.4.77, firmware 0.47.0): the house's power now, drawn as Home Assistant's own live view and
# power-flow-card-plus draw it, from the Energy settings (energy_flow.py). It is a diagram and nothing else.
ENERGY_TILE = 'screen.energy'
ENERGY_MIN_FIRMWARE = (0, 47, 0)
MAP_DOMAINS = frozenset(MAP_CARD['with'])
MAP_MAX_ENTITIES = MAP_CARD['max']
MAP_OWN = ('map', *MAP_OPTIONS)
# Displays that only work on a double-width card (`wide` in the catalogue).
WIDE_ONLY = tuple(sorted({item['key'] for entry in catalogue.TYPES.values() for item in entry['displays'] if item.get('wide')}))

# ----- The grid of a screen's pages -----
# A page is a grid of cells, and each screen has its own: two columns of three on the boards that shipped first,
# three by three on a 800 x 480 panel, whatever a later board's glass asks for. A tile's `slot` is its absolute
# cell (page * cells + row * columns + column); a wide tile starts in a column that has a cell to its right and
# covers both; a full tile (firmware 0.2.62+) starts a page and covers every cell of it. Empty cells are allowed.
#
# The rules are the firmware's (components/smart_display/runtime_model.h): the same pages whatever the grid, and never
# more tiles on one screen than its board takes, so a page need not be full (firmware 0.18.0+). That is eight pages and
# 64 tiles, or what the screen says in its hello on a board with more (firmware 0.34.0+, page_delivery.Sender: max_pages,
# max_tiles; Manager.ceilings). Older firmware had as many pages as 64 tiles fill (legacy_pages): seven of nine cells,
# three of twenty. Everything that counts cells, rows, pages or tiles goes through the screen's Grid
# (`Manager.grid_of(screen)`); DEFAULT_GRID is the two by three of the first boards, which is also what every layout
# stored before app 0.2.94 was made on.
FIRMWARE_MAX_PAGES = 8
FIRMWARE_MAX_TILES = 64
# The items one page's top bar holds: six, or what the screen's hello says on a board with room for more (firmware 0.34.0+,
# max_bar_items); the glass's width decides how many of them show (header_bar::place, the editor's topbar.ts).
FIRMWARE_MAX_BAR_ITEMS = 6
# The most any board may state (page_protocol.h): what a stored layout is held to when no screen is there to ask, so a
# layout made for a board with more pages still loads whatever is connected, and a save is held to the screen's own.
STORE_MAX_PAGES = 32
STORE_MAX_TILES = 1024
STORE_MAX_BAR_ITEMS = 16

class Grid:
    __slots__ = ('columns', 'rows', 'page_cap', 'tile_cap', 'bar_cap')

    def __init__(self, columns=2, rows=3, pages=FIRMWARE_MAX_PAGES, tiles=FIRMWARE_MAX_TILES, bar_items=FIRMWARE_MAX_BAR_ITEMS):
        columns, rows = int(columns), int(rows)
        if columns < 1 or rows < 1 or columns * rows > FIRMWARE_MAX_TILES:
            raise ValueError(f'no screen holds a page of {columns} x {rows} cells')
        self.columns, self.rows = columns, rows
        # The pages and tiles the screen takes (its hello, for_firmware); the cells alone say nothing about them any more.
        self.page_cap = max(1, min(STORE_MAX_PAGES, int(pages)))
        self.tile_cap = max(1, min(STORE_MAX_TILES, int(tiles)))
        self.bar_cap = max(1, min(STORE_MAX_BAR_ITEMS, int(bar_items)))

    def with_ceilings(self, pages, tiles, bar_items=FIRMWARE_MAX_BAR_ITEMS):
        """The same cells with these ceilings (a screen's hello, Manager.ceilings)."""
        return Grid(self.columns, self.rows, pages, tiles, bar_items)

    @property
    def bar_items(self):
        """The items one page's top bar takes."""
        return self.bar_cap

    def for_firmware(self, version):
        """The same cells with the pages and tiles firmware `version` takes (page_limit): this grid's own from 0.18.0,
        fewer pages and 64 tiles before."""
        new = (version or (0, 0, 0)) >= FREE_PAGES_MIN_FIRMWARE
        return Grid(self.columns, self.rows, page_limit(version, self), self.tile_cap if new else FIRMWARE_MAX_TILES,
                    self.bar_cap if new else FIRMWARE_MAX_BAR_ITEMS)

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
        return self.page_cap

    @property
    def legacy_pages(self):
        """The pages firmware before 0.18.0 takes on this grid: as many as 64 tiles fill, eight at most."""
        return min(FIRMWARE_MAX_PAGES, FIRMWARE_MAX_TILES // self.slots)

    @property
    def max_slots(self):
        return self.pages * self.slots

    @property
    def max_tiles(self):
        return min(self.tile_cap, self.max_slots)

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
        span = span_of(size)
        if span: return span
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
# A span (app 0.4.32, firmware 0.19.0): "CxR", a tile of C columns and R rows, set with the tile's handles. The five
# names keep their sizes; a span is every other rectangle smaller than the grid, and a screen says in its hello which
# of them its grid takes (tile_sizes), so an older screen is never sent one.
SPAN = re.compile(r'^([1-9])x([1-9])$')

def span_of(size):
    """(columns, rows) of a span such as "3x2", or None for a name or anything else."""
    found = SPAN.match(size) if isinstance(size, str) else None
    return (int(found[1]), int(found[2])) if found else None

def span_offered(columns, rows, grid):
    """Whether a grid takes this rectangle as a span: smaller than the grid, and more than the names say (2 x 2)."""
    return columns <= grid.columns and rows <= grid.rows and (columns, rows) != (grid.columns, grid.rows) and (columns > 2 or rows > 2)

def is_size(size):
    return size in TILE_SIZES_ON_SCREEN or span_of(size) is not None

def size_rows(size):
    """How many rows a size is high, apart from the whole page: tall and square two, a span its own."""
    span = span_of(size)
    return span[1] if span else 2 if size in ('tall', 'square') else 1

def size_columns(size):
    """How many columns a size is wide, apart from the whole page and a wide tile's grid: a span its own."""
    span = span_of(size)
    return span[0] if span else 2 if size in ('wide', 'square') else 1

def tile_size(tile):
    """The symbolic presentation size; dimensions are resolved by the screen's grid."""
    size = tile.get('options', {}).get('size', 'single')
    return size if is_size(size) else 'single'

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
# The direct controls per type, as the catalogue has them, the default first, with their words in English (the Claude
# skill writes them; the editor gets them in its language, controls_catalogue).
CONTROLS = {domain: tuple((key, english(f'addon.labels.controls.{domain}.{key}')) for key in catalogue.control_keys(domain))
            for domain in sorted(DOMAINS) if catalogue.control_keys(domain)}

def controls_catalogue():
    """Editor choices per domain: the default first, then 'none'; labels in the editor's language (app 0.2.90)."""
    return {domain: {'default': choices[0][0], 'choices': [{'key': key, 'label': t(f'addon.labels.controls.{domain}.{key}')} for key, _ in choices]
                     + [{'key': 'none', 'label': t('addon.labels.controls.none')}]}
            for domain, choices in CONTROLS.items()}

def resolve_controls(tile):
    """Control set a card shows on the screen, or None (catalogue.resolve_controls: the chosen one or its type's default,
    and on a card one row high what fits there)."""
    return catalogue.resolve_controls(tile, span_of)

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
# What a screen with 4 MB of flash says about its partition table (firmware 0.33.1 of those boards, app 0.4.56;
# components/flash_layout, docs/FLASH_LAYOUT.md): "wide", ready for the wide one ("widen", or "widen_next" when it
# takes one more update first), or "old" and "other" when it keeps what it has. No other board has the sensor.
NAME_SCREEN_FLASH = ('Screen flash',)
SCREEN_ENTITY_NAMES = frozenset(NAME_TILE_SETTINGS + NAME_SCREEN_FIRMWARE + NAME_GUITION_TYPE + NAME_DEVICE_NAME + NAME_IP_ADDRESS
                                + NAME_SCREEN_LANGUAGE + NAME_SCREEN_LAYOUT + NAME_SCREEN_BOARD + NAME_SCREEN_FEATURES
                                + NAME_SCREEN_FLASH)

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

def firmware_target(board):
    """The firmware a screen of this board is offered (app 0.3.21): what a build of the board makes today, boards.json's
    `firmware`, and never less than the shared FIRMWARE_VERSION; an unknown board gets the shared one. A board that went
    ahead with a fix of its own (its board file sets SCREEN_FIRMWARE_VERSION) is the only one offered that update. A
    number reads as core and board (firmware 0.4.0+): 0.4.2 is core 4 with the board's second fix, so it passes the
    gates of core 4 and no newer one."""
    shared = parse_firmware(FIRMWARE_VERSION)
    own = parse_firmware((SHAPES.get(board) or {}).get('firmware')) if isinstance(board, str) else None
    return '.'.join(map(str, max(shared, own) if own else shared))

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

def update_in_tessera(screen):
    """Whether this screen's next update has to come from Tessera itself (app 0.4.82): its board builds for the wide
    partition table (boards.json `wide_slots`) and the screen does not say it has that table yet. Its firmware no longer
    fits the update slot of ESPHome's own table, so an update from ESPHome Device Builder is refused by the screen; only
    Tessera moves it to the wide table on the way (docs/FLASH_LAYOUT.md). A screen that is away says nothing, and one with
    a table of its owner's own ('other') is left as it is."""
    if not isinstance(screen, dict) or not screen.get('online'):
        return False
    if not SHAPES.get(board_of(screen), {}).get('wide_slots'):
        return False
    return screen.get('flash') in (None, 'old', 'widen', 'widen_next')

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

def has_battery(screen, said=()):
    """Whether this screen has a battery the top bar can show (firmware 0.41.0, docs/BATTERY.md): the word `battery` in
    its Screen features or in its hello (`said`), which a battery in its own Override YAML gives too, or its board's
    `battery` in boards.json, so a Tab5 that still runs older firmware is offered the item with the note to update.
    Unlike the other abilities a board this app does not know has none."""
    if BATTERY_FEATURE in (features_of(screen) or ()) or BATTERY_FEATURE in (said or ()):
        return True
    return bool(SHAPES.get(board_of(screen), {}).get('battery'))

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
    # The rows its own YAML was built with (a Guition with four rows, app 0.4.31), for the grid lying down, which on
    # square glass is the grid either way.
    rows = screen.get('grid_rows')
    if type(rows) is int and rows > 0 and shape.get('width', 0) >= shape.get('height', 0):
        shape = {**shape, 'rows': rows}
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

def page_limit(version, grid=DEFAULT_GRID):
    """How many pages firmware `version` (a tuple, or None when unknown) takes on a screen with this grid: the grid's
    own from firmware 0.18.0 (eight, or what the screen's hello says), as many as 64 tiles fill before."""
    return grid.pages if (version or (0, 0, 0)) >= FREE_PAGES_MIN_FIRMWARE else grid.legacy_pages

def tile_limit(version, grid=DEFAULT_GRID):
    """How many tiles firmware `version` (a tuple, or None when unknown) takes on a screen with this grid: the grid's
    ceiling over its pages (firmware 0.18.0+: 64, or what the screen's hello says), one per cell of its pages (0.2.62+),
    twenty from 0.2.7, ten before."""
    version = version or (0, 0, 0)
    if version >= FREE_PAGES_MIN_FIRMWARE: return grid.max_tiles
    return grid.legacy_pages * grid.slots if version >= FULL_PAGE_MIN_FIRMWARE else LEGACY_MAX_TILES if version >= TWENTY_TILES_MIN_FIRMWARE else FIRST_MAX_TILES

CLIMATE_RANGE_MIN_FIRMWARE = (0, 19, 0)

def tile_cost(tile, memory):
    """What one tile takes inside a screen's chip (firmware 0.34.0+, docs/TILE_MEMORY.md), by the tile catalogue's
    price for its type (catalogue `memory`), what its own choices add (a tap that runs its own action, a second line set to
    one of its values), and on a board without PSRAM the tile itself and, where it keeps one, its block of extras, whose
    sizes the screen gave in its hello (page_delivery.memory_of). The screen counts the same way (tile_memory::cost), and
    so does the editor (web/src/model/memory.ts): tests/fixtures/memory-conformance.json holds the cases."""
    entity = str(tile.get('entity', ''))
    entry = catalogue.CARD_MEMORY.get(entity) or catalogue.MEMORY.get(entity.split('.', 1)[0], catalogue.DEAREST)
    options = tile.get('options') or {}
    action = options.get('tap') == 'action'
    line = isinstance(options.get('sub'), str) and options['sub'].startswith('attr:')
    cost = entry['bytes'] + (catalogue.CHOICE_MEMORY['action'] if action else 0) + (catalogue.CHOICE_MEMORY['line'] if line else 0)
    if not memory['psram']:
        cost += memory['tile'] + (memory['extra'] if entry['extras'] or action or line else 0)
    return cost

def page_cost(page, memory):
    """What one page of a pages-v2 document takes inside the screen's chip: the catalogue's price of a page (its title)
    and of each item of its top bar that shows an entity (its text), and on a board without PSRAM the page's own record,
    whose size the screen gave (`page`). The screen counts its text and moment items, which are the entity items."""
    entities = sum(1 for item in page.get('topbar', {}).get('trailing', []) if isinstance(item, dict) and item.get('type') == 'entity')
    return (catalogue.CHOICE_MEMORY['page'] + entities * catalogue.CHOICE_MEMORY['bar_text']
            + (0 if memory['psram'] else memory.get('page', 0)))

def layout_cost(tiles, memory, pages=()):
    """What `tiles` (a flat layout's, the keys of a bedside clock included) and the document's `pages` take together
    inside the screen's chip."""
    return sum(tile_cost(tile, memory) for tile in tiles) + sum(page_cost(page, memory) for page in pages)

def firmware_features(version, grid=DEFAULT_GRID):
    """What the editor may offer a screen with firmware `version` (a tuple, or None): the tile limit, full-page and
    navigation tiles, the same navigation tile on several pages, any entity on several tiles and a screen without a
    title."""
    version = version or (0, 0, 0)
    return {'tile_limit': tile_limit(version, grid), 'page_limit': page_limit(version, grid), 'full_page': version >= FULL_PAGE_MIN_FIRMWARE,
            'page_tiles_repeat': version >= PAGE_TILE_REPEAT_MIN_FIRMWARE,
            'entity_tiles_repeat': version >= ENTITY_REPEAT_MIN_FIRMWARE, 'no_title': version >= NO_TITLE_MIN_FIRMWARE,
            # A thermostat with only a range on its -/+ (drawn_controls sends older screens the tile without them).
            'climate_range': version >= CLIMATE_RANGE_MIN_FIRMWARE}

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
# The screensaver (screen_saver.py): what the screen shows in standby instead of its dimmed tiles; its hello lists it.
SCREENSAVER_MIN_FIRMWARE = (0, 29, 0)
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
HEADER_MAX_ITEMS = FIRMWARE_MAX_BAR_ITEMS
# Items the screen draws on its own clock, without Home Assistant; their labels are in the translations (header_bar.catalogue,
# app 0.2.90).
HEADER_BUILTIN = ('clock', 'analog', 'date')
# The screen's own items (firmware 0.38.0, GitHub #130): its Wi-Fi signal, and a mark while Home Assistant or Tessera is
# away. The screen reads both itself, so they stay when Home Assistant goes; a screen gets them once its hello names
# BAR_STATUS_FEATURE, and an older one simply goes without (header_bar.message).
HEADER_STATUS = ('wifi', 'link', 'battery')
BAR_STATUS_FEATURE = 'bar_status'
BAR_STATUS_MIN_FIRMWARE = (0, 38, 0)
# What the Wi-Fi item shows beside its bars, and when it shows.
WIFI_CONTENTS = ('icon', 'percent', 'dbm')
WIFI_SHOWS = ('always', 'weak')
# The battery item (firmware 0.41.0, docs/BATTERY.md): only a screen with a battery has it, which it says in its hello
# (BATTERY_FEATURE) and which its board says before it ever connected (boards.json `battery`). It shows Home Assistant's
# battery icon alone or with the percentage, always or only while the battery runs low.
BATTERY_FEATURE = 'battery'
BATTERY_MIN_FIRMWARE = (0, 41, 0)
BATTERY_CONTENTS = ('icon', 'percent')
BATTERY_SHOWS = ('always', 'low')
# Only shown, never controlled: the top bar takes these besides every tile domain.
HEADER_ONLY_DOMAINS = frozenset('device_tracker zone counter event input_datetime input_text water_heater humidifier'.split())
# What an entity item shows: its status, when it last changed, or its icon alone (GitHub #144, any firmware with a top bar:
# the screen draws an item without text as its icon).
HEADER_CONTENTS = ('state', 'last_changed', 'icon')
HEADER_SHOWS = ('always', 'active')

def header_entity(value):
    return (isinstance(value, str) and len(value) <= 120 and re.fullmatch(r'[a-z0-9_]+\.[a-z0-9_]+', value) is not None
            and value.split('.')[0] in (DOMAINS - {'screen'} - CAMERA_DOMAINS) | HEADER_ONLY_DOMAINS)

def header_items(layout):
    """Items the top bar shows: the stored ones, else what firmware before the top bar drew (the clock)."""
    if 'header' in layout:
        return layout['header']['items']
    return [{'type': 'clock'}] if layout.get('settings', {}).get('show_clock', True) else []

def validate_header(data, most=HEADER_MAX_ITEMS):
    """A top bar: at most `most` items, six unless the screen takes more (Grid.bar_items, firmware 0.34.0+)."""
    if not isinstance(data, dict) or set(data) - {'items'} or not isinstance(data.get('items'), list):
        raise ValueError(t('addon.errors.top_bar.invalid'))
    if len(data['items']) > most:
        raise ValueError(t('addon.errors.top_bar.full', n=most))
    items, seen = [], set()
    for item in data['items']:
        kind = item.get('type') if isinstance(item, dict) else None
        if kind in HEADER_BUILTIN or kind == 'link':
            if set(item) != {'type'}:
                raise ValueError(t('addon.errors.top_bar.invalid_setting'))
            clean = {'type': kind}
        elif kind in ('wifi', 'battery'):
            if set(item) - {'type', 'content', 'show'}:
                raise ValueError(t('addon.errors.top_bar.unknown_setting'))
            clean = {'type': kind, 'content': item.get('content', 'icon'), 'show': item.get('show', 'always')}
            contents, shows = (WIFI_CONTENTS, WIFI_SHOWS) if kind == 'wifi' else (BATTERY_CONTENTS, BATTERY_SHOWS)
            if clean['content'] not in contents or clean['show'] not in shows:
                raise ValueError(t('addon.errors.top_bar.invalid_setting'))
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
            # An item that shows its icon alone needs one.
            if clean['content'] == 'icon' and clean['icon'] == 'none':
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

def map_entities(value, own):
    """Who rides along on a map tile, checked: people and device trackers, each once, never the tile's own person, so
    the card never draws more than MAP_MAX_ENTITIES. The list stays in the app (screen_options) and a map is drawn from
    the saved tile alone (server.Manager.answer_live)."""
    # The map tile has no person of its own, so all eight may be chosen.
    if not isinstance(value, list) or len(value) > MAP_MAX_ENTITIES - (0 if own == MAP_TILE else 1):
        raise ValueError(t('addon.errors.layout.map_entities', n=MAP_MAX_ENTITIES))
    for entity in value:
        if not isinstance(entity, str) or not ACTION_NAME.fullmatch(entity) or entity.split('.')[0] not in MAP_DOMAINS \
                or entity == own or value.count(entity) > 1:
            raise ValueError(t('addon.errors.layout.map_entities', n=MAP_MAX_ENTITIES))
    return list(value)

def repeated_entities(tiles):
    """True when any other entity is on the screen more than once, as tiles or keys (firmware 0.16.0+)."""
    others = [tile['entity'] for tile in tiles if not page_target(tile['entity'])]
    return len(others) != len(set(others))

def min_firmware(layout):
    """Oldest firmware that still accepts this layout; None when any version works. Every feature the layout uses names
    the firmware it needs, and the layout needs the newest of them: a tilting blind (0.3.1) beside an alarm panel
    (0.3.3) needs 0.3.3, which returning the first match got wrong before firmware 0.5.0."""
    tiles = layout['tiles']
    domains = {t['entity'].split('.')[0] for t in tiles}
    options = [t.get('options', {}) for t in tiles]
    # What each tile's type and chosen options ask (the catalogue: a type's `firmware`, an option's screen requirement
    # without an `else`), and what the layout as a whole asks.
    gates = [(True, version) for tile in tiles for version, _ in catalogue.gates(tile)] + [
        (any(t['entity'] == NIGHTSTAND or is_key(t) for t in tiles), NIGHTSTAND_MIN_FIRMWARE),
        (repeated_page_tiles(tiles), PAGE_TILE_REPEAT_MIN_FIRMWARE),
        (repeated_entities(tiles), ENTITY_REPEAT_MIN_FIRMWARE),
        (layout.get('title') == '', NO_TITLE_MIN_FIRMWARE),
        (any(t['entity'] == MAP_TILE for t in tiles), MAP_TILE_MIN_FIRMWARE),
        (any(t['entity'] == ENERGY_TILE for t in tiles), ENERGY_MIN_FIRMWARE),
        (len(tiles) > LEGACY_MAX_TILES or any(is_full(t) or page_target(t['entity']) for t in tiles), FULL_PAGE_MIN_FIRMWARE),
        (any(t['entity'] == 'screen.settings' for t in tiles), (0, 2, 44)),
        (any(o.get('background') == 'none' for o in options), (0, 2, 16)),
        (len(tiles) > FIRST_MAX_TILES, TWENTY_TILES_MIN_FIRMWARE),
    ]
    needed = [version for used, version in gates if used]
    return max(needed) if needed else None

def one_mu(text):
    """The Greek small letter mu (U+03BC), which Home Assistant writes in "μg/m³", as the micro sign (U+00B5) the
    screens have a glyph for. ESPHome's "µs" and most integrations already use the micro sign."""
    return str(text).replace('μ', 'µ')

# Characters that only steer how the one before them is drawn: the variation selectors after an emoji's base ("❤️" is
# U+2764 U+FE0F) and the joiner between emoji. The screens have no glyph for them and LVGL draws a box for a missing
# one, so they go (app 0.4.60): firmware 0.36.0 draws the U+2764 before it as a heart.
STEERING = dict.fromkeys(map(ord, '\ufe0e\ufe0f\u200d'))

def short(value, limit):
    """A text the screen can draw, cut to `limit` bytes of UTF-8 without breaking a character."""
    return one_mu(value).translate(STEERING).encode('utf-8')[:limit].decode('utf-8', errors='ignore')

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
                      'history_hours': 'history_hours', 'refresh': 'refresh', 'fit': 'fit', 'overlay': 'overlay',
                      # How a map frames its people (app 0.4.33); who is on it is the editor's.
                      'framing': 'framing', 'distance': 'distance',
                      # A favourite (app 0.4.42): what it plays, as Home Assistant's library names it, and on which speaker.
                      'play': 'play', 'speaker': 'speaker'}
TILE_SIZES = {'full': 'full', 'fullscreen': 'full', 'full screen': 'full', 'full-screen': 'full', 'page': 'full', 'whole page': 'full',
              'wide': 'wide', 'double': 'wide', 'large': 'wide', 'big': 'wide',
              'single': 'single', 'small': 'single', 'normal': 'single', 'tall': 'tall', 'high': 'tall', 'square': 'square'}

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
        elif name == 'play':
            # What a favourite plays is an object, as the editor stores it (validate_favorite checks it).
            options[name] = value
        else:
            options[name] = str(value).strip()
    # Perform action (app 0.2.67): `action` names Home Assistant's action and `data` its fields; the tap follows.
    if data.get('action') not in (None, ''):
        options['action'] = {'action': str(data['action']).strip(), **({'data': data['data']} if isinstance(data.get('data'), dict) and data['data'] else {})}
        if data.get('tap') in (None, ''):
            options['tap'] = 'action'
    if (options.get('controls', 'none') != 'none' or options.get('display') in WIDE_ONLY) and options.get('size') not in ('tall', 'square', 'full') and span_of(options.get('size')) is None:
        options['size'] = 'wide'
    return {key: value for key, value in options.items() if value not in (None, '')}

EVENT_SPAN = re.compile(r'^([1-9])\s*[x×*]\s*([1-9])$')

def sizes_of(grid):
    """Every size this grid takes: the names that fit it, then its spans (app 0.4.32)."""
    names = ['single', 'wide', *(['tall'] if grid.rows > 1 else []), *(['square'] if grid.rows > 1 and grid.columns > 1 else []), 'full']
    return names + [f'{c}x{r}' for r in range(1, grid.rows + 1) for c in range(1, grid.columns + 1) if span_offered(c, r, grid)]

def event_size(size, grid=DEFAULT_GRID):
    """The size an event asks for on this grid (app 0.4.32): a name, or columns x rows as "3x2". A rectangle a name
    already says is that name ("2x2" is square, the whole grid full); one the grid does not take is refused, naming
    the sizes it does take."""
    if size in TILE_SIZES_ON_SCREEN:
        return size  # where it goes is checked when it is placed
    found = EVENT_SPAN.match(loose(size))
    if found:
        columns, rows = int(found[1]), int(found[2])
        if (columns, rows) == (grid.columns, grid.rows):
            return 'full'
        named = {(1, 1): 'single', (2, 1): 'wide', (1, 2): 'tall', (2, 2): 'square'}.get((columns, rows))
        if named and columns <= grid.columns and rows <= grid.rows:
            return named
        if span_offered(columns, rows, grid):
            return f'{columns}x{rows}'
    raise ValueError(t('addon.errors.events.size', size=size, sizes=', '.join(sizes_of(grid))))

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
    """The tiles of one entity in slot order: one, or several copies (a navigation tile from firmware 0.2.65, any
    entity from 0.16.0)."""
    return sorted((tile for tile in tiles if tile['entity'] == entity), key=lambda tile: tile.get('slot', 0))

def pick_copy(found, page=None, slot=None, grid=DEFAULT_GRID):
    """The copy an event means: the one covering `slot`, else the first on `page`, else the first; None when none is
    there. An event that doesn't say which acts on the first (app 0.2.78)."""
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

def run_tile_event(layout, action, data, repeat_pages=False, grid=DEFAULT_GRID, repeat_entities=False):
    """run_tile_event for the placed tiles; the keys of a bedside clock stay where they are (app 0.4.12). An event acts
    on the placed tiles of its entity; one whose entity is only a key may remove that key, like any tile, and cannot
    move it, since a key has no cell: the editor puts them under their clock. Adding such an entity puts a tile of its
    own on the screen when the firmware takes an entity twice (`repeat_entities`, 0.16.0+)."""
    keys = [dict(tile) for tile in layout.get('tiles', []) if is_key(tile)]
    entity = str(data.get('entity') or '').strip()
    key = next((tile for tile in keys if tile['entity'] == entity), None)
    if key is not None and not any(tile['entity'] == entity for tile in placed(layout.get('tiles', []))):
        if action == 'remove':
            tiles = list(layout['tiles'])
            tiles.remove(key)
            return {**layout, 'tiles': tiles}, key
        if action != 'add' or not repeat_entities:
            raise ValueError(t('addon.errors.events.key_stays', entity=entity))
    result, found = run_placed_event({**layout, 'tiles': placed(layout.get('tiles', []))}, action, data, repeat_pages, grid,
                                     repeat_entities)
    # A key whose clock went goes with it.
    there = {tile['entity'] for tile in result['tiles']}
    result['tiles'] = result['tiles'] + [tile for tile in keys if tile['in'] in there]
    return result, found

def run_placed_event(layout, action, data, repeat_pages=False, grid=DEFAULT_GRID, repeat_entities=False):
    """(layout, tile): the layout after one tile event and the tile it placed, changed, moved or removed (None for an
    order), on the screen's own grid. Raises ValueError with the sentence the log and the answer show.

    An entity can be on a screen more than once when its firmware takes that: a navigation tile from 0.2.65
    (`repeat_pages`), any other entity but the bedside clock from 0.16.0 (`repeat_entities`, GitHub #83). Add then
    always puts a new tile on the screen. Remove and move name the copy they mean by a spot it covers or by its page:
    `slot` or `page` for remove, `from_slot` or `from_page` for a move (whose `slot` and `page` say where to), and each
    mention in an order takes the next copy. Without that they act on the first copy in spot order (app 0.2.78).

    On older firmware an add of an entity that is there changes that tile, and moves it when it names another place;
    a navigation tile it takes on several pages changes the copy on the named spot or page and gets a new copy
    anywhere else."""
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
        if (not entity_id(entity) and entity not in BUILTIN) or page_target(entity) > grid.pages:
            raise ValueError(t('addon.errors.events.not_for_a_screen', entity=entity))
        # Add is add (firmware 0.16.0+): a new tile, whatever is there already; the bedside clock alone stays one.
        # Before that a navigation tile the firmware takes more than once changes the copy on the named spot or page,
        # and anywhere else a new copy goes (app 0.2.78). Every other tile, or one without a place, is the one there.
        chosen = False
        if repeat_entities and entity not in KEY_HOLDERS:
            found = None
        elif copies and repeat_pages and page_target(entity) and (page is not None or slot is not None):
            found = pick_copy(copies, page, slot, grid)
            chosen = found is not None
        was_size, had_slot = tile_size(found) if found else 'single', (found or {}).get('slot')
        options = tile_options(data, (found or {}).get('options'))
        if 'size' in options:
            options['size'] = event_size(options['size'], grid)
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

def apply_tile_event(layout, action, data, repeat_pages=False, grid=DEFAULT_GRID, repeat_entities=False):
    """The layout after one tile event (run_tile_event without the tile it acted on)."""
    return run_tile_event(layout, action, data, repeat_pages, grid, repeat_entities)[0]

def layout_snapshot(screen, layout, grid=None):
    """What a screen shows, for the sensor the app publishes in Home Assistant: the grid of its pages and one entry
    per tile with the page and the spot it is in, so an assistant can read the screen before it changes it. The
    column is `left` or `right` on a two-column screen and the column's number, counted from 1, on any other."""
    grid = grid or grid_of(screen)
    tiles = []
    holders = {tile['entity']: tile.get('slot', 0) for tile in placed(layout.get('tiles', []))}
    for tile in sorted(placed(layout.get('tiles', [])), key=lambda item: item.get('slot', 0)) + [t for t in layout.get('tiles', []) if is_key(t)]:
        slot, options = holders.get(tile['in'], 0) if is_key(tile) else tile.get('slot', 0), tile.get('options', {})
        if is_key(tile):
            # A key has no spot of its own: it names the tile it stands under and its place there, counted from 1.
            tiles.append({'entity': tile['entity'], 'name': tile.get('name') or '', 'page': grid.page_of(slot) + 1,
                          'under': tile['in'], 'key': tile['key'] + 1, 'tap': options.get('tap', 'auto')})
            continue
        tiles.append({'entity': tile['entity'], 'name': tile.get('name') or '',
                      'page': grid.page_of(slot) + 1, 'row': grid.row_of(slot), 'column': grid.column_word(slot), 'slot': slot,
                      'size': options.get('size', 'single'), 'controls': options.get('controls', ''),
                      'display': options.get('display', 'standard'), 'tap': options.get('tap', 'auto'),
                      **({'action': options['action']} if options.get('tap') == 'action' and 'action' in options else {}),
                      **({'to_page': page_target(tile['entity'])} if page_target(tile['entity']) else {})})
    snapshot = {'screen': screen.get('name', ''), 'node': screen.get('node') or '', 'title': layout.get('title', ''),
                'columns': grid.columns, 'rows': grid.rows, 'max_pages': grid.pages, 'max_tiles': grid.max_tiles,
                'pages': max([tile['page'] for tile in tiles], default=1), 'tiles': tiles}
    # A screen of more than 64 tiles (firmware 0.34.0+) can pass the 16 KB Home Assistant's recorder keeps of a state's
    # attributes: then a tile leaves out what it has by default (single, no controls, the standard display, the automatic
    # tap), which a reader takes as said. A layout that fits keeps every field, as it always did.
    if len(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')).encode()) > SNAPSHOT_MOST:
        for tile in tiles:
            for key, default in SNAPSHOT_DEFAULTS.items():
                if tile.get(key) == default: tile.pop(key)
    return snapshot

# The most a layout sensor's attributes take before its tiles leave out their defaults: under the 16384 bytes Home
# Assistant's recorder keeps, with room for the friendly name and the icon publish_layouts adds.
SNAPSHOT_MOST = 15 * 1024
SNAPSHOT_DEFAULTS = {'size': 'single', 'controls': '', 'display': 'standard', 'tap': 'auto'}

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

# A favourite's own options (app 0.4.42): what it plays, as Home Assistant's library names it, and on which speaker.
FAVORITE_OWN = ('play', 'speaker')
FAVORITE_KINDS = ('playlist', 'album', 'artist', 'track', 'podcast', 'episode', 'channel', 'genre', 'directory', 'music')

def validate_favorite(value):
    """What a favourite plays as it is stored: Home Assistant's content id and type, the title and picture its library
    gave, and the class of thing it is. ValueError when it is not one."""
    if not isinstance(value, dict) or set(value) - {'id', 'type', 'title', 'thumb', 'class'}:
        raise ValueError(t('addon.errors.layout.invalid_setting', setting='play'))
    clean = {}
    for key, limit, needed in (('id', 400, True), ('type', 64, True), ('title', 80, True), ('thumb', 600, False), ('class', 32, False)):
        item = value.get(key)
        if item is None and not needed:
            continue
        if not isinstance(item, str) or not item.strip() or len(item.encode()) > limit:
            raise ValueError(t('addon.errors.layout.invalid_setting', setting='play'))
        clean[key] = item
    thumb = clean.get('thumb')
    if thumb and not (thumb.startswith('https://') or thumb.startswith('http://') or thumb.startswith('/api/media_player_proxy/')):
        raise ValueError(t('addon.errors.layout.invalid_setting', setting='play'))
    return clean

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
    # An empty title is a screen without one (firmware 0.17.0+, min_firmware): its top bar shows the home key alone.
    if not isinstance(title, str) or len(title.encode()) > 96:
        raise ValueError(t('addon.errors.layout.title'))
    if not isinstance(tiles, list) or len(tiles) > most:
        raise ValueError(t('addon.errors.layout.tiles_max', n=most))
    clean, seen = [], set()
    for tile in tiles:
        if not isinstance(tile, dict) or not entity_id(tile.get('entity')):
            raise ValueError(t('addon.errors.layout.unsupported'))
        # A navigation tile goes to a page the screen has: eight, or what its board takes (firmware 0.34.0+).
        if page_target(tile['entity']) > (grid.pages if grid else FIRMWARE_MAX_PAGES):
            raise ValueError(t('addon.errors.layout.unsupported'))
        # Any entity may stand on several tiles (min_firmware asks 0.2.65 for a navigation tile, 0.16.0 for the rest);
        # the bedside clock appears once, as its keys name it.
        if tile['entity'] in seen and tile['entity'] in KEY_HOLDERS:
            raise ValueError(t('addon.errors.layout.once'))
        name = tile.get('name', '')
        if not isinstance(name, str) or len(name.encode()) > 80:
            raise ValueError(t('addon.errors.layout.tile_name'))
        seen.add(tile['entity'])
        item = {'entity': tile['entity'], 'name': name.strip()}
        if is_key(tile):
            if not isinstance(tile['in'], str) or type(tile.get('key')) is not int or 'slot' in tile or \
                    tile['entity'].split('.')[0] not in KEY_DOMAINS:
                raise ValueError(t('addon.errors.layout.unsupported'))
            item.update({'in': tile['in'], 'key': tile['key']})
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
            if not isinstance(options, dict) or set(options) - {'tap', 'display', 'inline', 'history_hours', 'background', 'size', 'icon', 'controls', 'action', 'refresh', 'sub', 'fit', 'overlay', 'guard', *MAP_OWN, *FAVORITE_OWN}:
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
            # The bedside clock is the whole page, always, and the only tile with keys.
            if tile['entity'] == NIGHTSTAND:
                options = {k: v for k, v in options.items() if k not in ('display', 'inline', 'controls', 'history_hours', 'sub')}
                options['size'] = 'full'
            # A key takes what a tile of its own takes, but no size, face or control: its clock decides its shape.
            if is_key(tile) and set(options) - set(KEY_OPTIONS):
                raise ValueError(t('addon.errors.layout.unknown_settings'))
            displays = DISPLAYS.get(domain, ('standard', 'watch'))
            # The map tile (app 0.4.36) is a map and nothing else, and has no slider or controls of its own.
            if tile['entity'] == MAP_TILE:
                displays = ('map',)
                options = {**{k: v for k, v in options.items() if k not in ('inline', 'controls', 'history_hours', 'sub')}, 'display': 'map'}
            # The energy card draws its diagram on every size it takes, with no face, slider or second line of its own.
            if tile['entity'] == ENERGY_TILE:
                options = {k: v for k, v in options.items() if k not in ('display', 'inline', 'controls', 'history_hours', 'sub')}
            # Every tile's taps and its type's own (run, an automation's alone: firmware 0.7.0+), from the catalogue.
            taps = tuple(catalogue.taps(domain))
            choices = {'tap': taps, 'display': displays, 'inline': ('none', 'slider')}
            if 'size' in options and not is_size(options['size']):
                raise ValueError(t('addon.errors.layout.invalid_setting', setting='size'))
            # A lock's tile (firmware 0.5.0+) unlocks after a second tap or only locks; no other tile has the choice.
            if 'guard' in options:
                if domain != 'lock' or options['guard'] not in LOCK_GUARDS:
                    raise ValueError(t('addon.errors.layout.invalid_setting', setting='guard'))
                if options['guard'] == 'confirm':
                    options = {k: v for k, v in options.items() if k != 'guard'}
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
            if options.get('display') in WIDE_ONLY and options.get('size') not in ('wide', 'square', 'full') and size_columns(options.get('size')) < 2:
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
            if options.get('inline') == 'slider' and not (catalogue.of_type(domain) or {}).get('inline'):   # a type with a small slider
                raise ValueError(t('addon.errors.layout.no_mini_slider'))
            if 'history_hours' in options and (type(options['history_hours']) is not int or options['history_hours'] not in catalogue.TILE['history_hours']):
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
            elif is_key(tile) and 'overlay' in options:
                if options['overlay'] not in PICTURE_OPTIONS['overlay']:
                    raise ValueError(t('addon.errors.layout.invalid_setting', setting='overlay'))
                if options['overlay'] == PICTURE_OPTIONS['overlay'][0]:
                    options = {key: value for key, value in options.items() if key != 'overlay'}
            # A map card (app 0.4.33) keeps who rides along and how it frames them, and whether its name is on it. It is
            # drawn at its frame's own size and again only when someone moved, so it has no fit and no pace.
            elif options.get('display') == 'map':
                if 'map' in options:
                    options = {**options, 'map': map_entities(options['map'], tile['entity'])}
                allowed = {**MAP_OPTIONS, 'overlay': PICTURE_OPTIONS['overlay']}
                # Following is the map tile's own: a person's map follows that person and who rides along.
                # Chosen with nobody yet is a map of the zones until someone is added.
                if tile['entity'] != MAP_TILE:
                    options = {k: v for k, v in options.items() if k != 'follow'}
                for key, choices in allowed.items():
                    if key in options and options[key] not in choices:
                        raise ValueError(t('addon.errors.layout.invalid_setting', setting=key))
                options = {key: value for key, value in options.items() if key not in ('fit', 'refresh') and
                           not (key in allowed and value == allowed[key][0]) and not (key == 'map' and not value)}
            elif set(options) & {'refresh', *PICTURE_OPTIONS, *MAP_OWN}:
                options = {key: value for key, value in options.items() if key not in ('refresh', *PICTURE_OPTIONS, *MAP_OWN)}
            # A favourite (app 0.4.42, firmware 0.24.0) keeps what it plays and on which speaker; another display leaves
            # them behind. It plays on a tap, so it has no small slider and no other tap of its own.
            if options.get('display') == 'favorite':
                if 'play' in options:
                    options = {**options, 'play': validate_favorite(options['play'])}
                elif not stored:
                    raise ValueError(t('addon.errors.layout.favorite_play'))
                if 'speaker' in options and (not isinstance(options['speaker'], str) or not options['speaker'].strip() or len(options['speaker'].encode()) > 48):
                    raise ValueError(t('addon.errors.layout.invalid_setting', setting='speaker'))
                options = {k: v for k, v in options.items() if k not in ('inline', 'controls', 'action') and not (k == 'tap' and v == 'action')}
            elif set(options) & set(FAVORITE_OWN):
                options = {k: v for k, v in options.items() if k not in FAVORITE_OWN}
            if options.get('display') == 'watch' and options.get('inline') == 'slider':
                raise ValueError(t('addon.errors.layout.watch_or_slider'))
            if 'controls' in options:
                allowed = ('none',) + tuple(key for key, _ in CONTROLS.get(domain, ()))
                if not isinstance(options['controls'], str) or options['controls'] not in allowed:
                    raise ValueError(t('addon.errors.layout.no_direct_control'))
            item['options'] = dict(options)
        clean.append(item)
    # The keys stand under a tile that holds keys (KEY_HOLDERS), each on a place of its own there; they follow the
    # placed tiles, in their holder's order and their own.
    keys = [item for item in clean if is_key(item)]
    clean = placed(clean)
    holders = {item['entity']: n for n, item in enumerate(clean) if item['entity'] in KEY_HOLDERS}
    places = set()
    for item in keys:
        if item['in'] not in holders or not 0 <= item['key'] < KEY_HOLDERS[item['in']] or (item['in'], item['key']) in places:
            raise ValueError(t('addon.errors.layout.position'))
        places.add((item['in'], item['key']))
    keys.sort(key=lambda item: (holders[item['in']], item['key']))
    # Positions: every placed tile or none (an older editor sends none and keeps its order).
    given = [tile.get('slot') for tile in placed(tiles)]
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
            # A span must be one this grid takes: a rectangle the names already say, or the whole page, is refused.
            if span_of(size) and not span_offered(*span_of(size), grid):
                raise ValueError(t('addon.errors.layout.position'))
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
    if keys:
        # The holders' order is the placed order now, which the sort above may have changed.
        order = {item['entity']: n for n, item in enumerate(clean)}
        keys.sort(key=lambda item: (order[item['in']], item['key']))
    result = {'title': title.strip(), 'tiles': clean + keys}
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

# The forecasts a weather card asks for, each with Home Assistant's feature bit for it (catalogue/_ha.json).
FORECAST_BITS = (('daily', catalogue.bits('weather', 'FORECAST_DAILY')), ('hourly', catalogue.bits('weather', 'FORECAST_HOURLY')))

def forecast_kinds(attributes):
    """The forecasts a weather entity offers, from its supported_features (WeatherEntityFeature FORECAST_DAILY and
    FORECAST_HOURLY, through the tile catalogue). Asking for one it lacks makes Home Assistant log an error; an entity
    that reports no features (unavailable) is asked for both, as before."""
    features = (attributes or {}).get('supported_features')
    if not isinstance(features, int) or isinstance(features, bool):
        return frozenset(('daily', 'hourly'))
    return frozenset(kind for kind, bit in FORECAST_BITS if features & bit)

def forecast_number(entry, name):
    value = entry.get(name)
    return round(value, 1) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

def forecast_time(entry, tz):
    try:
        return datetime.fromisoformat(str(entry.get('datetime')).replace('Z', '+00:00')).astimezone(tz or timezone.utc)
    except (ValueError, TypeError):
        return None

def lock_extras(entry):
    """What a lock's card needs beside its attributes (firmware 0.5.0+): `dc` 1 when Home Assistant keeps a default code in
    the entity's registry options (`options.lock.default_code`; it then fills the code in itself and the screen asks for
    none, as Home Assistant's own lock dialog does). The code itself never leaves Home Assistant."""
    options = (entry or {}).get('options') if isinstance(entry, dict) else None
    lock = options.get('lock') if isinstance(options, dict) else None
    return {'dc': 1} if isinstance(lock, dict) and isinstance(lock.get('default_code'), str) and lock['default_code'] else {}

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

def media_cover(attrs):
    """The address a media player's cover is fetched from, or '' without one. Home Assistant's own proxy for the player
    (`entity_picture_local`) goes first (app 0.4.15, GitHub #77): a player whose picture lies elsewhere, on the internet
    or on a server in the house, hands out that address as `entity_picture` and the proxy beside it, and through the
    proxy Home Assistant fetches the picture itself, so this app only ever talks to Home Assistant."""
    for name in ('entity_picture_local', 'entity_picture'):
        picture = attrs.get(name)
        if isinstance(picture, str) and picture:
            return picture
    return ''

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
    picture = media_cover(attrs)
    if picture:
        # Without Home Assistant's access token (app 0.3.7): it changes every few minutes on its own while the picture
        # stays, and each new token made every screen fetch the same cover again. The link's `cache` part is the
        # picture's own hash, so the mark still changes with the picture.
        stable = re.sub(r'([?&])token=[^&]*(&|$)', lambda m: m.group(1) if m.group(2) else '', picture)
        result['pic'] = hashlib.sha1(stable.encode()).hexdigest()[:10]
    return result or None


def extras(tile, states, forecast=None, tz=None, hourly=None, now=None, device=None, entries=None, words=None, icon_of=None, device_name=None,
           energy=None, home_name=''):
    """Small, pre-computed values the firmware cannot derive itself (time zones, forecasts, a vacuum's device, the rows of
    a light's effects page, the house's power split for the energy card from `energy`, Home Assistant's Energy settings)."""
    if tile['entity'] == ENERGY_TILE:
        import energy_flow
        glyph = lambda icon: tile_icons.GLYPHS.get(icon[4:]) if isinstance(icon, str) and icon.startswith('mdi:') else None
        return energy_flow.payload(energy or {}, states, glyph, home_name)
    domain = tile['entity'].split('.')[0]
    attrs = states.get(tile['entity'], {}).get('attributes', {})
    # A map card carries only its movement mark (app 0.4.33): the screen asks for a new picture when it changes, so
    # nothing polls and no place goes out (map_card.fingerprint).
    if (tile.get('options') or {}).get('display') == 'map':
        import map_card
        return {'mk': map_card.fingerprint(tile, states, entries)}
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
    if domain == 'automation':
        # When it last ran, and whether its actions run right now: Home Assistant counts the runs in `current`.
        last, running = epoch(attrs.get('last_triggered')), isinstance(attrs.get('current'), int) and attrs['current'] > 0
        return {**({'last': last} if last else {}), **({'run': True} if running else {})} or None
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
    # A map's own choices stay in the app: who is on it and how it frames them say where people are (app 0.4.33).
    # So do a favourite's own (app 0.4.42): the screen asks to play its tile, never an id.
    options = {k: v for k, v in tile.get('options', {}).items() if k not in ('icon', 'controls', 'action', *MAP_OWN, *FAVORITE_OWN)}
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

def state_message(index, tile, states, extra=None, precision=None, entry=None, units=None):
    if tile['entity'] in BUILTIN:
        message = {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'],
                   'name': short(tile['name'] or builtin_name(tile['entity']), 80), 'state': 'ok', 'a': {}}
        # The same wire form as any tile, so a chosen icon travels as its codepoint (app 0.2.74+).
        options = screen_options(tile, {})
        if options is not None:
            message['o'] = options
        # The map tile's movement mark (app 0.4.36), as any map's.
        if extra:
            message['x'] = extra
        return message
    state = states.get(tile['entity'], {})
    attrs = state.get('attributes', {})
    bounded = {}
    for key in ATTRS | HUMIDIFIER_ATTRS if tile['entity'].startswith('humidifier.') else ATTRS:
        value = attrs.get(key)
        if isinstance(value, bool):
            # assumed_state only matters to a lock's keys (firmware 0.5.0+) and a player's power keys (firmware
            # 0.39.0, both as Home Assistant's dialog has them); anywhere else it is bytes for nothing.
            if key in BOOL_ATTRS and (key != 'assumed_state' or tile['entity'].startswith(('lock.', 'media_player.'))):
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
            # A remote's activities (firmware 0.22.0+) are a select's options on its card, so they run to sixteen too.
            limit = 2 if key == 'hs_color' else 4 if key == 'fan_speed_list' else 16 if key in ('options', 'activity_list') else 8
            bounded[key] = [short(v, 48) if isinstance(v, str) else v for v in value[:limit]
                            if isinstance(v, str) or isinstance(v, (float, int)) and math.isfinite(v) and abs(v) <= 1000000]
    # A thermostat without a step of its own steps as Home Assistant's own controls step it: 1 degree in Fahrenheit,
    # half a degree otherwise (hui-target-temperature-card-feature), which also decides the decimals it shows.
    if tile['entity'].startswith('climate.') and 'target_temp_step' not in bounded and units is not None:
        bounded['target_temp_step'] = 1 if units.get('temperature') == '°F' else 0.5
    options = screen_options(tile, attrs, state.get('state'), entry)
    return {'v': 1, 'op': 'state', 'i': index, 'entity': tile['entity'],
            'name': short(tile['name'] or attrs.get('friendly_name') or tile['entity'], 80),
            'state': short(rounded_state(state.get('state', 'unavailable'), precision) if tile['entity'].startswith('sensor.') else state.get('state', 'unavailable'), 160), 'a': bounded,
            **({'o': options} if options is not None else {}), **({'x': extra} if extra else {})}

def drawn_controls(message, features):
    """The controls a screen draws right for this tile (app 0.4.32), in place of ones it would get wrong: what the entity
    can draw and what the screen's hello says it draws (catalogue.drawn_controls). `features`: the list the screen's
    hello said, None where it is not known (the editor's preview, which runs the newest firmware)."""
    return catalogue.drawn_controls(message, features)

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
    # What a screen with 4 MB of flash says about its partition table (app 0.4.56); nothing for every other screen.
    flash = diagnostic(NAME_SCREEN_FLASH, r'[a-z][a-z_]{0,15}')
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
                        'flash': flash.get(item.get('device_id')),
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

def hotspot_name(friendly):
    """The Wi-Fi fallback hotspot's network name (app 0.4.63): "Tessera" and the screen's name as Tessera shows it, so ten
    screens that lost a changed network each say which one they are. A network name holds at most 32 bytes (ESPHome counts
    characters, the radio bytes), so a long name is cut after a whole word, or a whole character when one word is that long."""
    full = f'Tessera {" ".join(friendly.split())}'
    name = full
    while len(name.encode('utf-8')) > 32:
        name = name[:-1]
    if name != full and full[len(name)] != ' ' and ' ' in name[len('Tessera '):]:
        name = name[:name.rindex(' ')]
    return name.rstrip()

def old_hotspot_name(device):
    """The hotspot name this app wrote from app 0.4.32 to 0.4.62: the device name, cut to leave room for " Setup"."""
    return device[:26] + ' Setup'

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
    # ESPHome Device Builder may still be older (docs/RELEASING.md, "ESPHome versions").
    key, ota = base64.b64encode(secrets.token_bytes(32)).decode(), secrets.token_urlsafe(24)
    # The Wi-Fi fallback hotspot and its captive portal, where the board has room for them (boards.json `hotspot`,
    # app 0.4.5+): a board with 4 MB of flash leaves both out, some 90 KB of its 1.75 MB update slot. A screen whose
    # Wi-Fi changed is then installed again over USB (docs/EASY_SETUP.md). Its name says which screen it is (hotspot_name,
    # app 0.4.63).
    hotspot = (f'''  ap:
    ssid: {quote(hotspot_name(friendly))}
    password: {quote(secrets.token_urlsafe(12))}
captive_portal:
''' if SHAPES[board].get('hotspot', True) else '')
    # What lets ESP Screens replace the partition table over Wi-Fi (boards.json `wide_slots`, app 0.4.56): a board with
    # 4 MB of flash builds for wider update slots than ESPHome's own table has, and a screen that still has that table
    # gets the wide one after an update (docs/FLASH_LAYOUT.md). It has to stand here, in the screen's own YAML: ESPHome's
    # default for it would win over a line in a package.
    table_access = '    allow_partition_access: true\n' if SHAPES[board].get('wide_slots') else ''
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
{table_access}wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  power_save_mode: none
{hotspot}'''
