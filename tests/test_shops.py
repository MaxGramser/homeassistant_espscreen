"""Where to buy a recommended screen (shops.py, app 0.4.110): what the app takes from the website, and how often it asks.

Nothing here reaches the website: fetch is a stand-in that answers as the website would, or not at all.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    import shops

ROW = {'id': 'reterminald1001', 'name': 'reTerminal D1001', 'size': 8.0, 'maker': 'Seeed Studio', 'shop': 'Seeed Studio',
       'url': 'https://www.seeedstudio.com/reTerminal-D1001-p-6729.html?sensecap_affiliate=x', 'discount': '5% off', 'code': 'CODE5',
       'photo': 'https://tessera-maxgramser.on-forge.com/images/stand-d1001.jpg'}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@unittest.skipUnless(HAS_AIOHTTP, 'aiohttp is not installed')
class ShopsTest(unittest.TestCase):
    def test_only_https_shop_links_and_photos_from_the_website_are_kept(self):
        rows = [ROW, {**ROW, 'id': 'bad id'}, {**ROW, 'id': 'guition', 'url': 'http://example.com/x'},
                {**ROW, 'id': 'sensecapd1', 'photo': 'https://elsewhere.example/p.jpg'}, 'nonsense']
        kept = shops.clean(rows)
        self.assertEqual([shop['board'] for shop in kept], ['reterminald1001', 'sensecapd1'])
        self.assertEqual(kept[0]['discount'], '5% off')
        self.assertEqual(kept[0]['code'], 'CODE5')
        self.assertIsNone(kept[1]['photo'])
        self.assertEqual(shops.clean(None), [])

    def test_asks_once_in_a_while_and_shows_nothing_while_the_website_is_away(self):
        clock, answers, asked = Clock(), [None, [ROW], [ROW]], []
        store = shops.Shops(clock=clock)

        async def fetch():
            asked.append(clock.now)
            answer = answers.pop(0)
            return None if answer is None else shops.clean(answer)
        store.fetch = fetch

        async def run():
            self.assertEqual(await store.list(), [])
            self.assertEqual(await store.list(), [])
            clock.now += shops.RETRY_TTL
            listed = await store.list()
            self.assertEqual([shop['board'] for shop in listed], ['reterminald1001'])
            self.assertIs(listed[0]['photo'], True)
            clock.now += shops.SHOPS_TTL - 1
            await store.list()
            return len(asked)
        self.assertEqual(asyncio.run(run()), 2)

    def test_a_photo_only_for_a_listed_screen(self):
        store = shops.Shops()
        self.assertIsNone(asyncio.run(store.photo('reterminald1001')))
        store.shops = shops.clean([ROW])
        store.photos['reterminald1001'] = (b'jpeg', 'image/jpeg')
        self.assertEqual(asyncio.run(store.photo('reterminald1001')), (b'jpeg', 'image/jpeg'))
        self.assertIsNone(asyncio.run(store.photo('guition')))


if __name__ == '__main__':
    unittest.main()
