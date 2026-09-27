"""Open a page from Home Assistant (app 0.2.102, firmware 0.2.87): `esphome.<screen>_show_page` puts one page of
tiles in front the way a Go to page tile does, on every board the same way, and the skill and the guide say so."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import claude_skill  # noqa: E402
from core import FIRMWARE_VERSION, SHOW_PAGE_MIN_FIRMWARE  # noqa: E402

PROFILES = ('checkout/cyd.yaml', 'checkout/guition.yaml', 'packages/cyd.yaml', 'packages/guition.yaml')


def action(text, name):
    """One API action of a profile, up to the next one."""
    found = re.search(rf'^    - action: {name}\n(.*?)(?=^    - action: |^    #|^[a-z_]+:)', text, re.M | re.S)
    return found[1] if found else ''


class ShowPage(unittest.TestCase):
    def setUp(self):
        self.profiles = {name: profiles.text(name) for name in PROFILES}

    def test_the_firmware_that_carries_the_action_is_this_release_or_older(self):
        version = lambda text: tuple(int(part) for part in text.split('.'))
        self.assertLessEqual(version(SHOW_PAGE_MIN_FIRMWARE), version(FIRMWARE_VERSION))

    def test_every_board_opens_a_page_the_way_a_touch_on_a_go_to_page_tile_does(self):
        for name, text in self.profiles.items():
            block = action(text, 'show_page')
            self.assertTrue(block, f'{name}: no show_page action')
            self.assertIn('page: int', block, name)
            # Opened for someone to look at: Back to page 1 counts from now, and a dimmed screen lights up.
            self.assertIn('id(last_use_ms) = millis();', block, name)
            self.assertIn('id(wake_display).execute();', block, name)
            # The settings page and every card close, as go_home does; the page is drawn the way a swipe draws it.
            self.assertIn('settings_screen::close();', block, name)
            self.assertIn('runtime_tiles::go_to_page(std::clamp((int) page, 1, pages) - 1, false);', block, name)
            # 1 is the first page, and a number past the last page lands on the last page, never outside.
            self.assertIn('std::clamp((int) page, 1, pages) - 1', block, name)
            self.assertIn('runtime_tiles::page_count()', block, name)

    def test_the_skill_and_the_guide_explain_it(self):
        text = claude_skill.text()
        self.assertIn('## Open a page on a screen', text)
        section = text.split('## Open a page on a screen', 1)[1].split('\n## ', 1)[0]
        for needle in ('esphome.<device_name>_show_page', f'firmware {SHOW_PAGE_MIN_FIRMWARE} or newer', 'page: 4',
                       '1 for the first page', 'switch.<screen>_back_to_page_1'):
            self.assertIn(needle, section)
        self.assertIn('open a page', claude_skill.DESCRIPTION)
        # claude.ai takes at most 200 characters, and the boards are the catalog's.
        self.assertLessEqual(len(claude_skill.DESCRIPTION), 200)
        self.assertIn('CYD, Guition, Waveshare and Hosyond', claude_skill.DESCRIPTION)
        guide = (ROOT / 'README_EXTENDED.md').read_text(encoding='utf-8')
        self.assertIn('## Open a page from an automation', guide)
        self.assertIn(f'esphome.<screen>_show_page`** (firmware {SHOW_PAGE_MIN_FIRMWARE}+)', guide)


if __name__ == '__main__':
    unittest.main()
