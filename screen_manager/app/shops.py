"""Where to buy a recommended screen (app 0.4.110): New screen's "No screen yet?" under the recommended boards.

The Tessera website keeps, per board, the shop links its owner chose (its admin, "Where to buy"); a link marked as an
affiliate link pays Tessera a small part of a sale and may give the buyer a discount. The website lists the recommended,
established boards that have one at api/v1/addon/shops, and this module asks it: at most once in SHOPS_TTL, with nothing
of the house in the request, and keeps the answer in memory. The photo of each screen comes through the app as well
(api/shops/<board>/photo), so the browser in Home Assistant asks the website for nothing.

When the website can't be asked, New screen shows no panel: an empty list, never an error.
"""
import asyncio
import logging
import re
import time
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

LOG = logging.getLogger('screen_manager')

SHOPS_URL = 'https://tessera-maxgramser.on-forge.com/api/v1/addon/shops'
SITE_HOST = 'tessera-maxgramser.on-forge.com'
SHOPS_TTL = 6 * 3600
RETRY_TTL = 15 * 60
PHOTO_LIMIT = 2 * 1024 * 1024
BOARD = re.compile(r'[a-z0-9_]{1,40}')
PHOTO_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


def text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def https(url, host=None):
    if not isinstance(url, str) or len(url) > 2048:
        return False
    parts = urlsplit(url)
    return parts.scheme == 'https' and bool(parts.hostname) and (host is None or parts.hostname == host)


def clean(rows):
    """Only what New screen shows, checked: a shop link must be https, a photo must come from the website."""
    shops = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not BOARD.fullmatch(str(row.get('id') or '')) or not https(row.get('url')):
            continue
        shops.append({
            'board': row['id'], 'name': text(row.get('name'), 60), 'size': row.get('size') if isinstance(row.get('size'), (int, float)) else None,
            'maker': text(row.get('maker'), 60), 'shop': text(row.get('shop'), 80) or urlsplit(row['url']).hostname,
            'url': row['url'], 'discount': text(row.get('discount'), 40), 'code': text(row.get('code'), 40),
            'photo': row['photo'] if https(row.get('photo'), SITE_HOST) else None,
        })
    return shops


class Shops:
    def __init__(self, clock=time.time, url=SHOPS_URL):
        self.clock, self.url = clock, url
        self.shops, self.until = [], 0.0
        self.photos = {}
        self.session = None
        self.lock = asyncio.Lock()

    def client(self):
        # Its own session: no Home Assistant token or Supervisor header, certificate checks on.
        if self.session is None or self.session.closed:
            self.session = ClientSession()
        return self.session

    async def fetch(self):
        try:
            async with self.client().get(self.url, headers={'Accept': 'application/json'}, timeout=ClientTimeout(total=10),
                                         allow_redirects=False) as response:
                if response.status != 200:
                    return None
                result = await response.json()
        except (ClientError, asyncio.TimeoutError, ValueError):
            return None
        return clean(result.get('data')) if isinstance(result, dict) else None

    async def list(self):
        """The shops for New screen: from memory, asked again after SHOPS_TTL (after RETRY_TTL when the website was away)."""
        async with self.lock:
            now = self.clock()
            if now >= self.until:
                shops = await self.fetch()
                if shops is None:
                    self.until = now + RETRY_TTL
                else:
                    self.shops, self.until = shops, now + SHOPS_TTL
                    self.photos = {board: photo for board, photo in self.photos.items() if any(s['board'] == board for s in shops)}
            return [{**shop, 'photo': bool(shop['photo'])} for shop in self.shops]

    async def photo(self, board):
        """The photo of one shop's screen as (bytes, content type), or None."""
        shop = next((s for s in self.shops if s['board'] == board), None)
        if shop is None or not shop['photo']:
            return None
        if board in self.photos:
            return self.photos[board]
        try:
            async with self.client().get(shop['photo'], timeout=ClientTimeout(total=15), allow_redirects=False) as response:
                kind = (response.headers.get('Content-Type') or '').split(';')[0].strip()
                if response.status != 200 or kind not in PHOTO_TYPES:
                    return None
                # The whole file, chunk by chunk (a single read returns only what has arrived), never past the limit.
                body = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    body += chunk
                    if len(body) > PHOTO_LIMIT:
                        return None
        except (ClientError, asyncio.TimeoutError):
            return None
        self.photos[board] = (bytes(body), kind)
        return self.photos[board]

    async def close(self):
        if self.session is not None and not self.session.closed:
            await self.session.close()
