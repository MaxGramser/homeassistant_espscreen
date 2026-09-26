"""Top bar (app 0.2.38 / firmware 0.2.32): validation, text, icons, visibility and delivery."""
from firmware_sources import runtime_source
from manager_fixtures import with_screen_grid
import asyncio
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import header_bar  # noqa: E402
import tile_icons  # noqa: E402
from core import FIRMWARE_VERSION, HEADER_MIN_FIRMWARE, discover, header_items, validate_header, validate_layout  # noqa: E402

FIRMWARE = (ROOT / 'components/smart_display/header_bar.h').read_text()
# The firmware's words live in the translations since app 0.2.90 (screen.time in English, the language of reference).
FIRMWARE += json.dumps(json.loads((ROOT / 'screen_manager/translations/en.json').read_text(encoding='utf-8'))['screen']['time'])
TILES = runtime_source()
HEADER_VIEW = (ROOT / 'components/smart_display/page_header.h').read_text()
EDITOR = (ROOT / 'web/src/model/topbar.ts').read_text()
PROFILES = ('checkout/guition.yaml', 'checkout/cyd.yaml')

def state(value, last_changed='2026-09-13T14:00:00+00:00', **attributes):
    return {'state': value, 'attributes': attributes, 'last_changed': last_changed}

def entity(eid, content='state', icon='auto', show='always'):
    return {'type': 'entity', 'entity': eid, 'content': content, 'icon': icon, 'show': show}


def editor_bars():
    """LOOK_BARS in web/src/model/topbar.ts: {look: {metric: number}}."""
    block = EDITOR.split('export const LOOK_BARS', 1)[1].split('};', 1)[0]
    return {look: dict((key, int(value)) for key, value in re.findall(r'(\w+): (\d+)', body))
            for look, body in re.findall(r'(standard|compact): \{([^}]*)\}', block)}

class ValidationTests(unittest.TestCase):
    def test_items_fill_defaults_and_keep_order(self):
        header = validate_header({'items': [{'type': 'clock'}, {'type': 'entity', 'entity': 'binary_sensor.front_door'}, {'type': 'analog'}]})
        self.assertEqual(header['items'], [{'type': 'clock'}, entity('binary_sensor.front_door'), {'type': 'analog'}])
        # Top-bar-only domains: a phone's tracker, a lock, the alarm, the home zone.
        for eid in ('device_tracker.phone', 'lock.front_door', 'alarm_control_panel.house', 'zone.home', 'event.doorbell'):
            validate_header({'items': [entity(eid)]})

    def test_rejects_what_the_firmware_cannot_draw(self):
        bad = [
            None, [], {'items': None}, {'items': [], 'extra': 1},
            {'items': [{'type': 'clock'}] * 7},
            {'items': [{'type': 'weather'}]},
            {'items': [{'type': 'clock', 'entity': 'sensor.x'}]},
            {'items': [entity('screen.clock')]},
            {'items': [entity('update.home_assistant')]},
            {'items': [entity('sensor.x', content='attribute')]},
            {'items': [entity('sensor.x', show='sometimes')]},
            {'items': [entity('sensor.x', icon='mdi:thermometer')]},
            {'items': [{**entity('sensor.x'), 'color': 'red'}]},
            {'items': [entity('sensor.x'), entity('sensor.x')]},
            {'items': [{'type': 'date'}, {'type': 'date'}]},
        ]
        for data in bad:
            with self.assertRaises(ValueError, msg=data):
                validate_header(data)
        # The same entity twice is fine when it shows something else.
        validate_header({'items': [entity('person.max'), entity('person.max', content='last_changed')]})

    def test_layout_keeps_header_and_old_layouts_keep_their_clock(self):
        layout = validate_layout({'title': 'Living room', 'tiles': [], 'header': {'items': [{'type': 'date'}]}})
        self.assertEqual(header_items(layout), [{'type': 'date'}])
        self.assertEqual(header_items(validate_layout({'title': 'Home', 'tiles': []})), [{'type': 'clock'}])
        without_clock = validate_layout({'title': 'Home', 'tiles': [], 'settings': {'show_clock': False}})
        self.assertEqual(header_items(without_clock), [])

class TextTests(unittest.TestCase):
    def test_numbers_as_home_assistant_writes_them(self):
        self.assertEqual(header_bar.number_text(21.34, 1), '21.3')
        self.assertEqual(header_bar.number_text(1249.0, 0), '1,249')
        self.assertEqual(header_bar.number_text(1249.04, 1), '1,249.0')
        self.assertEqual(header_bar.number_text(234.038566388889), '234.039')
        self.assertEqual(header_bar.number_text(23.5), '23.5')
        self.assertEqual(header_bar.number_text(-3.5, 1), '-3.5')
        self.assertEqual(header_bar.number_text(-0.04, 1), '0.0')
        self.assertEqual(header_bar.with_unit('21.3', '°C'), '21.3 °C')
        self.assertEqual(header_bar.with_unit('65', '%'), '65%')
        self.assertEqual(header_bar.with_unit('18', '°'), '18°')
        self.assertEqual(header_bar.with_unit('4', None), '4')

    def test_values_per_domain(self):
        # The screens' clock is Settings -> Language & region's (app 0.2.90); these values are on 24 hours.
        import i18n
        i18n.set_screens('en', 'point', True)
        tz = ZoneInfo('Europe/Amsterdam')
        registry = {'sensor.t': {'options': {'sensor': {'suggested_display_precision': 1}}},
                    'sensor.p': {'options': {'sensor': {'suggested_display_precision': 2, 'display_precision': 0}}}}
        cases = [
            ('sensor.t', state('21.34', unit_of_measurement='°C', device_class='temperature'), ('21.3 °C', None)),
            ('sensor.p', state('1249.4', unit_of_measurement='W'), ('1,249 W', None)),
            ('sensor.h', state('unavailable', unit_of_measurement='%'), ('—', None)),
            ('binary_sensor.door', state('on', device_class='door'), ('Open', None)),
            ('binary_sensor.door', state('off', device_class='door'), ('Closed', None)),
            # Home Assistant's own words for the class (screen.ha.binary), as the screen's tiles say them (app 0.2.90).
            ('binary_sensor.smoke', state('on', device_class='smoke'), ('Detected', None)),
            ('binary_sensor.something', state('off'), ('Off', None)),
            ('alarm_control_panel.house', state('armed_away'), ('Armed away', None)),
            ('alarm_control_panel.house', state('disarmed'), ('Disarmed', None)),
            ('alarm_control_panel.house', state('triggered'), ('Triggered', None)),
            ('lock.front_door', state('locked'), ('Locked', None)),
            ('person.max', state('not_home'), ('Away', None)),
            ('person.max', state('Office'), ('Office', None)),
            ('zone.home', state('4'), ('4', None)),
            ('weather.home', state('rainy', temperature=17.6, temperature_unit='°C'), ('18 °C', None)),
            ('climate.living_room', state('heat', current_temperature=20.46), ('20.5 °C', None)),
            ('sun.sun', state('above_horizon', next_setting='2026-09-14T17:57:31+00:00'), ('19:57', None)),
            ('input_datetime.alarm', state('07:30:00', has_date=False, has_time=True), ('07:30', None)),
            ('sensor.backup', state('2026-09-15T03:34:32+00:00', device_class='timestamp'), (None, 1789443272)),
            ('scene.film', state('2026-09-14T15:32:14+00:00'), (None, 1789399934)),
            ('script.all_off', state('off', last_triggered='2026-09-14T15:32:14+00:00'), (None, 1789399934)),
        ]
        for eid, value, expected in cases:
            self.assertEqual(header_bar.value(eid, value, registry.get(eid), {'temperature': '°C'}, tz), expected, eid)

    def test_times_follow_the_screens_clock(self):
        import i18n
        try:
            i18n.set_screens('en', 'point', False)
            self.assertEqual(i18n.screen_clock(19, 57), '7:57 PM')
            self.assertEqual(i18n.screen_clock(0, 5), '12:05 AM')
            i18n.set_screens('nl', 'comma', False)
            self.assertEqual(i18n.screen_clock(9, 30), '9:30 a.m.')
            i18n.set_screens('nl', 'comma', True)
            self.assertEqual(i18n.screen_clock(9, 30), '09:30')
        finally:
            i18n.set_screens('en', 'point', True)

    def test_text_keeps_to_the_font_and_its_length(self):
        # Every letter European languages write with stays (app 0.2.90); anything else folds to its base letter or goes.
        self.assertEqual(header_bar.clean_text('Café “Sun” 25 m³'), 'Café “Sun” 25 m³')
        self.assertEqual(header_bar.clean_text('Ångström ✓'), 'Ångström')
        self.assertEqual(header_bar.clean_text('Ǻngström'), 'Angström')
        # Home Assistant writes μg/m³ with the Greek letter (U+03BC); the screens draw the micro sign (U+00B5).
        self.assertEqual(header_bar.clean_text('12 μg/m³'), '12 µg/m³')
        self.assertEqual(header_bar.clean_text('12 µg/m³'), '12 µg/m³')
        self.assertLessEqual(len(header_bar.clean_text('é' * 60).encode()), header_bar.TEXT_BYTES)

    def test_active_colour_and_icon(self):
        door_open, door_closed = state('on', device_class='door'), state('off', device_class='door')
        self.assertTrue(header_bar.active('binary_sensor.door', door_open))
        self.assertFalse(header_bar.active('binary_sensor.door', door_closed))
        self.assertFalse(header_bar.active('sensor.p', state('0.0')))
        self.assertTrue(header_bar.active('sensor.p', state('12')))
        self.assertTrue(header_bar.active('person.max', state('home')))
        self.assertFalse(header_bar.active('person.max', state('Office')))
        self.assertFalse(header_bar.active('lock.front_door', state('locked')))
        self.assertFalse(header_bar.active('sensor.x', state('unavailable')))
        self.assertEqual(header_bar.accent('binary_sensor.door', door_open), header_bar.AMBER)
        self.assertIsNone(header_bar.accent('binary_sensor.door', door_closed))
        self.assertEqual(header_bar.accent('binary_sensor.leak', state('on', device_class='moisture')), header_bar.RED)
        self.assertEqual(header_bar.accent('alarm_control_panel.house', state('armed_home')), header_bar.GREEN)
        self.assertEqual(header_bar.accent('alarm_control_panel.house', state('arming')), header_bar.ORANGE)
        self.assertEqual(header_bar.accent('alarm_control_panel.house', state('triggered')), header_bar.RED)
        self.assertIsNone(header_bar.accent('alarm_control_panel.house', state('disarmed')))
        self.assertEqual(header_bar.accent('lock.front_door', state('unlocked')), header_bar.RED)
        self.assertEqual(header_bar.accent('person.max', state('home')), header_bar.GREEN)
        glyph = tile_icons.GLYPHS
        self.assertEqual(header_bar.auto_icon('binary_sensor.door', door_open), glyph['door-open'])
        self.assertEqual(header_bar.auto_icon('binary_sensor.door', door_closed), glyph['door-closed'])
        self.assertEqual(header_bar.auto_icon('sensor.t', state('21', device_class='temperature')), glyph['thermometer'])
        self.assertEqual(header_bar.auto_icon('sensor.t', state('21', device_class='temperature', icon='mdi:fire')), glyph['fire'])
        self.assertEqual(header_bar.auto_icon('weather.home', state('rainy')), glyph['weather-rainy'])
        self.assertEqual(header_bar.auto_icon('lock.front_door', state('unlocked')), glyph['lock-open-variant'])
        self.assertEqual(header_bar.auto_icon('counter.visitors', None), glyph['gauge'])

    def test_every_icon_name_is_in_the_fonts(self):
        names = set(header_bar.SENSOR_ICONS.values()) | set(header_bar.DOMAIN_ICONS.values())
        names |= {name for pair in header_bar.BINARY_ICONS.values() for name in pair}
        self.assertLessEqual(names, set(tile_icons.GLYPHS))
        self.assertIn('F0150', tile_icons.GLYPHS.values(), 'the dial is sized by clock-outline')
        self.assertIn('0xF0150', HEADER_VIEW)

class MessageTests(unittest.TestCase):
    def test_message_leaves_hidden_items_out_and_keeps_builtins(self):
        states = {'binary_sensor.door': state('off', device_class='door'), 'person.max': state('home', last_changed='2026-09-14T15:00:00+00:00'),
                  'sensor.t': state('21.3', unit_of_measurement='°C', device_class='temperature')}
        layout = {'title': 'Hallway', 'tiles': [], 'header': {'items': [
            entity('binary_sensor.door', show='active'), entity('person.max', content='last_changed'),
            entity('sensor.t', icon='none'), {'type': 'analog'}, {'type': 'clock'}]}}
        message = header_bar.message(layout, states)
        self.assertEqual(message['op'], 'header')
        self.assertEqual(message['items'], [
            {'k': 'ago', 'i': tile_icons.GLYPHS['account'], 'e': 1789398000, 'c': header_bar.GREEN},
            {'k': 'text', 't': '21.3 °C'}, {'k': 'analog'}, {'k': 'clock'}])
        states['binary_sensor.door'] = state('on', device_class='door')
        opened = header_bar.message(layout, states)['items'][0]
        self.assertEqual(opened, {'k': 'text', 'i': tile_icons.GLYPHS['door-open'], 't': 'Open', 'c': header_bar.AMBER})
        preview = header_bar.preview(layout['header'], {**states, 'binary_sensor.door': state('off', device_class='door')})
        self.assertEqual([p['shown'] for p in preview], [False, True, True, True, True])
        self.assertEqual(preview[0]['name'], 'binary_sensor.door')

    def test_old_layout_sends_the_clock_of_show_clock(self):
        self.assertEqual(header_bar.message({'title': 'Home', 'tiles': []}, {})['items'], [{'k': 'clock'}])
        self.assertEqual(header_bar.message({'title': 'Home', 'tiles': [], 'settings': {'show_clock': False}}, {})['items'], [])

    def test_suggestions_prefer_the_screens_room_and_skip_diagnostics(self):
        states = {'sensor.plug_temp': state('30', device_class='temperature'), 'sensor.living_room_temp': state('21', device_class='temperature'),
                  'sensor.attic_temp': state('18', device_class='temperature'), 'zone.home': state('3'), 'sun.sun': state('above_horizon')}
        entities = [{'id': 'sensor.plug_temp', 'name': 'Plug', 'area': 'Living room'}, {'id': 'sensor.living_room_temp', 'name': 'Living room', 'area': 'Living room'},
                    {'id': 'sensor.attic_temp', 'name': 'Attic', 'area': 'Attic'}, {'id': 'zone.home', 'name': 'Home', 'area': ''},
                    {'id': 'sun.sun', 'name': 'Sun', 'area': ''}]
        picks = header_bar.suggestions({'name': 'Living room'}, entities, states, {'sensor.plug_temp': {'entity_category': 'diagnostic'}})
        self.assertEqual([(p['label'], p['item']['entity']) for p in picks],
                         [('Temperature', 'sensor.living_room_temp'), ('People home', 'zone.home'), ('Sunrise and sunset', 'sun.sun')])
        for pick in picks:
            validate_header({'items': [pick['item']]})

    def test_discovery_offers_top_bar_domains_outside_the_tile_picker(self):
        registry = [{'entity_id': 'lock.front_door'}, {'entity_id': 'light.hall'}, {'entity_id': 'update.core'}]
        states = {'lock.front_door': state('locked'), 'light.hall': state('on'), 'update.core': state('off'), 'zone.home': state('2')}
        _, entities = discover(registry, states, [], [])
        flags = {e['id']: e.get('tile', True) for e in entities}
        self.assertEqual(flags, {'lock.front_door': False, 'light.hall': True, 'zone.home': False})

class ParityTests(unittest.TestCase):
    def test_text_font_carries_exactly_the_glyphs_the_add_on_sends(self):
        for name in PROFILES + ('packages/cyd.yaml', 'packages/guition.yaml'):
            text = profiles.resolved(name)
            block = re.search(r'id: sublabel_big\n    size: \d+\n    bpp: 4\n    glyphs: \[(.*?)\]\n', text, re.S)
            self.assertIsNotNone(block, name)
            glyphs = set(re.findall(r"'([^'])'|\"(')\"", block.group(1)))
            self.assertEqual({a or b for a, b in glyphs}, set(header_bar.GLYPHS), name)

    def test_editor_and_firmware_share_words_and_spacing(self):
        for phrase in ('Just now', ' min ago', ' hour ago', ' hours ago', 'Yesterday', ' days ago', '1 week ago', ' weeks ago',
                       '1 month ago', ' months ago', ' year ago', ' years ago', 'In ', 'Tomorrow'):
            self.assertIn(phrase, FIRMWARE)
        # The editor's mockup draws the screens' own words since app 0.2.90: screen.time and screen.date of the translations.
        for key in ('screen.time.${key}', 'screen.date.top_bar', 'screen.date.weekdays_min.${now.getDay()}', 'screen.date.months_short.${now.getMonth()}'):
            self.assertIn(key, EDITOR)
        for threshold in ('3600', '86400', '172800', '604800', '2592000', '31536000'):
            self.assertIn(threshold, FIRMWARE)
            self.assertIn(threshold, EDITOR)
        self.assertIn('std::max(2, scaled(cap, 4)), std::max(6, (cap * 125 + 50) / 100), std::max(8, scaled(cap, 16))', FIRMWARE)
        self.assertIn('Math.max(2, Math.floor((cap * 4 + 5) / 10)), item: Math.max(6, Math.floor((cap * 125 + 50) / 100)), name: Math.max(8, Math.floor((cap * 16 + 5) / 10))', EDITOR)
        self.assertIn('width * 35 / 100', FIRMWARE)
        # The same rule over the same room: the home key takes its width off the bar before the name is measured
        # (firmware 0.2.100+), so both sides read `width`, not the whole bar.
        self.assertIn('(width * 35) / 100', EDITOR)
        self.assertIn('const width = Math.max(0, metrics.width - homeShift);', EDITOR)
        english = json.loads((ROOT / 'screen_manager/translations/en.json').read_text(encoding='utf-8'))['screen']
        self.assertEqual(header_bar.MONTHS, tuple(english['date']['months_short']))

    def test_profiles_draw_the_bar_from_the_runtime(self):
        for name in PROFILES:
            text = profiles.text(name)
            self.assertIn('runtime_tiles::header_text_font = id(sublabel_big)->get_lv_font();', text, name)
            self.assertIn('runtime_tiles::header_icon_font = id(materialdesign_icons_mini)->get_lv_font();', text, name)
            self.assertIn('runtime_tiles::time_label = id(lbl_time);', text, name)
            refresh = text.split('  - id: ui_refresh', 1)[1].split('return;', 1)[0]
            self.assertNotIn('lbl_time', refresh, name)
        self.assertIn('render_header();', TILES.split('inline void render(lv_obj_t *room) {', 1)[1].split('\n}', 1)[0])
        self.assertLessEqual(HEADER_MIN_FIRMWARE, tuple(int(p) for p in FIRMWARE_VERSION.split('.')))

    def test_a_starting_screen_says_what_it_waits_for_in_the_middle(self):
        # Firmware 0.2.73+: until the first layout the text and a spinner stand in the middle and the name stays empty;
        # the first layout deletes them, so no spinner turns behind the tiles.
        render = TILES.split('inline void render(lv_obj_t *room) {', 1)[1].split('\n}', 1)[0]
        self.assertIn('if (!model.configured) boot_status(lv_obj_get_parent(room), tr(!ha_connected() ? '
                      'txt::status_connecting : transfer.begun ? txt::status_loading_tiles : txt::status_waiting));', render)
        self.assertIn('else if (boot_panel) { lv_obj_delete(boot_panel);', render)
        self.assertIn('label(room, !model.configured ? std::string() :', render)
        boot = TILES.split('inline void boot_status(', 1)[1].split('\n}', 1)[0]
        self.assertIn('boot_spinner = spinner_create(boot_panel,', boot)
        # Under the tiles, the cards and an alert, in the name's place.
        self.assertIn('lv_obj_move_to_index(boot_panel, lv_obj_get_index(room_label));', boot)
        for name in PROFILES:
            self.assertNotIn('Choose tiles in HA', profiles.text(name), name)

    def test_second_hand_runs_only_while_the_screen_is_awake(self):
        for name in PROFILES:
            text = profiles.text(name)
            self.assertIn('runtime_tiles::screen_awake = []() { return !id(display_dimmed); };', text, name)
        for name in ('packages/cyd.yaml', 'packages/guition.yaml'):
            self.assertIn('runtime_tiles::screen_awake', profiles.text(name), name)
        self.assertIn('inline bool awake() { return !screen_awake || screen_awake(); }', TILES)
        second_hand = TILES.split('inline void second_hand(', 1)[1].split('\n}', 1)[0]
        self.assertIn('set_hidden(p,!(awake() && now.is_valid()));', second_hand)
        self.assertIn('part_line(w,18,w.points+28,2,w.hand_width)', second_hand)
        tick = TILES.split('inline void tick() {', 1)[1]
        # The classic dial and the calm dial (firmware 0.3.6+) both move their hand; a digital or flip clock has none.
        self.assertIn('(((w.extra_mode=="analog" || w.extra_mode=="calendar") && t.display=="analog") || (w.extra_mode=="calm" && t.display=="dial")) && t.is_clock())second_hand(w,now);', tick)

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from server import Manager, create_app

@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class ManagerTests(unittest.IsolatedAsyncioTestCase):
    def manager(self, path, firmware='0.2.32'):
        class HA:
            online = True
            registry = [{'entity_id': 'text.screen', 'platform': 'esphome', 'original_name': 'Tile settings', 'device_id': 'd'},
                        {'entity_id': 'sensor.fw', 'platform': 'esphome', 'original_name': 'Screen firmware', 'device_id': 'd'},
                        {'entity_id': 'sensor.t', 'options': {'sensor': {'suggested_display_precision': 1}}},
                        {'entity_id': 'binary_sensor.door'}, {'entity_id': 'light.a'}]
            devices, areas = [], []
            time_zone, units = None, {'temperature': '°C'}
            def __init__(self):
                self.messages = []
                self.changed = asyncio.Event()
                self.states = {'text.screen': state('Ready'), 'sensor.fw': state(firmware), 'light.a': state('on'),
                               'sensor.t': state('21.34', unit_of_measurement='°C', device_class='temperature'),
                               'binary_sensor.door': state('off', device_class='door')}
            async def send(self, inbox, message, action=None):
                self.messages.append(message)
        return Manager(with_screen_grid(HA()), path)

    async def test_header_follows_layout_only_on_new_firmware(self):
        with tempfile.TemporaryDirectory() as temp:
            m = self.manager(Path(temp) / 'screens.json')
            layout = {'title': 'Hallway', 'tiles': [{'entity': 'light.a', 'name': ''}], 'settings': {'show_clock': True},
                      'header': {'items': [entity('sensor.t'), entity('binary_sensor.door', show='active')]}}
            m.save('text.screen', layout)
            saved = m.layouts['text.screen']
            self.assertFalse(saved['settings']['show_clock'], 'older firmware hides its clock when the bar has none')
            await m.sync_one('text.screen', saved)
            self.assertEqual([msg['op'] for msg in m.ha.messages], ['layout', 'header', 'state'])
            self.assertEqual(m.ha.messages[1]['items'], [{'k': 'text', 'i': tile_icons.GLYPHS['thermometer'], 't': '21.3 °C'}])
            await m.sync_one('text.screen', saved)
            self.assertEqual(len(m.ha.messages), 3, 'an unchanged bar is not sent again')
            m.ha.states['binary_sensor.door'] = state('on', device_class='door')
            await m.sync_one('text.screen', saved)
            self.assertEqual(len(m.ha.messages), 4)
            self.assertEqual(m.ha.messages[-1]['items'][1]['t'], 'Open')
            self.assertIn('binary_sensor.door', m.watched_entities())
            old = self.manager(Path(temp) / 'old.json', firmware='0.2.31')
            old.save('text.screen', layout)
            await old.sync_one('text.screen', old.layouts['text.screen'])
            self.assertEqual([msg['op'] for msg in old.ha.messages], ['layout', 'state'])

    async def test_older_editor_keeps_the_bar_and_gone_entities_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            m = self.manager(Path(temp) / 'screens.json')
            header = {'items': [{'type': 'date'}, {'type': 'clock'}]}
            m.save('text.screen', {'title': 'Hallway', 'tiles': [], 'header': header})
            m.save('text.screen', {'title': 'Different name', 'tiles': []})
            self.assertEqual(m.layouts['text.screen']['header'], header)
            with self.assertRaises(ValueError):
                m.save('text.screen', {'title': 'Hallway', 'tiles': [], 'header': {'items': [entity('sensor.does_not_exist')]}})
            self.assertEqual(m.layouts['text.screen']['header'], header)

    async def test_preview_endpoint_formats_unsaved_items(self):
        with tempfile.TemporaryDirectory() as temp:
            m = self.manager(Path(temp) / 'screens.json')
            app = create_app(m, development=True)
            async with TestClient(TestServer(app)) as client:
                inventory = await (await client.get('/api/inventory')).json()
                self.assertEqual(inventory['header']['max_items'], 6)
                self.assertEqual(inventory['header']['min_firmware'], '0.2.32')
                headers = {'X-Screen-CSRF': inventory['csrf']}
                items = [entity('binary_sensor.door', show='active'), {'type': 'clock'}]
                response = await client.post('/api/header-preview', json={'header': {'items': items}}, headers=headers)
                data = await response.json()
                self.assertEqual([p['shown'] for p in data['items']], [False, True])
                self.assertEqual(data['items'][0]['t'], 'Closed')
                bad = await client.post('/api/header-preview', json={'header': {'items': [{'type': 'nope'}]}}, headers=headers)
                self.assertEqual(bad.status, 400)


class EditorBar(unittest.TestCase):
    def test_the_editors_bar_is_each_looks_own(self):
        # The mockup's top bar takes the look's fonts and margin at the look's own density, the canvas the look was
        # drawn on (480 and 320 wide), and scales them to the screen's (topbar.ts, barMetricsFor).
        bars = editor_bars()
        self.assertEqual(set(bars), {'standard', 'compact'})
        for look, board in (('standard', 'guition'), ('compact', 'cyd')):
            values = profiles.board_values(board)
            self.assertEqual(values['LOOK'].strip('"'), look)
            bar = bars[look]
            self.assertEqual((bar['name'], bar['text'], bar['icon'], bar['inset'], bar['dpi']),
                             (int(values['FONT_HEADLINE_SIZE']), int(values['FONT_SUBLABEL_BIG_SIZE']),
                              int(values['FONT_ICON_MINI_SIZE']), int(values['HEADER_INSET']), round(float(values['DISPLAY_DPI']))), look)
            self.assertEqual(bar['width'], int(values['PANEL_W' if int(values.get('ROTATION_LANDSCAPE', '0')) % 180 == 0 else 'PANEL_H']) - 2 * bar['inset'], look)

if __name__ == '__main__':
    unittest.main()
