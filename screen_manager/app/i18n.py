"""The languages of ESP Screens (app 0.2.90).

Every text of the app, the editor and the screens lives in one JSON file per language (screen_manager/translations,
docs/TRANSLATING.md); English is the source, and a text a language lacks shows in English. The editor reads its own
section in the browser, the screens get theirs built into their firmware (components/smart_display/screen_text_gen.py),
and this module gives the app its `addon` texts and the `screen` words it sends to the screens itself.

`Region` is Settings -> Language & region, the one place for every screen: the language (Home Assistant's, or a chosen
one), the clock (12 or 24 hours) and how numbers are written. "auto" does what Home Assistant does for a user who never
changed their profile: the clock and the numbers follow the language.
"""
import contextvars
import json
import math
import logging
import re
from pathlib import Path
import atomic

LOG = logging.getLogger('screen_manager')
HERE = Path(__file__).resolve().parent
# In the app's image the files sit next to the code (Dockerfile: COPY translations); in a checkout one folder up.
FOLDER = next((path for path in (HERE / 'translations', HERE.parent / 'translations') if path.is_dir()), HERE / 'translations')
CODE = re.compile(r'[a-z]{2,3}(-[A-Za-z0-9]{2,8})?')
CLOCKS = ('auto', '24', '12')
NUMBERS = ('auto', 'point', 'comma', 'space')
PLACEHOLDER = re.compile(r'\{([a-z_]+)\}')

# Which form of a plural text ("1 hour ago | {n} hours ago") fits n; the firmware (screen_text_gen.py) and the editor
# (web/src/i18n.ts) have the same rules, docs/TRANSLATING.md says which languages use which.
def _slavic(n, one):
    # C++'s remainder (the sign of n), as the firmware and the editor count.
    t, h = int(math.fmod(n, 10)), int(math.fmod(n, 100))
    if one:
        return 0
    return 1 if 2 <= t <= 4 and not 12 <= h <= 14 else 2

PLURAL = {
    'one_other': lambda n: 0 if n == 1 else 1,
    'one_upto_1': lambda n: 0 if abs(n) <= 1 else 1,
    'slavic_pl': lambda n: _slavic(n, n == 1),
    'east_slavic': lambda n: _slavic(n, math.fmod(n, 10) == 1 and math.fmod(n, 100) != 11),
    'none': lambda n: 0,
}

# The language of an editor's request (its X-ESP-Screens-Language header), for the messages the app answers with.
REQUEST_LANGUAGE = contextvars.ContextVar('request_language', default='en')


def flatten(node, prefix=''):
    """(key, text) pairs in document order; a list's items get .0, .1, ... ."""
    if isinstance(node, dict):
        items = node.items()
    elif isinstance(node, list):
        items = ((str(index), value) for index, value in enumerate(node))
    else:
        return [(prefix, node)]
    pairs = []
    for key, value in items:
        pairs.extend(flatten(value, f'{prefix}.{key}' if prefix else key))
    return pairs


class Translations:
    """Every language file, read once."""

    def __init__(self, folder=FOLDER):
        self.data, self.flat = {}, {}
        for path in sorted(Path(folder).glob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError) as error:
                LOG.warning('Translation %s is unreadable (%s); it is left out', path.name, type(error).__name__)
                continue
            if CODE.fullmatch(path.stem) and isinstance(data, dict):
                self.data[path.stem] = data
                self.flat[path.stem] = {key: value for key, value in flatten({k: v for k, v in data.items() if k != '_meta'})
                                        if isinstance(value, str)}
        self.data.setdefault('en', {'_meta': {'name': 'English', 'english': 'English', 'plural': 'one_other'}})
        self.flat.setdefault('en', {})

    def resolve(self, code):
        """The language ESP Screens has for `code`: the code itself (in any case), else its base (pt-BR -> pt), else English."""
        if not isinstance(code, str):
            return 'en'
        by_lower = {known.lower(): known for known in self.data}
        for candidate in (code, code.split('-')[0]):
            if candidate.lower() in by_lower:
                return by_lower[candidate.lower()]
        return 'en'

    def meta(self, code):
        """A language's `_meta`, its base language's for what a small variant file (en-GB) leaves out."""
        language = self.resolve(code)
        merged = {}
        for name in reversed(list(dict.fromkeys([language, self.resolve(language.split('-')[0])]))):
            merged.update(self.data.get(name, {}).get('_meta', {}))
        return merged

    def languages(self):
        """Every language for the settings: English first, then by English name."""
        found = [{'code': code, 'name': str(self.meta(code).get('name') or code),
                  'english': str(self.meta(code).get('english') or code), 'checked': self.meta(code).get('checked') is True}
                 for code in self.data]
        return sorted(found, key=lambda item: (not item['code'].startswith('en'), item['code'] != 'en', item['english']))

    def chain(self, language):
        """The files a language's texts come from, most specific first: pt-BR, then pt, then English."""
        language = self.resolve(language)
        base = self.resolve(language.split('-')[0])
        return list(dict.fromkeys([language, base, 'en']))

    def text(self, key, language='en', **params):
        """`key` in `language`, else in its base language (pt-BR -> pt), else in English, with {placeholders} filled;
        `n` picks a plural form."""
        language = self.resolve(language)
        # Only an empty text is missing: a separator of one space (French thousands) is a text.
        text = next((found for found in (self.flat.get(code, {}).get(key) for code in self.chain(language))
                     if isinstance(found, str) and found != ''), None)
        if text is None:
            return key
        if '|' in text and 'n' in params:
            forms = [form.strip() for form in text.split('|')]
            rule = PLURAL.get(self.meta(language).get('plural'), PLURAL['one_other'])
            try:
                text = forms[min(rule(int(params['n'])), len(forms) - 1)]
            except (TypeError, ValueError):
                text = forms[-1]
        return PLACEHOLDER.sub(lambda match: str(params[match.group(1)]) if match.group(1) in params else match.group(0), text)

    def clock_24h(self, code):
        """Whether the language writes 24 hours by default (_meta.clock), as Home Assistant's "auto" does."""
        return str(self.meta(code).get('clock', '24')) != '12'

    def number_style(self, code):
        """How the language writes 1234.5: point (1,234.5), comma (1.234,5) or space (1 234,5)."""
        decimal = self.text('screen.number.decimal', code)
        group = self.text('screen.number.group', code)
        if decimal == '.':
            return 'point'
        return 'space' if group.strip() == '' else 'comma'


TRANSLATIONS = Translations()


class Text(str):
    """A text that keeps its key and params, so it can be written again in another language: a message made in one place
    and shown in another, such as a delivery status the sync loop sets or an update result kept in updates.json, shows in
    the language of whoever looks at it (app 0.2.90). Everywhere else it is the str it reads as."""

    def __new__(cls, text, key=None, params=None):
        made = super().__new__(cls, text)
        made.key, made.params = key, dict(params or {})
        return made

    def into(self, language):
        """This text in `language`; one without a key stays as it is."""
        return _render(self.key, language, self.params) if self.key else str(self)


def _render(key, language, params):
    """`key` in `language` with its params filled in; a param that is a Text itself goes into that language too."""
    return TRANSLATIONS.text(key, language, **{name: value.into(language) if isinstance(value, Text) else value
                                               for name, value in params.items()})


def t(key, **params):
    """An `addon` text in the language of the editor that asked (REQUEST_LANGUAGE). It keeps its key, so the error it is
    raised with can still be written in another language (Updater.record)."""
    return Text(_render(key, REQUEST_LANGUAGE.get(), params), key, params)


def english(key, **params):
    """A text in English that keeps its key, for a message made now and read later: a delivery status, an update result,
    why a screen can't show an alert. Logs read the English; `shown` writes it in the editor's language."""
    return Text(_render(key, 'en', params), key, params)


def shown(value):
    """A text made earlier in the language of the editor that asks now; anything but a Text as it is."""
    return value.into(REQUEST_LANGUAGE.get()) if isinstance(value, Text) else value


# How every Home Assistant language writes the clock and numbers (tools/i18n.py cldr writes it from the Unicode CLDR):
# Automatic in Settings -> Language & region follows it, also for a language ESP Screens has no texts for yet.
try:
    REGIONS = {code: value for code, value in json.loads((HERE / 'regions.json').read_text(encoding='utf-8')).items()
               if isinstance(value, dict)}
except (OSError, ValueError):
    REGIONS = {}

# The screens' language and number format (Settings -> Language & region), for the words the app sends to the screens
# itself: tile names, the top bar, the history card. The manager keeps it current (Manager.language_changed).
SCREENS = {'language': 'en', 'numbers': 'point', 'clock_24h': True, 'group_min': 1, 'percent_space': False}
# The screen whose messages the app is writing now (Manager.sync_one), for the words that go to that screen alone: the
# language its firmware speaks, which can still be the one before an update, and whether that firmware predates the
# languages (English, fewer letters, numbers of its own).
SCREEN = contextvars.ContextVar('screen', default=None)
LEGACY = {'language': 'en', 'legacy': True, 'numbers': 'point', 'group_min': 1, 'percent_space': False}


def set_screens(language, numbers, clock_24h=True, group_min=1, percent_space=False):
    SCREENS.update(language=language, numbers=numbers, clock_24h=clock_24h, group_min=group_min, percent_space=percent_space)


def screen_context(screen):
    """What SCREEN holds for a screen: firmware without the "Screen language" sensor predates the languages; one whose
    sensor has no state yet (restarting) counts as speaking the screens' language."""
    if not screen:
        return None
    if not screen.get('language_sensor'):
        return LEGACY
    return {'language': TRANSLATIONS.resolve(screen.get('language') or SCREENS['language']), 'legacy': False}


def _screen(name):
    """A property of the screen being written for, else of all screens."""
    screen = SCREEN.get()
    return screen[name] if screen and name in screen else SCREENS[name]


def screen_language():
    """The language of the screen being written for, else of all screens ("nl", "pt-BR")."""
    return _screen('language')


def screen_script():
    """The script of the screen being written for (`_meta.script` of its language): its firmware carries that script's
    letters (packages/core.yaml, SCRIPT_GLYPHS), "latin" for most."""
    return TRANSLATIONS.meta(screen_language()).get('script', 'latin')


def legacy_screen():
    screen = SCREEN.get()
    return bool(screen and screen.get('legacy'))


def screen_t(key, **params):
    """A text in the screens' language, for what the app sends to them (and the notification it leaves in Home
    Assistant); a param that is a Text goes into that language too."""
    return _render(key, _screen('language'), params)


def screen_clock(hour, minute):
    """A time of day as the screens write it: "07:30" on 24 hours, "7:30 AM" on 12, in the language's day periods."""
    if SCREENS.get('clock_24h', True):
        return f'{hour:02d}:{minute:02d}'
    period = TRANSLATIONS.text('screen.time.am' if hour < 12 else 'screen.time.pm', _screen('language'))
    return f'{hour % 12 or 12}:{minute:02d} {period}'


def screen_number(text):
    """A number as Home Assistant sends it, written as the screens write numbers ("1.234,5" in Dutch)."""
    return format_number(text, _screen('numbers'), _screen('group_min'))


def unit_suffix(unit):
    """What follows a number for its unit, spaced as Home Assistant spaces them (blankBeforeUnit): nothing before "°",
    " %" or "%" by the language, one space before any other unit."""
    if not unit or unit == '°':
        return unit or ''
    if unit == '%':
        return ' %' if _screen('percent_space') else '%'
    return ' ' + unit


class Region:
    """Settings -> Language & region, kept in /data/language.json: one language, clock and number format for every
    screen. A screen's firmware carries its language; the clock and the numbers travel in the layout message."""

    def __init__(self, path, translations=TRANSLATIONS, ha_language=None):
        self.path, self.tr = Path(path), translations
        self.setting, self.clock, self.numbers = 'auto', 'auto', 'auto'
        # The 24 hours an app from before Language & region pinned, until Home Assistant tells what the screens showed.
        self.pinned = False
        # Home Assistant's own language (get_config), once connected.
        self.ha_language = ha_language or (lambda: None)
        self.stored = self.path.exists()
        raw = atomic.read_json(self.path, 1)
        if raw:
            self.setting = raw.get('language') if raw.get('language') == 'auto' or raw.get('language') in self.tr.data else 'auto'
            self.clock = raw.get('clock') if raw.get('clock') in CLOCKS else 'auto'
            self.numbers = raw.get('numbers') if raw.get('numbers') in NUMBERS else 'auto'
            self.pinned = raw.get('pinned') is True

    def save(self):
        atomic.write_json(self.path, {'version': 1, 'language': self.setting, 'clock': self.clock, 'numbers': self.numbers,
                                      **({'pinned': True} if self.pinned else {})})
        self.stored = True

    def change(self, data):
        """Apply {language?, clock?, numbers?} from the editor; ValueError (translated) for anything unknown."""
        if not isinstance(data, dict):
            raise ValueError(t('addon.errors.language_choice'))
        setting = data.get('setting', self.setting)
        clock = data.get('clock', self.clock)
        numbers = data.get('numbers', self.numbers)
        if setting != 'auto' and setting not in self.tr.data:
            raise ValueError(t('addon.errors.language_choice'))
        if clock not in CLOCKS or numbers not in NUMBERS:
            raise ValueError(t('addon.errors.region_choice'))
        # The owner choosing a clock ends the pin.
        self.setting, self.clock, self.numbers = setting, clock, numbers
        self.pinned = self.pinned and 'clock' not in data
        self.save()

    def language(self):
        """The language of every screen: the chosen one, else Home Assistant's, else English."""
        return self.setting if self.setting != 'auto' else self.tr.resolve(self.ha_language() or 'en')

    def written(self):
        """How the language writes the clock and numbers: Home Assistant's own language (sv, pt-BR) even when ESP Screens
        shows it English or Portuguese texts, the chosen language when there is one. From regions.json, else from the
        language's file."""
        code = self.setting if self.setting != 'auto' else (self.ha_language() or 'en')
        for candidate in (code, str(code).split('-')[0]):
            found = REGIONS.get(candidate)
            if found:
                return found
        language = self.tr.resolve(code)
        return {'clock': '24' if self.tr.clock_24h(language) else '12', 'numbers': self.tr.number_style(language),
                'group_min': 2 if self.tr.text('screen.number.group_min', language) == '2' else 1,
                'percent_space': self.tr.text('screen.number.percent', language).startswith(' ')}

    def clock_24h(self):
        return self.written().get('clock') != '12' if self.clock == 'auto' else self.clock == '24'

    def number_style(self):
        return self.written().get('numbers', 'point') if self.numbers == 'auto' else self.numbers

    def group_min(self):
        """CLDR's minimum grouping digits of the numbers the screens write: 2 is 1234 but 12.345. A chosen format is
        Home Assistant's for it (en, de or fr), which groups from 1,234."""
        return int(self.written().get('group_min', 1)) if self.numbers == 'auto' else 1

    def percent_space(self):
        """Whether the language puts a space before "%" (Home Assistant's rule, whatever the number format)."""
        return bool(self.written().get('percent_space'))

    def view(self):
        """What the editor's Language & region card shows."""
        return {'setting': self.setting, 'effective': self.language(),
                'ha': self.ha_language(), 'languages': self.tr.languages(),
                'clock': self.clock, 'clock_effective': '24' if self.clock_24h() else '12',
                'numbers': self.numbers, 'numbers_effective': self.number_style(),
                'group_min': self.group_min(), 'percent_space': self.percent_space(),
                # What Automatic means now, for its label: the clock and the numbers of the language.
                'clock_auto': '12' if self.written().get('clock') == '12' else '24',
                'numbers_auto': self.written().get('numbers', 'point'), 'group_min_auto': int(self.written().get('group_min', 1))}



def format_number(text, style, group_min=1):
    """A number as Home Assistant sends it ("1234.5") written in `style` ("1.234,5" for comma); anything else unchanged.
    `group_min` 2 leaves four digits whole (1234, but 12.345), as the language itself does."""
    if not isinstance(text, str) or not re.fullmatch(r'-?\d+(\.\d+)?', text):
        return text
    sign, body = ('-', text[1:]) if text.startswith('-') else ('', text)
    whole, _, rest = body.partition('.')
    group, decimal = {'point': (',', '.'), 'comma': ('.', ','), 'space': (' ', ',')}.get(style, (',', '.'))
    if len(whole) > (4 if group_min == 2 else 3):
        head = len(whole) % 3 or 3
        whole = whole[:head] + ''.join(group + whole[index:index + 3] for index in range(head, len(whole), 3))
    return sign + whole + (decimal + rest if rest else '')
