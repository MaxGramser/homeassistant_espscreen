"""Updating from app 0.4.31 keeps what people have (app 0.4.32, the tile catalogue).

tests/compat_corpus.py builds one-tile layouts of every entity type, size and option the app of 0.4.31 could store, on
three grids, and fixtures/compat/golden-0.4.31.json.gz holds what that app stored and sent for each of them. This app
must load every one of those saved pages, compile the same tiles, ask no newer firmware for them, refuse none of their
settings, and send a screen that is not updated (firmware before 0.19.0) what it got before. The only differences are
the ones listed here, each an intended change with its reason.
"""
import gzip
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import compat_corpus  # noqa: E402

GOLDEN = ROOT / 'tests/fixtures/compat/golden-0.4.31.json.gz'
# Attributes a screen gets now that it did not before; firmware before 0.19.0 reads none of them and skips them.
NEW_ATTRIBUTES = {'target_temp_low', 'target_temp_high', 'target_temp_step', 'preset_mode', 'preset_modes'}


def intended_control_change(entity, attributes, old, new):
    """Why a screen before firmware 0.19.0 gets other controls for this tile now, or None when there is no reason.

    A thermostat without a single temperature (only a range, or none at all) got a -/+ that drew "--" and stepped from
    its lowest temperature; it goes without them (core.drawn_controls): setpoint becomes none, setpoint_mode the mode keys.
    """
    flags = attributes.get('supported_features')
    if not entity.startswith('climate.') or not isinstance(flags, int) or flags & 1:
        return None
    changed = {key for key in set(old) | set(new) if old.get(key) != new.get(key)}
    if changed != {'controls'}:
        return None
    if (old['controls'], new['controls']) in (('setpoint', 'none'), ('setpoint_mode', 'mode')):
        return 'a thermostat without a single temperature loses the -/+ it drew wrong'
    return None


class UpdateFrom0431(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(GOLDEN, 'rt', encoding='utf-8') as handle:
            cls.golden = json.load(handle)
        cls.now = compat_corpus.run('check', ROOT / 'screen_manager/app', cls.golden)
        data = json.loads(compat_corpus.FIXTURE.read_text())
        cls.states = {**data['states'], **compat_corpus.SYNTHETIC}

    def saved(self):
        """(key, what 0.4.31 did, what this app does) for every case 0.4.31 saved."""
        for key, old in self.golden['cases'].items():
            if 'refused' not in old:
                yield key, old, self.now['cases'][key]

    def test_the_corpus_is_what_it_was_recorded_from(self):
        self.assertEqual(set(self.golden['cases']), set(self.now['cases']))
        self.assertGreater(sum('refused' not in case for case in self.golden['cases'].values()), 14000)

    def test_every_saved_page_loads_and_compiles_to_the_same_tiles(self):
        broken = {key: new['broken'] for key, _, new in self.saved() if 'broken' in new}
        self.assertEqual(broken, {})
        differ = [key for key, old, new in self.saved() if new['compiled'] != old['compiled']]
        self.assertEqual(differ, [])

    def test_no_saved_page_asks_for_newer_firmware(self):
        differ = {key: (old['min_firmware'], new['min_firmware']) for key, old, new in self.saved() if new['min_firmware'] != old['min_firmware']}
        self.assertEqual(differ, {})

    def test_no_saved_setting_is_refused(self):
        refused = {key: new['unsupported'] for key, _, new in self.saved() if any(new['unsupported'])}
        self.assertEqual(refused, {})

    def test_a_screen_not_updated_gets_what_it_got_but_for_the_listed_fixes(self):
        unexplained, fixed = [], 0
        for key, old, new in self.saved():
            for before, after in zip(old['old_screen'], new['old_screen']):
                self.assertEqual((before['entity'], before['name'], before['state']), (after['entity'], after['name'], after['state']), key)
                added = set(after['a']) - set(before['a'])
                self.assertLessEqual(added, NEW_ATTRIBUTES, key)
                self.assertEqual({k: v for k, v in after['a'].items() if k not in added}, before['a'], key)
                if before['o'] != after['o']:
                    reason = intended_control_change(before['entity'], (self.states.get(before['entity']) or {}).get('attributes') or {}, before['o'] or {}, after['o'] or {})
                    if reason:
                        fixed += 1
                    else:
                        unexplained.append((key, before['o'], after['o']))
        self.assertEqual(unexplained, [])
        # The fix reaches the thermostats it is for, and only those.
        self.assertGreater(fixed, 0)


if __name__ == '__main__':
    unittest.main()
