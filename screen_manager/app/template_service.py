"""The template tiles' subscriptions (docs/TEXT_TILE.md): one `render_template` in Home Assistant per template on a
screen, and the last result of each, for text_tile.block to turn into the tile's rows.

Home Assistant renders the template again whenever an entity it reads changes, and paces templates that read the time
or every state itself, so this app never polls. A burst of results (a template over many sensors) reaches the screens
at most every PACE_SECONDS: a result marks `screen.text` dirty, and the sync loop sends only the tiles whose message
changed. While Home Assistant is away the last results stay, so a screen keeps what it shows; the error row is for a
template Home Assistant refuses, never for a lost connection.
"""
from __future__ import annotations

import asyncio
import logging
import time

import text_tile

LOG = logging.getLogger('screen_manager')
PACE_SECONDS = 0.5
# How long the editor's preview waits for Home Assistant's first result.
PREVIEW_SECONDS = 5


class Refused(Exception):
    """Home Assistant would not render the template (its own words)."""


class Result:
    __slots__ = ('text', 'error', 'listeners')

    def __init__(self, text=None, error=None, listeners=None):
        self.text, self.error, self.listeners = text, error, listeners

    def block(self, budget):
        """The tile's `md` (text_tile's wire form), or None while Home Assistant has given nothing yet."""
        if self.error is not None:
            return text_tile.error(self.error)
        return None if self.text is None else text_tile.block(self.text, budget)


def result_of(event):
    """A render_template event as a Result: its text, or its error (a warning is not one: Home Assistant still renders)."""
    event = event if isinstance(event, dict) else {}
    if 'result' in event:
        result = event['result']
        return Result(text='' if result is None else result if isinstance(result, str) else str(result),
                      listeners=listeners_of(event.get('listeners')))
    if event.get('level') == 'ERROR' or ('error' in event and 'level' not in event):
        return Result(error=str(event.get('error') or ''))
    return None


def listeners_of(raw):
    """What makes Home Assistant render the template again (its `listeners`): the entities and domains it reads, whether
    it reads every state (Home Assistant then renders it at most once a minute) and whether it reads the time."""
    raw = raw if isinstance(raw, dict) else {}
    names = lambda key: sorted(str(item) for item in raw.get(key) or [] if isinstance(item, str))[:40]
    return {'entities': names('entities'), 'domains': names('domains'), 'all': raw.get('all') is True, 'time': raw.get('time') is True}


class TemplateService:
    """`ha` is the Home Assistant client: subscribe_template(template, callback) -> id, unsubscribe_template(id),
    `online`, `connection` (a number that grows with every new websocket), `dirty` and `changed`."""

    def __init__(self, ha, clock=time.monotonic):
        self.ha, self.clock = ha, clock
        self.results = {}  # template -> Result
        self.subs = {}  # template -> (subscription id, connection)
        self.marked = 0.0
        self.waiting = None

    def result(self, template):
        return self.results.get(template)

    async def sync(self, wanted):
        """Subscribe every template in `wanted` that has none on this connection, and end the ones no tile has any more."""
        connection = getattr(self.ha, 'connection', 0)
        for template in [t for t, (_, on) in self.subs.items() if t not in wanted or on != connection]:
            sub, on = self.subs.pop(template)
            if on == connection and getattr(self.ha, 'online', False):
                try:
                    await self.ha.unsubscribe_template(sub)
                except Exception as error:
                    LOG.debug('Ending a template subscription failed (%s)', type(error).__name__)
        for template in [t for t in self.results if t not in wanted]:
            del self.results[template]
        if not getattr(self.ha, 'online', False):
            return
        for template in wanted:
            if template in self.subs:
                continue
            try:
                sub = await self.ha.subscribe_template(template, lambda event, template=template: self.received(template, event))
            except Refused as error:
                self.received(template, {'error': str(error), 'level': 'ERROR'})
                # Asked again on the next connection, or when the template changes.
                self.subs[template] = (None, connection)
                continue
            except (ConnectionError, TimeoutError):
                return
            self.subs[template] = (sub, connection)

    def received(self, template, event):
        """A result of Home Assistant's: kept, and the screens told at most every PACE_SECONDS."""
        result = result_of(event)
        if result is None:
            return
        old = self.results.get(template)
        if old is not None and old.text == result.text and old.error == result.error:
            return
        self.results[template] = result
        self.mark()

    def mark(self):
        now = self.clock()
        if now - self.marked >= PACE_SECONDS:
            self.marked = now
            self.ha.dirty.add(text_tile.TEXT_TILE)
            self.ha.changed.set()
            # An open firmware preview in the editor asks for its packets again (preview_events.py).
            events = getattr(self.ha, 'state_events', None)
            if events is not None:
                events.notify(text_tile.TEXT_TILE)
        elif self.waiting is None:
            self.waiting = asyncio.get_running_loop().call_later(PACE_SECONDS - (now - self.marked), self._later)

    def _later(self):
        self.waiting = None
        self.mark()

    async def preview(self, template):
        """One rendering for the editor: the Result of Home Assistant's first answer, then the subscription ends."""
        done = asyncio.get_running_loop().create_future()

        def first(event):
            result = result_of(event)
            if result is not None and not done.done():
                done.set_result(result)
        try:
            sub = await self.ha.subscribe_template(template, first)
        except Refused as error:
            return Result(error=str(error))
        try:
            return await asyncio.wait_for(done, PREVIEW_SECONDS)
        except TimeoutError:
            return Result(error='Home Assistant gave no result in time')
        finally:
            try:
                await self.ha.unsubscribe_template(sub)
            except Exception:
                pass


def wanted_templates(tile_lists, limit=text_tile.DEFAULT_TILES):
    """The templates of every screen's template tiles, at most `limit` per screen (the first ones, in tile order)."""
    wanted = set()
    for tiles in tile_lists:
        count = 0
        for tile in tiles:
            if tile.get('entity') != text_tile.TEXT_TILE:
                continue
            template = (tile.get('options') or {}).get(text_tile.OPTION)
            if isinstance(template, str) and count < limit:
                wanted.add(template)
                count += 1
    return wanted
