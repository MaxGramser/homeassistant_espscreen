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
            # Opened for someone to look at: Back to page 1 counts from now, and a dimmed screen lights up, first: a
            # layout that came while it stood dark is prepared only once it is lit, and the page waits for that.
            self.assertLess(block.index('screen_standby::the().wake(millis());'), block.index('runtime_tiles::navigation_ready()'), name)
            self.assertIn('runtime_tiles::wanted_page = std::max(1, (int) page);', block, name)
            self.assertIn('id(open_page).execute(page);', block, name)
            opened = re.search(r'^  - id: open_page\n(.*?)(?=^  - id: )', text, re.M | re.S)
            self.assertTrue(opened, name)
            opened = opened[1]
            self.assertIn('screen_standby::the().use(millis());', block, name)
            # The settings page and every card close, as go_home does; the page is drawn the way a swipe draws it.
            self.assertIn('settings_screen::close();', opened, name)
            self.assertIn('runtime_tiles::go_to_page(std::clamp((int) page, 1, pages) - 1, false);', opened, name)
            # 1 is the first page, and a number past the last page lands on the last page, never outside.
            self.assertIn('std::clamp((int) page, 1, pages) - 1', opened, name)
            self.assertIn('runtime_tiles::page_count()', opened, name)
            # A page that waited opens once the pages are ready, from the 1 s interval.
            self.assertIn('runtime_tiles::wanted_page > 0 && runtime_tiles::navigation_ready()', text, name)

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
        self.assertIn('CYD, Guition, Waveshare, Hosyond, Sunton, M5Stack Tab5, reTerminal D1001, CrowPanel, SenseCAP, Freenove and WT32', claude_skill.DESCRIPTION)
        guide = (ROOT / 'README_EXTENDED.md').read_text(encoding='utf-8')
        self.assertIn('## Open a page from an automation', guide)
        self.assertIn(f'esphome.<screen>_show_page`** (firmware {SHOW_PAGE_MIN_FIRMWARE}+)', guide)


if __name__ == '__main__':
    unittest.main()


class FromTheLoop(unittest.TestCase):
    """A page is built on the loop's next pass, never at the bottom of the API's call that asked for it: on top of the API
    and the parser a page and its cards came within 40 bytes of the loop task's 16 KB on a Guition 10.1
    (docs/ARCHITECTURE.md, "The loop's stack"). The host render's pages_from_the_loop round proves the order; here, the
    scripts that build a page for an API call start with a delay of 0 ms, and the latest ask wins."""

    def test_the_page_builders_an_api_call_reaches_start_from_the_loop(self):
        import yaml

        class Loader(yaml.SafeLoader):
            pass
        Loader.add_multi_constructor('!', lambda loader, suffix, node: None)
        core = yaml.load((ROOT / 'packages/core.yaml').read_text(), Loader=Loader)
        scripts = {script['id']: script for script in core['script']}
        for name in ('open_page', 'show_tile_page_soon'):
            first = scripts[name]['then'][0]
            self.assertEqual(first, {'delay': '0ms'}, f'{name} starts on the loop\'s next pass (delay: 0ms)')
            self.assertEqual(scripts[name].get('mode'), 'restart', f'{name}: a second ask before the pass replaces the first')
        # The way home waits its pass in screen_standby.h (go_home, due): its script is that call, and the standby's one
        # timer runs it. tests/test_screen_standby.cpp proves nothing is built before the pass.
        self.assertEqual(scripts['go_home']['then'], [{'lambda': 'screen_standby::the().go_home(millis());'}])
        self.assertEqual(scripts['standby_wait'].get('mode'), 'restart')
        self.assertEqual(scripts['standby_wait']['then'][1], {'lambda': 'screen_standby::the().due(millis());'})
        text = (ROOT / 'packages/core.yaml').read_text()
        self.assertIn('runtime_tiles::layout_changed = []() { id(show_tile_page_soon).execute(); };', text,
                      "a layout's commit asks for its page from the loop")

    def test_standby_goes_to_page_1_before_its_screensaver_opens(self):
        """GitHub #457: with Back to page 1 on standby, a go_home one pass behind the screensaver closed its camera or
        media view 0.2 s after it opened. The order is screen_standby.h's (enter, due): the settings page and the cards
        close, page 1 comes, and the screensaver opens last, all of it one pass after the call that asked.
        tests/test_screen_standby.cpp runs it (page_1_comes_before_the_screensaver); here, that the YAML has no way
        home of its own left that could come behind it."""
        text = (ROOT / 'packages/core.yaml').read_text()
        header = (ROOT / 'components/smart_display/screen_standby.h').read_text()
        test = (ROOT / 'tests/test_screen_standby.cpp').read_text()
        self.assertIn('static void page_1_comes_before_the_screensaver()', test)
        self.assertIn('      if (land || go) home();\n      if (land) glass.apply();', header,
                      'one page 1 however many asked, and the standby shows itself after it')
        for gone in ('go_home_now', 'dim_display', 'script.execute: go_home'):
            self.assertNotIn(gone, text, f'{gone}: the way home and the standby are screen_standby.h\'s')
