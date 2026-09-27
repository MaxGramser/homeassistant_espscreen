"""Settings (app 0.2.45): New screen, Firmware & USB, firmware updates, Alerts and Claude moved off the main
page into a view of their own. App 0.2.73: the sidebar carries the way in (New screen, Firmware & USB, Alerts,
Settings), each once; the Settings page keeps the updates and Claude."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_sources  # noqa: E402


class SettingsView(unittest.TestCase):
    def setUp(self):
        self.sidebar = editor_sources.component('Sidebar')
        self.settings = editor_sources.component('AppSettingsView')
        self.script = editor_sources.SCRIPT
        self.css = editor_sources.CSS

    def test_the_sidebar_is_the_one_way_to_the_tools(self):
        more = self.sidebar.split('<div class="more">', 1)[1]
        self.assertEqual(re.findall(r'<button id="([\w-]+)"', more), ['open-alerts', 'open-settings', 'refresh'])
        self.assertEqual(self.sidebar.count('id="new-screen"'), 1)
        for element in ('new-screen', 'open-alerts', 'open-settings'):
            self.assertEqual(editor_sources.PAGE.count(f'id="{element}"'), 1, element)
        # The firmware tool is no way to add a screen: it stays out of the sidebar but in Settings (app 0.3.27).
        self.assertNotIn("go('#firmware')\"><span class=\"mdi\"", self.sidebar)
        self.assertIn("go('#firmware')", self.settings)

    def test_every_tool_lives_in_the_settings_view_once(self):
        for element in ('updates', 'update-all', 'auto-update', 'claude-install', 'claude-status', 'claude-path', 'claude-download', 'close-settings'):
            self.assertEqual(editor_sources.PAGE.count(f'id="{element}"'), 1, element)
            self.assertIn(f'id="{element}"', self.settings, element)
        # The first-run button stays where a new user starts.
        self.assertIn('id="start"', editor_sources.component('EmptyState'))
        self.assertIn('href="api/claude-skill.zip"', self.settings)

    def test_the_view_switches_by_hash_and_renders_what_it_shows(self):
        store = editor_sources.source('store.ts')
        for marker in ('export const routes = ["", "#settings", "#new-screen", "#firmware", "#alerts", "#override"] as const;',
                       'window.addEventListener("hashchange"', 'export async function installClaudeSkill', 'send("claude-skill", "POST")'):
            self.assertIn(marker, store, marker)
        app = editor_sources.source('App.vue')
        for marker in ('route.value === "#settings") return AppSettingsView', 'route.value === "#new-screen") return InstallerView',
                       'route.value === "#firmware") return FirmwareView', 'route.value === "#alerts") return AlertsView'):
            self.assertIn(marker, app, marker)
        for marker in ('.side', '.nav-item[aria-current="true"]', '.panel', '.card'):
            self.assertIn(marker, self.css, marker)

    def test_the_chosen_screen_is_marked_in_the_list(self):
        self.assertIn(':aria-current="isSelected(screen) ? \'true\' : \'false\'"', self.sidebar)
        rule = self.css.split('\n.nav-item[aria-current="true"] {', 1)[1].split('}', 1)[0]
        self.assertIn('background: var(--seg)', rule)


if __name__ == '__main__':
    unittest.main()
