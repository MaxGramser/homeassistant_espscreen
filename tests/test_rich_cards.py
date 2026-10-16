"""Weather card data (hours, rain) and last-run times for scenes, scripts and buttons."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
from core import extras, packets, state_message, validate_layout
import ha_catalogue
import test_portal

TZ = ZoneInfo('Europe/Amsterdam')
NOW = datetime(2026, 9, 13, 11, 40, tzinfo=timezone.utc)


def hourly(day=None):
    # Whole hours from 08:00 on the given day (default: the fixed NOW day) into the next morning.
    start = (day or NOW).replace(hour=0, minute=0, second=0, microsecond=0)
    return [{'datetime': (start + timedelta(hours=h)).isoformat(), 'condition': 'rainy' if h < 12 else 'partlycloudy', 'temperature': 18 + h / 10,
             'precipitation': 0.2 if h < 12 else 0.0, 'precipitation_probability': 60 if h < 12 else 5} for h in range(8, 30)]


def daily():
    return [{'datetime': f'2026-09-{13 + i}T10:00:00+00:00', 'condition': 'cloudy', 'temperature': 21 + i, 'templow': 12.1, 'precipitation': 1.7 if i else 0.0}
            for i in range(6)]


class WeatherExtras(unittest.TestCase):
    def test_hours_start_now_and_carry_rain(self):
        states = {'weather.house': {'state': 'rainy', 'attributes': {'temperature': 18.4, 'humidity': 92, 'wind_speed': 12.2, 'wind_speed_unit': 'km/h'}}}
        extra = extras({'entity': 'weather.house'}, states, daily(), TZ, hourly(), NOW)
        self.assertEqual([h['t'] for h in extra['hours']], ['13:00', '14:00', '15:00', '16:00', '17:00', '18:00', '19:00', '20:00'], 'local time, from the current hour')
        self.assertEqual(extra['hours'][0], {'t': '13:00', 'c': 'rainy', 'h': 19.1, 'p': 60, 'r': 0.2})
        self.assertEqual(extra['hours'][1]['r'], 0.0)
        self.assertEqual(len(extra['days']), 5)
        self.assertEqual(extra['days'][1], {'d': 'Mo', 'c': 'cloudy', 'h': 22, 'l': 12.1, 'r': 1.7}, 'no probability when the provider gives none')
        message = state_message(0, {'entity': 'weather.house', 'name': 'Outside', 'options': {'display': 'forecast'}}, states, extra)
        self.assertEqual(message['a']['wind_speed_unit'], 'km/h')
        self.assertEqual(message['a']['humidity'], 92)
        self.assertLessEqual(len(packets(message)), 8, 'a full weather card still fits comfortably')

    def test_weather_without_forecasts_sends_nothing_extra(self):
        self.assertIsNone(extras({'entity': 'weather.house'}, {}, None, TZ, None, NOW))
        self.assertEqual(extras({'entity': 'weather.house'}, {}, daily(), TZ, [], NOW).keys(), {'days'})


class LastRun(unittest.TestCase):
    def test_scripts_scenes_and_buttons_report_when_they_last_ran(self):
        states = {'script.tv': {'state': 'off', 'attributes': {'last_triggered': '2026-09-13T08:10:49.403953+00:00'}},
                  'scene.evening': {'state': '2026-09-12T16:33:37.040291+00:00', 'attributes': {}},
                  'button.bell': {'state': '2026-09-13T09:00:00+00:00', 'attributes': {}},
                  'script.new': {'state': 'off', 'attributes': {'last_triggered': None}},
                  'scene.never': {'state': 'unknown', 'attributes': {}}}
        self.assertEqual(extras({'entity': 'script.tv'}, states, None, TZ), {'last': 1789287049})
        self.assertEqual(extras({'entity': 'scene.evening'}, states, None, TZ), {'last': 1789230817})
        self.assertEqual(extras({'entity': 'button.bell'}, states, None, TZ), {'last': 1789290000})
        self.assertIsNone(extras({'entity': 'script.new'}, states, None, TZ))
        self.assertIsNone(extras({'entity': 'scene.never'}, states, None, TZ))
        message = state_message(0, {'entity': 'script.tv', 'name': ''}, states, extras({'entity': 'script.tv'}, states, None, TZ))
        self.assertEqual(message['x'], {'last': 1789287049})
        self.assertNotIn('last_triggered', message['a'], 'the raw timestamp stays behind; the firmware gets the epoch')


class HourlySync(unittest.IsolatedAsyncioTestCase):
    async def test_manager_asks_for_daily_and_hourly_forecasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = test_portal.ManagerTests().setup_manager(Path(tmp) / 'screens.json')
            m.ha.states['weather.house'] = {'state': 'rainy', 'attributes': {'friendly_name': 'House', 'temperature': 18.4}}
            asked = []
            async def forecast(entity, kind='daily'):
                asked.append(kind)
                # The manager reads the real clock, so the hourly strip is anchored to today.
                return daily() if kind == 'daily' else hourly(datetime.now(timezone.utc))
            m.ha.forecast = forecast
            m.ha.registry.append({'entity_id': 'sensor.fw', 'platform': 'esphome', 'original_name': 'Screen firmware'})
            m.ha.states['sensor.fw'] = {'state': '0.2.19'}
            m.save('text.screen', {'title': 'Home', 'tiles': [{'entity': 'weather.house', 'name': '', 'options': {'display': 'forecast'}}]})
            await m.sync_one('text.screen', m.layouts['text.screen'])
            self.assertEqual(sorted(asked), ['daily', 'hourly'])
            sent = m.ha.messages[1][1]
            self.assertEqual(len(sent['x']['days']), 5)
            self.assertTrue(sent['x']['hours'])
            await m.sync_one('text.screen', m.layouts['text.screen'])
            self.assertEqual(len(asked), 2, 'both forecasts are cached')


class SecondLine(unittest.TestCase):
    """The second line of a tile (app 0.2.105, firmware 0.2.90+).

    Four ways to fill it and one rule about where each is decided: the line the screen works out itself, nothing at
    all and words of your own live in the option, so the screen keeps drawing them while Home Assistant is away;
    only a value of the entity needs an answer, and that list is Home Assistant's own - the attributes its frontend
    translations name - so nothing here is a list we keep.
    """

    # Real translations and a real state, taken from a live Home Assistant on 2026-09-21.
    WORDS = {
        'component.script.entity_component._.state_attributes.last_triggered.name': 'Last triggered',
        'component.script.entity_component._.state_attributes.mode.name': 'Run mode',
        'component.script.entity_component._.state_attributes.current.name': 'Running automations',
        'component.light.entity_component._.state_attributes.brightness.name': 'Brightness',
    }
    SCRIPT = {'attributes': {'last_triggered': '2026-09-21T05:08:31.915334+00:00', 'mode': 'single',
                             'current': '0', 'friendly_name': 'Goede morgen'}}
    SCENE = {'attributes': {'entity_id': ['light.a'], 'id': '169', 'icon': 'mdi:x', 'friendly_name': 'Avondlicht'}}

    def test_the_values_offered_are_the_ones_home_assistant_names(self):
        offered = ha_catalogue.subtitle_attributes('script.goede_morgen', self.SCRIPT, self.WORDS)
        self.assertEqual([v['key'] for v in offered], ['last_triggered', 'mode', 'current'])
        self.assertEqual([v['name'] for v in offered], ['Last triggered', 'Run mode', 'Running automations'])
        # An entity Home Assistant names no attribute of offers none: a scene, and that is why own text exists.
        self.assertEqual(ha_catalogue.subtitle_attributes('scene.avondlicht', self.SCENE, self.WORDS), [])
        # The tile's own name and icon are never a second line, and neither is a list.
        self.assertNotIn('friendly_name', [v['key'] for v in offered])
        self.assertEqual(ha_catalogue.subtitle_attributes('light.x', {'attributes': {}}, self.WORDS), [])
        self.assertEqual(ha_catalogue.subtitle_attributes('script.x', self.SCRIPT, {}), [])

    def test_only_a_value_needs_an_answer_from_the_app(self):
        def message(choice):
            return ha_catalogue.subtitle_message({'entity': 'script.goede_morgen', 'options': {'sub': choice}}, self.SCRIPT)
        # The screen holds these three itself and keeps drawing them with Home Assistant away.
        for choice in ('auto', 'none', 'text:Klaar om 7'):
            self.assertEqual(message(choice), {}, choice)
        # A moment in time goes as seconds, so the screen says it in its own words and its own clock.
        self.assertEqual(message('attr:last_triggered'), {'sm': 1789967311})
        self.assertEqual(message('attr:mode'), {'s': 'single'})
        # An attribute that is gone leaves the line to the screen again, instead of an empty one.
        self.assertEqual(message('attr:nope'), {})

    def test_a_number_is_written_as_home_assistant_writes_an_attributes_number(self):
        """computeAttributeValueToParts of Home Assistant's frontend (GitHub #241): a formatter for a few attributes,
        formatNumber (at most two decimals, a half away from zero), then the unit of the attribute for its domain, the
        system's temperature unit or the weather's units."""
        import i18n

        def line(entity, attribute, value, units=None, **attributes):
            tile = {'entity': entity, 'options': {'sub': f'attr:{attribute}'}}
            return ha_catalogue.subtitle_message(tile, {'attributes': {attribute: value, **attributes}}, units).get('s')
        metric = {'temperature': '°C', 'length': 'km', 'pressure': 'Pa'}
        cases = [
            (('climate.hall', 'current_humidity', 61.60000000000001), '61.6%'),
            (('climate.hall', 'current_humidity', 0.125), '0.13%'),
            (('climate.hall', 'current_temperature', 21.5, metric), '21.5 °C'),      # the system's unit, not the entity's
            (('light.desk', 'brightness', 128), '50%'),                             # 128 of 255
            (('light.desk', 'color_temp_kelvin', 2700), '2,700 K'),
            (('media_player.den', 'volume_level', 0.425), '43%'),                   # Math.round: a half goes up
            (('media_player.den', 'media_duration', 200), '03:20'),
            (('media_player.den', 'media_duration', 3723.4), '1:02:03'),
            (('input_datetime.day', 'year', 2026), '2026'),                         # its own toString, no grouping
            (('sun.sun', 'elevation', 12.345), '12.35°'),
            # Intl.NumberFormat rounds the number as JavaScript writes it: 2.675 and 1.005 are halves there.
            (('climate.hall', 'current_humidity', 2.675), '2.68%'),
            (('climate.hall', 'current_humidity', 1.005), '1.01%'),
            (('climate.hall', 'current_humidity', -0.001), '-0%'),
            (('weather.home', 'pressure', 1015.2, metric), '1,015.2 hPa'),          # no pressure_unit: hPa where lengths are km
            (('weather.home', 'wind_speed', 12, metric), '12 km/h'),
            (('weather.home', 'ozone', 5, metric), '5'),
            (('sensor.phone', 'speed', 3), '3'),                                    # no unit Home Assistant knows
        ]
        for (entity, attribute, value, *units), expected in cases:
            self.assertEqual(line(entity, attribute, value, *units), expected, (entity, attribute, value))
        self.assertEqual(line('weather.home', 'pressure', 1015, metric, pressure_unit='hPa'), '1,015 hPa')
        self.assertEqual(line('weather.home', 'precipitation', 1.2, {'length': 'mi'}), '1.2 in')
        # A number Home Assistant sends as text stays the text it is, as its frontend keeps it.
        self.assertEqual(line('climate.hall', 'current_humidity', '61.600'), '61.600')
        try:
            i18n.set_screens('nl', 'comma', True)
            self.assertEqual(line('climate.hall', 'current_humidity', 1234.5), '1.234,5%')
            i18n.set_screens('de', 'comma', True, percent_space=True)
            self.assertEqual(line('climate.hall', 'current_humidity', 61.6), '61,6 %')
        finally:
            i18n.set_screens('en', 'point', True)

    def test_words_and_a_yes_or_no_take_home_assistants_word(self):
        words = {'component.script.entity_component._.state_attributes.mode.state.single': 'Single',
                 'component.media_player.entity_component._.state_attributes.is_volume_muted.state.true': 'Muted'}

        def line(entity, attribute, value, words=words):
            tile = {'entity': entity, 'options': {'sub': f'attr:{attribute}'}}
            return ha_catalogue.subtitle_message(tile, {'attributes': {attribute: value}}, None, None, words).get('s')
        self.assertEqual(line('script.morning', 'mode', 'single'), 'Single')
        self.assertEqual(line('script.morning', 'mode', 'queued'), 'queued')     # no word: the words it is
        self.assertEqual(line('media_player.den', 'is_volume_muted', True), 'Muted')
        self.assertEqual(line('media_player.den', 'is_volume_muted', False), 'Off')  # no word: the screens' Off
        # An integration's own word for its translation key comes first, as in Home Assistant's frontend.
        own = {**words, 'component.roborock.entity.vacuum.roborock.state_attributes.fan_speed.state.max': 'Max+'}
        tile = {'entity': 'vacuum.robot', 'options': {'sub': 'attr:fan_speed'}}
        entry = {'platform': 'roborock', 'translation_key': 'roborock'}
        self.assertEqual(ha_catalogue.subtitle_message(tile, {'attributes': {'fan_speed': 'max'}}, None, entry, own), {'s': 'Max+'})

    def test_the_editor_gets_every_line_the_screen_would(self):
        named = {f'component.climate.entity_component._.state_attributes.{key}.name': key.title()
                 for key in ('current_humidity', 'hvac_action', 'friendly_name', 'last_triggered', 'fan_modes', 'aux')}
        state = {'attributes': {'current_humidity': 61.60000000000001, 'hvac_action': 'heating', 'friendly_name': 'Hall',
                                'last_triggered': '2026-09-21T05:08:31+00:00', 'fan_modes': ['on', 'auto'], 'aux': True,
                                'access_token': 'private'}}
        lines = ha_catalogue.subtitle_lines('climate.hall', state, {'temperature': '°C'}, None, named)
        # Only what the panel offers: a moment is the screen's to say, a list is no line, the name is the tile's own,
        # and what Home Assistant does not name (a token) never leaves the app.
        self.assertEqual(lines, {'current_humidity': '61.6%', 'hvac_action': 'heating', 'aux': 'On'})

    def test_the_layout_keeps_the_choice_and_refuses_a_shape_it_cannot_read(self):
        def options(sub):
            layout = validate_layout({'title': 'Home', 'tiles': [{'entity': 'script.morning', 'options': {'sub': sub}}]})
            return layout['tiles'][0].get('options')
        self.assertEqual(options('auto'), {})            # the default is stored as nothing at all
        self.assertEqual(options('none'), {'sub': 'none'})
        self.assertEqual(options('text:Klaar om 7'), {'sub': 'text:Klaar om 7'})
        # Words of your own keep the words, not the space around them: a line that starts with a blank looks
        # indented on the tile while every other line starts at the same place.
        self.assertEqual(options('text:  Klaar om 7  '), {'sub': 'text:Klaar om 7'})
        # Own text with nothing in it is an empty line, which is what "nothing" already means.
        self.assertEqual(options('text:   '), {'sub': 'none'})
        self.assertEqual(options('attr:last_triggered'), {'sub': 'attr:last_triggered'})
        for bad in ('attr:Bad Name', 'weird', 'attr:', 3, 'text:' + 'x' * 96):
            with self.assertRaises(ValueError, msg=bad):
                options(bad)
        # A Go to page tile keeps it: not saying "Page 3" is the reason this exists.
        page = validate_layout({'title': 'Home', 'tiles': [{'entity': 'screen.page_2', 'options': {'sub': 'none'}}]})
        self.assertEqual(page['tiles'][0]['options'], {'sub': 'none'})
