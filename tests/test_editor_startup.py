"""Opening ESP Screens.

App 0.2.58: the page asks for the full inventory and opens the live stream at the same time. An add-on that is
building firmware answers the stream first, whose light payload has screens but no entities. The page keeps the
catalogue it has on a light poll and every name on the page follows the inventory, so the first full inventory
fills in what was missing.

App 0.2.65: the page no longer opens the first screen by itself; the owner picks one. Until then a card asks for
that, or offers the install when there are no screens yet.

App 0.2.73: the page is the Vue app in web/; these tests read its source (tests/editor_sources.py).
"""
import re
import sys
import unittest
from pathlib import Path

import editor_sources  # noqa: E402

SCRIPT = editor_sources.SCRIPT


class Startup(unittest.TestCase):
    def test_no_screen_opens_by_itself(self):
        self.assertNotIn('inventory.screens[0]', SCRIPT)
        # The ways into a screen are its button in the list and its row in the ⌘K search; both pass the chosen screen.
        # The logo goes home (app 0.4.0): select(null), nothing chosen, never another screen. A new preview screen opens
        # itself (the session's createVirtualScreen). Layoutbot opens another screen only under the person's own tap on
        # its Show or Yes, and Yes goes back to the screen the person was on (home). Choosing is the session's
        # (stores/session.ts). On its way through the other screens Yes opens each in place of the browser's entry
        # (select's `replace`), so Back never lands on one of them (web/tests/layoutbot-phone.spec.ts).
        # session.openTab opens a screen on one of its tabs (select(id)) for the person's tap on a build's message, a
        # screen's plugin key in the sidebar, a row of Settings, ⌘K or a plugin tile's key: those are its only callers.
        # New screen opens the screen it just installed (install.made) only under the person's tap on "To your pages" at
        # its end (components/install/Progress.vue, toPages), never when the install finishes by itself.
        self.assertEqual(set(re.findall(r'(?<![\w.])(?<!function )(?:session\.)?select\(([^),]*)[,)]', SCRIPT)),
                         {'screen.id', 'null', 'other.id', 'home', 'id', 'install.made.id'},
                         'a screen opens only when the person chooses it: a new select() needs a person\'s tap behind it')
        progress = editor_sources.source('components/install/Progress.vue')
        self.assertRegex(progress, r'function toPages\(\) \{ if \(install\.made\) session\.select\(install\.made\.id\)')
        self.assertRegex(progress, r'id="install-pages" @click="toPages"', 'New screen opens its screen only on the tap on To your pages')
        self.assertEqual(progress.count('toPages'), 2, 'toPages is the button\'s alone')
        session = editor_sources.source('stores/session.ts')
        body = session[session.index('async function openTab('):]
        self.assertIn('await select(id)', body[:body.index('\n  }\n')], 'openTab opens the screen it is given')
        callers = sorted(re.findall(r'(?<!function )openTab\(([^,]+),', SCRIPT))
        self.assertEqual(callers, sorted(['screen.id', 'scr.selected', 'screen.value!.id', 'screen.id', 'screen.id', 'screen.id']),
                         'openTab is asked for the screen of a person\'s tap only (and the open screen)')
        bot = editor_sources.source('stores/layoutbot.ts')
        for argument, function in (('other.id', 'preview'), ('other.id', 'deliver'), ('home', 'deliver')):
            body = bot[bot.index(f'async function {function}('):]
            self.assertIn(f'select({argument}', body[:body.index('\n  }\n')], f'layoutbot opens {argument} only in {function}')
        self.assertEqual(len(re.findall(r'select\((?:other\.id|home)[,)]', SCRIPT)), 3, 'layoutbot opens another screen in preview and deliver only')
        chat = editor_sources.component('LayoutBotChat')
        self.assertEqual(re.findall(r'bot\.(preview|deliver)\(', SCRIPT), ['preview', 'deliver'],
                         'Show and Yes in the chat are the only ways into preview and deliver')
        self.assertIn('@click="bot.preview(other)"', chat)
        self.assertIn('@click="bot.deliver(message)"', chat)
        self.assertIn('const asking = scr.selected ? select(null) : undefined;', editor_sources.source('stores/session.ts'))
        # In the list a click chooses the screen (app 0.2.108; its details fold behind a chevron since app 0.4.0); the
        # choosing is still select's. The overview's cards choose a screen the same way.
        sidebar = editor_sources.component('Sidebar')
        self.assertIn('@click="choose(screen)"', sidebar)
        self.assertIn('  session.select(screen.id);\n}', sidebar)
        self.assertIn('@click="session.select(screen.id)"', editor_sources.component('HomeView'))
        self.assertIn('openScreen: (screen) => session.select(screen.id)', editor_sources.component('CommandPalette'))
        # A new inventory opens nothing either: the inventory store knows no screen to open (stores/inventory.ts).
        inventory = editor_sources.source('stores/inventory.ts')
        for name in ('refresh', 'applyLive'):
            body = inventory[inventory.index(f'function {name}('):]
            self.assertNotRegex(body[:body.index('\n  }\n')], r'(?<![\w.])select\(', name)
        self.assertNotIn('select(', inventory)

    def test_the_right_side_asks_for_a_screen_until_one_is_chosen(self):
        empty = editor_sources.component('EmptyState')
        choose = re.search(r'<section v-if="inv.inventory.screens.length" id="choose" class="empty">(.*?)</section>', empty, re.S)
        self.assertTrue(choose, 'the card asks for a screen while there are screens')
        self.assertIn('<h2>{{ t("editor.empty.choose.title") }}</h2>', choose[1])
        self.assertEqual(editor_sources.text('empty.choose.title'), 'Choose a screen')
        self.assertNotIn('<button', choose[1], 'the list beside it is the choice')
        self.assertIn('id="empty" class="empty"', empty, 'the install card when there are no screens yet')
        self.assertIn('id="start"', empty)
        # With screens and none chosen, the right side is the overview of every screen (app 0.4.0); the card that asks
        # for a screen stays for a chosen screen whose layout is still on its way.
        app = editor_sources.source('App.vue')
        self.assertIn('if (scr.currentScreen && doc.layout) return ScreenView;', app)
        self.assertIn('return scr.selected || !inv.inventory.screens.length ? EmptyState : HomeView;', app)

    def test_a_light_poll_keeps_the_catalogue_and_names_follow_the_inventory(self):
        inventory = editor_sources.source('stores/inventory.ts')
        self.assertIn('inventory.value = full ? data : { ...inventory.value, ...data };', inventory)
        self.assertIn('inventory?light=1', inventory)
        # Names come from the inventory at render time, so they appear as soon as the full inventory does.
        self.assertIn('return inv.entityOf(id)?.name ||', editor_sources.source('stores/entities.ts'))
        self.assertIn('for (const entity of inventory.value.entities) if (!index.has(entity.id)) index.set(entity.id, entity);', inventory)
        self.assertIn('entityName(props.tile.entity)', editor_sources.source('composables/useTileCard.ts'))


if __name__ == '__main__':
    unittest.main()
