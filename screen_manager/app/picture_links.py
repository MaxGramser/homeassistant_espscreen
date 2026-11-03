"""The camera port: the links a screen downloads its pictures from (docs/PICTURES.md, "In ESP Screen Manager").

A screen never asks Home Assistant for a picture and never holds a Home Assistant token: this app answers its question
with a link on its own port on the LAN (8098), random and short-lived, and the screen downloads the picture there. A
still that is made once (an alert's picture, a plugin's places, a photo) is kept as bytes; a picture that changes by
itself (a camera at its pace, a map someone moves on) is a recipe, painted again when the screen loads its link, with an
ETag of what it shows, so an unchanged picture answers 304. A stream (`.mjpeg`, live_stream) is served beside them. The
address the links carry, where the screens reach this app, is lan_address's.
"""
import hashlib
from email.utils import formatdate
import os
import secrets
import time

PORT = 8098
# A link to a picture that changes by itself nobody used for this long is forgotten; the screen asks for a new one.
LINK_SECONDS = 120
# A still stays loadable this long (an alert's picture, which its camera may also be opened from).
STILL_SECONDS = 1800
# A screen whose firmware asks for each tile's picture alone (tile_picture.h) holds a link per tile, so a few screens
# with pages of cameras and covers hold a few dozen at once.
MAX_LINKS = 256
TYPES = {'bmp': 'image/bmp', 'jpg': 'image/jpeg'}


class Link:
    __slots__ = ('still', 'etag', 'recipe', 'used', 'lifetime', 'suffix', 'revalidate')

    def __init__(self, now, still=None, recipe=None, suffix='bmp', revalidate=True):
        self.still, self.recipe, self.used = still, recipe, now
        self.etag = f'"{hashlib.sha1(still).hexdigest()[:16]}"' if still else ''
        self.lifetime = STILL_SECONDS if still is not None else LINK_SECONDS
        self.suffix = suffix
        # Whether an unchanged picture answers 304: every screen since firmware 0.49.0 (picture_fetch); before, ESPHome's
        # http_request logged a 304 as a failed load, and a page of slow cameras would have done that every 15 s.
        self.revalidate = revalidate


class Links:
    """Every link of every screen. `render(recipe)` paints a recipe's picture again: (etag, bytes) or None."""

    def __init__(self, render=None, clock=time.monotonic):
        self.render, self.clock = render, clock
        self.links = {}

    def prune(self):
        now = self.clock()
        for token in [token for token, link in self.links.items() if now - link.used > link.lifetime]:
            del self.links[token]
        while len(self.links) >= MAX_LINKS:
            del self.links[min(self.links, key=lambda token: self.links[token].used)]

    def add(self, still=None, recipe=None, suffix='bmp', revalidate=True):
        """A new random token for one picture: `still` its bytes, or `recipe` what paints it again on every load."""
        self.prune()
        token = secrets.token_urlsafe(18)
        self.links[token] = Link(self.clock(), still, recipe, suffix, revalidate)
        return token

    def __contains__(self, token):
        return token in self.links

    async def serve(self, token, etag=None):
        """(HTTP status, bytes or None, etag, content type) for one load of a screen."""
        link = self.links.get(token)
        now = self.clock()
        if link is None or now - link.used > link.lifetime:
            self.links.pop(token, None)
            return 404, None, '', ''
        link.used = now
        kind = TYPES.get(link.suffix, 'image/bmp')
        if link.still is not None:
            return (304, None, link.etag, kind) if etag == link.etag and link.revalidate else (200, link.still, link.etag, kind)
        found = await self.render(link.recipe) if self.render else None
        if found is None:
            return 503, None, '', kind
        tag, body = found
        return (304, None, tag, kind) if etag == tag and link.revalidate else (200, body, tag, kind)


def web_app(links, stream=None):
    """The camera port: GET /camera/<token>.bmp or .jpg, and /camera/<token>.mjpeg for a stream (live_stream), or .jpg
    on a stream's token for its pictures one an ask, open to the LAN like the screens are."""
    from aiohttp import web

    async def image(request):
        # A live link's token as .jpg: one picture an ask (live_stream.LiveFeed.pull), for firmware whose tiles ask so.
        if stream is not None and request.match_info['suffix'] == 'jpg' and request.match_info['token'] in stream.links:
            return await stream.pull(request, request.match_info['token'])
        status, body, etag, kind = await links.serve(request.match_info['token'], request.headers.get('If-None-Match'))
        # Last-Modified with every picture: ESPHome's online_image (firmware before 0.49.0) warned at every load without one.
        headers = {'Cache-Control': 'no-cache', 'Last-Modified': formatdate(usegmt=True), **({'ETag': etag} if etag else {})}
        if status == 200:
            return web.Response(body=body, content_type=kind, headers=headers)
        if status == 304:
            return web.Response(status=304, headers=headers)
        return web.Response(status=status, text='No image' if status == 503 else 'Unknown link', headers=headers)

    app = web.Application(client_max_size=1024)
    app.router.add_get(r'/camera/{token:[A-Za-z0-9_-]{16,64}}.{suffix:bmp|jpg}', image)
    if stream is not None:
        async def streamed(request):
            return await stream.serve(request, request.match_info['token'])
        app.router.add_get(r'/camera/{token:[A-Za-z0-9_-]{16,64}}.mjpeg', streamed)
    return app


def port():
    try:
        value = int(os.environ.get('SCREEN_CAMERA_PORT', PORT))
    except ValueError:
        return PORT
    return value if 0 < value < 65536 else PORT
