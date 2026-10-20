"""A question in, an answer out (docs/PICTURES.md, "In ESP Screen Manager: one service").

Every picture a screen asks for, in the new shape (picture_question) or an older one (picture_legacy), is answered here
the same way: each source checked against the rules (picture_sources.Sources.may), fetched or drawn (Sources.get),
painted for exactly its places (picture_paint) and served on the camera port (picture_links), or, where the screen
streams and the source is a camera, a stream (picture_stream). A painted picture is kept by what it shows, so a camera's
tile that loads again before its camera changed, or a second screen of the same size, costs nothing.
"""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field, replace
import hashlib
import logging

import picture_paint
import picture_question as pq
from picture_sources import Resolved, _Drawn

LOG = logging.getLogger(__name__)

# Painted pictures kept by what they show: a page's tiles of a few screens, their covers and their full views.
KEPT = 48
KEPT_BYTES = 48 * 1024 * 1024
SUFFIX = {'jpeg': 'jpg', 'bmp8': 'bmp', 'bmp24': 'bmp'}
# What a screen names as the formats it takes, best first, is what this app answers in, but a drawn picture (a map, a
# vacuum's map: lines, words and flat colours) goes as the first BMP the screen takes, since JPEG blurs its lines and
# the 8-bit palette keeps them sharp and small. Photographs (a camera, a cover, a photo, a poster) go as the screen
# named first: JPEG on a P4, a tenth of a BMP's bytes (docs/PICTURES.md, "Formats").
DRAWN = ('map:', 'vacuum:')


def format_for(question, resolved):
    """The format to paint `question` in, from what its sources gave (`resolved`)."""
    formats = question.formats or ('bmp24',)
    if any(r.state == 'ok' and str(r.mark).startswith(DRAWN) for r in resolved):
        return next((f for f in formats if f != 'jpeg'), formats[0])
    return formats[0]


@dataclass
class Answer:
    """The link a question is answered with ('' for none now), what goes with the picture (`meta`), and per place the
    source's entity where it gave a picture ('' where it gave none), as an older screen's page reads its answer."""
    url: str = ''
    meta: dict = field(default_factory=dict)
    shown: tuple = ()
    problem: str = ''
    stream: bool = False


@dataclass(frozen=True)
class Recipe:
    """What paints a link's picture again on every load: the screen's inbox and its question."""
    inbox: str
    question: pq.Question


class Service:
    def __init__(self, manager, sources, links, stream=None):
        self.manager, self.sources, self.links, self.stream = manager, sources, links, stream
        self.kept = OrderedDict()
        links.render = self.render

    # ----- answering -----
    async def answer(self, inbox, screen, question, url_of=None):
        """The Answer to `question` from the screen `inbox`, or None while a picture is on its way (no answer: the screen
        asks again). `url_of(token, suffix)` makes a link's address where it is not the camera port's (the editor's
        preview, preview_images)."""
        question = question.scaled(pq.scale_for(question.box, question.cap))
        for source in dict.fromkeys(question.sources):
            problem = self.sources.may(inbox, screen, question, source)
            if problem:
                LOG.info('Picture for %s refused: %s', (screen or {}).get('name', inbox), problem)
                return Answer(problem=problem)
        if url_of is None:
            base = await self.manager.link_base(screen)
            if not base:
                LOG.warning('Pictures: no address for this app on the LAN; set SCREEN_CAMERA_URL')
                return Answer()
            url_of = lambda token, suffix: f'{base}/camera/{token}.{suffix}'
        if question.live and len(question.places) == 1 and self.stream is not None:
            url = self._stream(inbox, screen, question, url_of)
            if url:
                return Answer(url, stream=True, shown=(self._entity(question.sources[0]),))
        found = await self.picture(inbox, screen, question)
        if found is None:
            return None
        if found.state != 'ok':
            return Answer(shown=tuple('' for _ in question.places))
        volatile = found.volatile
        revalidate = question.owner.kind != 'tile' or pq.serves_304(screen)
        suffix = SUFFIX.get(found.format, 'bmp')
        token = self.links.add(recipe=Recipe(inbox, question), suffix=suffix, revalidate=revalidate) if volatile else \
            self.links.add(still=found.body, suffix=suffix, revalidate=revalidate)
        return Answer(url_of(token, suffix), found.meta, found.shown)

    def _entity(self, source):
        return source.param('entity') or source.ref

    def _stream(self, inbox, screen, question, url_of):
        """A stream's link for a question of one place that may stream: the full view of a camera, or a camera tile set
        to Live, on a screen that names the rectangle it streams into. '' when the source is no camera that streams."""
        source, owner = question.sources[0], question.owner
        if source.kind == 'camera' and owner.kind == 'view' and source.ref.startswith('camera.'):
            token = self.stream.link(source.ref, question.live, sound=question.sound, screen=inbox)
            return url_of(token, 'mjpeg')
        if source.kind == 'tile' and owner.kind == 'tile':
            tile = self.sources._tile(inbox, source)
            options = (tile or {}).get('options') or {}
            if tile and options.get('display') == 'live' and tile['entity'].startswith('camera.'):
                contain = options.get('fit') == 'contain'
                token = self.stream.link(tile['entity'], question.live, cover=not contain, warm=question.sound, screen=inbox,
                                         tile=True)
                return url_of(token, 'mjpeg') + ('?fit=contain' if contain else '')
        # A plugin tile's place set to live (plugin API 0.17, ui::live): the camera of its own entity (may() checked it),
        # into the place's room, filled or whole as the place's fit says.
        if source.kind == 'camera' and owner.kind == 'plugin_tile' and source.ref.startswith('camera.'):
            contain = question.places[0].fit in ('contain', 'within', 'whole')
            token = self.stream.link(source.ref, question.live, cover=not contain, screen=inbox, tile=True)
            return url_of(token, 'mjpeg') + ('?fit=contain' if contain else '')
        return ''

    # ----- painting -----
    async def render(self, recipe):
        """(etag, bytes) of a link's picture as it is now, or None when there is none."""
        screen = self.manager.screen(recipe.inbox)
        found = await self.picture(recipe.inbox, screen, recipe.question)
        if found is None or found.state != 'ok':
            return None
        return found.etag, found.body

    async def picture(self, inbox, screen, question):
        """The question's picture now (Painted), or None while its one source is on its way."""
        resolved = await asyncio.gather(*(self.sources.get(inbox, screen, question, source, place)
                                          for source, place in zip(question.sources, question.places)))
        if len(resolved) == 1 and resolved[0].state == 'pending':
            return None
        shown = tuple(self._entity(s) if r.state == 'ok' else '' for s, r in zip(question.sources, resolved))
        if all(r.state != 'ok' for r in resolved):
            return Painted('none', shown=shown)
        places = tuple(self._painted(question, place, r) for place, r in zip(question.places, resolved))
        raws, meta, provisional = [], {}, False
        for place, r in zip(places, resolved):
            raw = r.raw if r.state == 'ok' else None
            if isinstance(raw, _Drawn):
                drawn = await raw.draw(place.w, place.h)
                if raw.meta:
                    meta = raw.meta(place.w, place.h)
                    if asyncio.iscoroutine(meta):
                        meta = await meta
                provisional = provisional or bool(getattr(drawn, 'info', {}).get('provisional'))
                raw = drawn
            raws.append(raw)
        painted = replace(question, places=places)
        fmt = format_for(question, resolved)
        key = (painted.box, painted.places, tuple(r.mark for r in resolved), fmt)
        etag = f'"{hashlib.sha1(repr(key).encode()).hexdigest()[:16]}"'
        body = self.kept.get(key)
        if body is None:
            try:
                body = await asyncio.get_running_loop().run_in_executor(None, picture_paint.paint, painted, raws, fmt)
            except Exception as error:  # noqa: BLE001 - a picture Pillow cannot read
                LOG.info('The picture of %s cannot be painted (%s)', ', '.join(s.text for s in question.sources), type(error).__name__)
                return Painted('none', shown=tuple('' for _ in shown))
            if not provisional:
                self._keep(key, body)
        else:
            self.kept.move_to_end(key)
        return Painted('ok', body, etag, meta, shown, any(r.volatile for r in resolved), fmt)

    def _painted(self, question, place, r: Resolved):
        """The place as its source would have it painted: a camera tile's own fit and shade, the colour beside the
        screensaver's cover, whether a photo moves (only where the larger picture fits the screen's cap)."""
        changes = {}
        if r.fit and place.fit not in ('shrink', 'exact'):
            changes['fit'] = r.fit
        if r.fade is not None:
            changes['fade'] = r.fade
        if r.ground is not None:
            changes['ground'] = r.ground
        if r.move is not None:
            moves = r.move and place.move > 0
            if moves:
                big = (round(place.w * (1 + place.move / 100)), round(place.h * (1 + place.move / 100)))
                moves = pq.capped(big, cap=question.cap) == big
            changes['move'] = place.move if moves else 0
        return replace(place, **changes) if changes else place

    def _keep(self, key, body):
        self.kept[key] = body
        while len(self.kept) > KEPT or sum(len(b) for b in self.kept.values()) > KEPT_BYTES:
            self.kept.popitem(last=False)


@dataclass
class Painted:
    state: str
    body: bytes = b''
    etag: str = ''
    meta: dict = field(default_factory=dict)
    shown: tuple = ()
    volatile: bool = False
    format: str = 'bmp24'
