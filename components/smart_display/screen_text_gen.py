"""The texts a screen shows, in the language it is built for (app 0.2.90).

Every text lives in screen_manager/translations/<code>.json; its `screen` section is what the firmware draws. A build
takes one language: this module turns that section into one C++ table in the build's main.cpp, so a screen carries a
single language and looks a text up by its index (screen_text.h). The keys are the same for every language and come
from en.json in document order; tools/i18n.py writes them to screen_text_keys.h, and a static_assert in the build
checks that header against the JSON it is built from. A key a language lacks takes the English text.

Plain Python on purpose, without ESPHome: __init__.py imports it for the build, tools/i18n.py and the tests use it too.
The ESP Screens app has its own reader (screen_manager/app/i18n.py), as the app's image holds no components folder.
"""
import json
import re
from pathlib import Path

# The repository root: components/smart_display/ sits two folders down, in a checkout and in the clone ESPHome makes
# of the repository for an external component (git clone --depth=1 of the whole repository).
ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = ROOT / 'screen_manager' / 'translations'
LANGUAGE_CODE = re.compile(r'[a-z]{2,3}(-[A-Za-z0-9]{2,8})?')

# How a language picks the form of a plural text ("1 hour ago | {n} hours ago"): the index of the form for n, as C++.
# The editor has the same rules (web/src/i18n.ts); docs/TRANSLATING.md lists which languages use which.
PLURAL_RULES = {
    'one_other': 'return n == 1 ? 0 : 1;',
    'one_upto_1': 'return (n < 0 ? -n : n) <= 1 ? 0 : 1;',
    'slavic_pl': 'if (n == 1) return 0; int t = n % 10, h = n % 100; '
                 'return t >= 2 && t <= 4 && (h < 12 || h > 14) ? 1 : 2;',
    'east_slavic': 'int t = n % 10, h = n % 100; if (t == 1 && h != 11) return 0; '
                   'return t >= 2 && t <= 4 && (h < 12 || h > 14) ? 1 : 2;',
    'none': 'return 0;',
}


def load(code, folder=TRANSLATIONS):
    """A language file as a dict; None when there is none."""
    path = Path(folder) / f'{code}.json'
    if not LANGUAGE_CODE.fullmatch(code or '') or not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def resolve(code, folder=TRANSLATIONS):
    """The language a build takes for `code`: the file itself, else its base language (pt-BR -> pt), else English."""
    for candidate in (code, (code or '').split('-')[0]):
        if candidate and load(candidate, folder) is not None:
            return candidate
    return 'en'


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


def screen_pairs(data):
    """The `screen` section as (key, text) pairs, the key without the section."""
    return [(key, value) for key, value in flatten((data or {}).get('screen', {})) if isinstance(value, str)]


def identifier(key):
    """The C++ name of a key: settings.dark_mode -> settings_dark_mode."""
    return re.sub(r'[^A-Za-z0-9]+', '_', key).strip('_')


def keys_hash(keys):
    """FNV-1a over the keys, so a build notices a screen_text_keys.h that no longer matches the JSON."""
    value = 0x811C9DC5
    for byte in '\n'.join(keys).encode('utf-8'):
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def cpp_string(text):
    """A C++ string literal of UTF-8 text; every byte outside printable ASCII as a three-digit octal escape."""
    out = []
    for byte in text.encode('utf-8'):
        char = chr(byte)
        if char in '"\\':
            out.append('\\' + char)
        elif 32 <= byte < 127:
            out.append(char)
        else:
            out.append(f'\\{byte:03o}')
    return '"' + ''.join(out) + '"'


def chain(language, folder=TRANSLATIONS):
    """The files a language's texts come from, most specific first: pt-BR, then pt, then English."""
    found = [language]
    base = language.split('-')[0]
    if base != language and load(base, folder) is not None:
        found.append(base)
    return found + ([] if 'en' in found else ['en'])


def table(code, folder=TRANSLATIONS):
    """(language, keys, texts, plural rule) of a build: every English key, in its language where it has one, else in its
    base language (a small pt-BR file takes the rest from pt), else in English."""
    english = load('en', folder)
    language = resolve(code, folder)
    files = [load(name, folder) or {} for name in chain(language, folder)]
    texts_of = [dict(screen_pairs(data)) for data in files]
    keys, texts = [], []
    for key, text in screen_pairs(english):
        keys.append(key)
        # Only an empty text is missing: a separator of one space (French thousands) is a text.
        texts.append(next((own[key] for own in texts_of if isinstance(own.get(key), str) and own[key] != ''), text))
    plural = next((data.get('_meta', {}).get('plural') for data in files if data.get('_meta', {}).get('plural')), None)
    rule = plural if plural in PLURAL_RULES else 'one_other'
    return language, keys, texts, rule


def arrays(keys):
    """{list key: (index of its first item, length)} for the lists among the keys (date.months_short.0 ...)."""
    found = {}
    for index, key in enumerate(keys):
        head, _, last = key.rpartition('.')
        if head and last.isdigit():
            start, length = found.get(head, (index, 0))
            found[head] = (start, length + 1)
    return found


def keys_header(keys):
    """screen_text_keys.h: the index of every key, and the hash of them all."""
    lines = [
        '// GENERATED by tools/i18n.py from screen_manager/translations/en.json; run `python3 tools/i18n.py header`',
        '// after changing the keys of the `screen` section. The index of every text a screen shows in its language\'s',
        '// table (screen_text.h); a list such as the month names is its first index plus a count.',
        '#pragma once',
        '#include <cstdint>',
        '',
        'namespace screen_text {',
        'namespace txt {',
    ]
    lists = arrays(keys)
    listed = {index for start, length in lists.values() for index in range(start, start + length)}
    for index, key in enumerate(keys):
        if index not in listed:
            lines.append(f'constexpr uint16_t {identifier(key)} = {index};')
    for key, (start, length) in lists.items():
        lines.append(f'constexpr uint16_t {identifier(key)} = {start};')
        lines.append(f'constexpr uint16_t {identifier(key)}_count = {length};')
    lines += [
        '}  // namespace txt',
        f'constexpr uint16_t KEY_COUNT = {len(keys)};',
        f'constexpr uint32_t KEYS_HASH = 0x{keys_hash(keys):08X}u;',
        '}  // namespace screen_text',
        '',
    ]
    return '\n'.join(lines)


def definitions(code, folder=TRANSLATIONS, *, audio=True, audio_tests=True, voice=True):
    """The C++ a build adds to main.cpp: its language's table and plural rule, and the check against the keys header."""
    language, keys, texts, rule = table(code, folder)
    # Keep the shared indices/hash, but omit peripheral words on screens without that feature.
    # Empty entries share one literal; no translated audio strings enter an audio-off image.
    audio_keys = {"audio", "microphone_mute", "microphone_alc", "speaker_volume", "tap_sound"}
    test_keys = {"test_microphone", "test_speaker", "test_wake_word", "stop_audio_test"}
    for index, key in enumerate(keys):
        name = key.removeprefix("settings.")
        if (key in ("settings.wake_word_enabled",) and not (audio and voice)) or (key == "settings.wake_word" and not (audio and (audio_tests or voice))) or (key.startswith("voice.") and not voice) or (key.startswith("audio.") and not (audio and audio_tests)) or (key.startswith("settings.") and ((name in audio_keys and not audio) or
                                            (name in test_keys and not (audio and audio_tests)))):
            texts[index] = ""
    rows = ',\n'.join(f'    {cpp_string(text)}' for text in texts)
    return language, (
        f'static_assert(screen_text::KEYS_HASH == 0x{keys_hash(keys):08X}u && screen_text::KEY_COUNT == {len(keys)},\n'
        '              "screen_text_keys.h does not match screen_manager/translations/en.json: run tools/i18n.py header");\n'
        f'const char *const screen_text::TABLE[] = {{\n{rows}\n}};\n'
        f'const char *const screen_text::LANGUAGE = {cpp_string(language)};\n'
        f'int screen_text::plural_index(int n) {{ {PLURAL_RULES[rule]} }}\n'
    )


def english_header(folder=TRANSLATIONS):
    """tests/screen_text_en.h: the English table for the C++ tests, which build without ESPHome."""
    _, text = definitions('en', folder)
    return ('// GENERATED by tools/i18n.py (`python3 tools/i18n.py header`): the English texts for the C++ tests, which\n'
            '// build a header without ESPHome and so without the table a screen\'s build writes into main.cpp.\n'
            '#pragma once\n'
            '#include "components/smart_display/screen_text.h"\n\n' + text)
