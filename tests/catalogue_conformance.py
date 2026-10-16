"""The cases the add-on's catalogue.py and the editor's catalogue.ts must answer alike (app 0.4.32).

    python tests/catalogue_conformance.py      writes tests/fixtures/catalogue-conformance.json from catalogue.py

tests/test_catalogue.py checks the file still is what catalogue.py answers; web/tests/catalogue.spec.ts checks
catalogue.ts answers the same. The cases: every type with controls, on every size (the names and spans of one and two
rows and columns), with no choice and with each of its controls chosen, for entities that report every feature, none,
a single temperature, a range; what a screen that lists climate_range, one that does not and one not known draws;
and what a screen without cover_rows draws of a control the screen lays out by its room (roomless).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
from core import span_of  # noqa: E402

FIXTURE = ROOT / 'tests/fixtures/catalogue-conformance.json'
SIZES = ['single', 'wide', 'tall', 'square', 'full', '1x1', '1x3', '3x1', '2x3', '3x2']
ENTITIES = [
    {},                                                        # reports nothing
    {'supported_features': 0},
    {'supported_features': 2 ** 23 - 1},                       # every feature there is
    {'supported_features': 1, 'temperature': 21},              # a single temperature
    {'supported_features': 2, 'target_temp_low': 19, 'target_temp_high': 23},   # a range only
    {'supported_features': 3, 'temperature': None, 'target_temp_low': 19, 'target_temp_high': 23},
    {'supported_features': 8},                                 # a thermostat's fan only; a cover's stop
]
FEATURES = [None, [], ['climate_range'], ['cover_rows'], ['media_rows']]


def cases():
    for domain in sorted(catalogue.TYPES):
        keys = catalogue.control_keys(domain)
        if not keys:
            continue
        variants = [{}] + [{'controls': key} for key in keys + ['none']] + [{'display': 'watch'}, {'inline': 'slider'}]
        for size in SIZES:
            for options in variants:
                tile = {'entity': f'{domain}.case', 'options': {'size': size, **options}}
                yield {'kind': 'resolve', 'tile': tile, 'expect': catalogue.resolve_controls(tile, span_of)}
        for key in keys:
            for attributes in ENTITIES:
                for features in FEATURES:
                    got = catalogue.drawable(domain, key, attributes, None if features is None else frozenset(features))
                    yield {'kind': 'drawable', 'domain': domain, 'key': key, 'attributes': attributes, 'features': features, 'expect': got}
            for size in SIZES:
                yield {'kind': 'roomless', 'domain': domain, 'key': key, 'size': size, 'expect': catalogue.roomless(domain, key, size, span_of)}


def output():
    return json.dumps({'cases': list(cases())}, indent=0, sort_keys=True) + '\n'


if __name__ == '__main__':
    FIXTURE.write_text(output())
    print(f'wrote {FIXTURE.relative_to(ROOT)}: {len(json.loads(FIXTURE.read_text())["cases"])} cases')
