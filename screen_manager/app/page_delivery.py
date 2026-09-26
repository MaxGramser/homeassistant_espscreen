"""Protocol 2 compilation and one serialized, acknowledged sender per screen.

Only the add-on knows older protocols. New firmware receives a complete page
configuration through a bounded transaction, followed by value-only updates.
The document revision used for saving is separate from this content revision.
"""
import asyncio
from copy import deepcopy
import json

from page_layout import compile_tiles, fingerprint, grid_of_record, new_id
from i18n import english

PROTOCOL = 2
MAX_MESSAGE = 4096


class DeliveryError(RuntimeError):
    """A transient transport failure. Retry from a new device-granted session."""


class Refused(DeliveryError):
    """The device refused deterministic input. Do not repeatedly reload it."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message  # Retain a translated Text's key for later readers.


class Superseded(DeliveryError):
    """A newer saved document replaced this delivery target."""


def bounded(message):
    if len(json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()) > MAX_MESSAGE:
        raise Refused(english('addon.errors.too_large'))
    return message


def configuration(record, region):
    """Editor workspace and legacy device settings never change this revision."""
    return fingerprint({"layout": record["layout"], "grid": record["sourceGrid"], "region": region})


def appearance_configuration(record, region, initial_tiles):
    """Separate paint-only fields without keeping another document on the board."""
    layout = deepcopy(record['layout'])
    appearance = {'title': layout.pop('title'), 'pages': [], 'tiles': []}
    index = 0
    for page_index, page in enumerate(layout['pages']):
        title = page['topbar'].pop('title')
        appearance['pages'].append({'p': page_index, 'title': title.get('text', '') if title['source'] == 'text' else ''})
        for tile in sorted(page['tiles'], key=lambda tile: (tile['placement']['row'], tile['placement']['column'])):
            tile['appearance'].pop('label')
            background = tile['appearance'].pop('background', 'auto')
            appearance['tiles'].append({'i': index, 'name': initial_tiles[index]['name'], 'background': background})
            index += 1
    return fingerprint({'layout': layout, 'grid': record['sourceGrid'], 'region': region}), appearance


def page_message(page, index, items, *, initial):
    message = {"op": "page" if initial else "bar", "p": index, "items": items}
    if initial:
        title = page["topbar"]["title"]
        message.update(id=page["id"], title=title.get("text", "") if title["source"] == "text" else "",
                       home_control=bool(page["topbar"]["leading"]), excluded=page["navigation"]["excludeFromPagination"])
    return message


def tile_message(message, tile, *, initial):
    message = deepcopy(message)
    message.pop("v", None)
    if initial:
        message.update(op="tile", slot=tile["slot"])
        message.setdefault("o", {})
    else:
        message["op"] = "state"
        # HA may change an automatic icon with the entity's state. This is a
        # resolved value, separate from the saved icon choice in configuration.
        message["icon"] = message.pop("o", {}).get("icon", "")
    return message


def bar_value_messages(bars, previous):
    """Send each changed resolved value once, with bounded explicit destinations.

    Pages still own their bars. Only identical rendered values share a packet;
    different formatting or colour choices remain independent.
    """
    grouped, replacements = {}, []
    for page, items in enumerate(bars):
        # Conditional visibility can change the number of rendered items without
        # a configuration edit. Replace that bar before addressing its slots.
        if page >= len(previous) or len(items) != len(previous[page]):
            replacements.append({"op": "bar", "p": page, "items": items})
            continue
        for index, item in enumerate(items):
            if page < len(previous) and index < len(previous[page]) and item == previous[page][index]:
                continue
            key = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            message = grouped.setdefault(key, {"op": "bar_value", "item": item, "targets": []})
            message["targets"].append(page * 6 + index)
    return [*replacements, *grouped.values()]


def prepare(inbox, record, region, values, bars):
    """Compile and bound the entire transaction before persistence or delivery.

    Initial states are supplied by the caller so this pure boundary has no HA
    side effects. The real delivery also checks refreshed values here.
    """
    revision = configuration(record, region)
    tiles = compile_tiles(record["layout"], grid_of_record(record))
    pages = record["layout"]["pages"]
    if len(values) != len(tiles) or len(bars) != len(pages):
        raise Refused(english('addon.errors.pages.fields'))
    initial_tiles = [tile_message(value, tile, initial=True) for value, tile in zip(values, tiles)]
    initial_bars = [page_message(page, i, bar, initial=True) for i, (page, bar) in enumerate(zip(pages, bars))]
    live_values = [tile_message(value, tile, initial=False) for value, tile in zip(values, tiles)]
    begin = {"op": "begin", "inbox": inbox, "title": record["layout"]["title"], "pages": len(pages),
             "tiles": len(tiles), "home": next(i for i, p in enumerate(pages) if p["id"] == record["layout"]["homePageId"]), **region}
    for message in [begin, *initial_tiles, *initial_bars, *live_values]:
        bounded({**message, "v": PROTOCOL, "session": "0" * 16, "seq": 0xFFFFFFFF, "rev": revision})
    return begin, initial_tiles, initial_bars, live_values


class Sender:
    """All layout, value, history, option and image messages share this lock.

    send(message) must return the response to that particular API call. It must
    not substitute HA's cached text-entity state. alive() checks that the saved
    configuration being sent is still current after each asynchronous step.
    """

    def __init__(self, send):
        self.send = send
        self.lock = asyncio.Lock()
        self.session = None
        self.sequence = 0
        self.revision = None
        self.confirmed = None
        self.failed_revision = None
        self.failure = None
        self.values, self.bars = [], []
        self.phase = "waiting"
        self.protocol = None
        self.tile_sizes = {"single", "wide", "full"}
        self.last_protocol = None
        self.last_tile_sizes = set(self.tile_sizes)
        self.bar_values = False
        self.appearance_updates = False
        self.group_lamps = False
        self.structure, self.appearance = None, None

    def disconnected(self):
        self.session = self.confirmed = self.protocol = None
        self.tile_sizes = {"single", "wide", "full"}
        self.bar_values = False
        self.appearance_updates = False
        self.group_lamps = False
        self.structure, self.appearance = None, None
        self.phase = "waiting"
        self.failed_revision = self.failure = None

    async def _hello(self):
        request = new_id()
        answer = await self.send({"v": PROTOCOL, "op": "hello", "request": request})
        if isinstance(answer, dict) and answer.get("protocol") == PROTOCOL:
            session = answer.get("session", "")
            if answer.get("request") != request or len(session) != 16 or any(c not in "0123456789abcdef" for c in session):
                raise DeliveryError("The screen returned an unrelated session")
            if answer.get("status") != "Session:" + session:
                raise DeliveryError("The screen did not grant a session")
            sizes = answer.get("tile_sizes", ["single", "wide", "full"])
            self.tile_sizes = {size for size in sizes if isinstance(size, str)} if isinstance(sizes, list) else {"single", "wide", "full"}
            self.protocol, self.session, self.sequence = PROTOCOL, session, 0
            self.last_protocol, self.last_tile_sizes = PROTOCOL, set(self.tile_sizes)
            self.bar_values = answer.get("bar_values") == 1
            self.appearance_updates = answer.get("appearance_updates") == 1
            self.group_lamps = answer.get("group_lamps") == 1
            return PROTOCOL
        # This is an answer from the running old firmware, not cached registry metadata.
        if isinstance(answer, dict) and answer.get("protocol") in (None, 1) and answer.get("status") == "Error: protocol version":
            self.protocol, self.session = 1, None
            self.last_protocol, self.last_tile_sizes = 1, {"single", "wide", "full"}
            return 1
        raise DeliveryError("The running screen's protocol could not be verified")

    async def probe(self):
        async with self.lock:
            return await self._hello()

    async def _packet(self, message, revision):
        if not self.session:
            raise DeliveryError("No verified screen session")
        self.sequence += 1
        if self.sequence > 0xFFFFFFFF:
            raise DeliveryError("A fresh screen session is required")
        packet = bounded({**message, "v": PROTOCOL, "session": self.session, "seq": self.sequence, "rev": revision})
        answer = await self.send(packet)
        if not isinstance(answer, dict) or any(answer.get(k) != v for k, v in
                (("protocol", PROTOCOL), ("session", self.session), ("seq", self.sequence), ("rev", revision))):
            # Rejected packets do not advance the device's sequence. Preserve its
            # useful refusal, but never treat a stale success as acknowledgment.
            status = answer.get("status", "") if isinstance(answer, dict) else ""
            if status.startswith("Error: insufficient") or status.startswith("Error: invalid") or status.startswith("Error: incomplete"):
                raise Refused(english('addon.errors.pages.memory' if status.startswith('Error: insufficient') else 'addon.errors.pages.fields'))
            raise DeliveryError(status or "No matching screen acknowledgment")
        if answer.get("status") not in ("Synced", "Loading tiles"):
            raise DeliveryError(answer.get("status") or "Screen requested synchronization")
        return answer

    async def synchronize(self, inbox, record, region, values, bars, alive=lambda: True):
        """values and bars are resolved snapshots for this validated document.

        Every message is size-checked before begin. Optional histories/images
        may arrive later; tile configuration and an initial HA value may not.
        """
        revision = configuration(record, region)
        if self.failed_revision == revision:
            raise Refused(self.failure)
        pages = record["layout"]["pages"]
        try:
            begin, initial_tiles, initial_bars, live_values = prepare(inbox, record, region, values, bars)
        except Refused as error:
            # No begin was sent, so an already applied document remains valid.
            # Resolved live values may shrink again without a layout edit.
            self.failure, self.phase = error.message, "refused"
            raise
        async with self.lock:
            def current():
                if not alive(): raise Superseded("A newer saved layout is waiting")
            try:
                current()
                replace = self.confirmed != revision or not self.session
                structure, appearance = (appearance_configuration(record, region, initial_tiles) if replace
                                         else (self.structure, self.appearance))
                if replace and self.session and self.confirmed and self.appearance_updates and structure == self.structure:
                    update = {'op': 'appearance', 'base': self.confirmed, 'title': appearance['title'],
                              'pages': [item for item, old in zip(appearance['pages'], self.appearance['pages']) if item != old],
                              'tiles': [item for item, old in zip(appearance['tiles'], self.appearance['tiles']) if item != old]}
                    try:
                        bounded({**update, 'v': PROTOCOL, 'session': self.session, 'seq': 0xFFFFFFFF, 'rev': revision})
                    except Refused:
                        pass  # An unusually large paint edit uses the bounded full transaction.
                    else:
                        answer = await self._packet(update, revision)
                        current()
                        if not answer.get('applied'): raise DeliveryError('The appearance update was not activated')
                        self.revision = revision
                        replace = False
                if replace:
                    self.phase = "applying"
                    if await self._hello() != PROTOCOL:
                        raise Refused(english('editor.pages.update_notice'))
                    if any(message["o"].get("size", "single") not in self.tile_sizes for message in initial_tiles):
                        raise Refused(english('addon.errors.pages.update_tall'))
                    current()
                    answer = await self._packet(begin, revision)
                    self.revision = revision
                    current()
                    if not answer.get("applied"):
                        for message in [*initial_bars, *initial_tiles]:
                            await self._packet(message, revision)
                            current()
                        answer = await self._packet({"op": "commit"}, revision)
                        current()
                    if not answer.get("applied"):
                        raise DeliveryError("The complete page configuration was not activated")
                    # A resumed active revision still needs the latest values.
                    self.values, self.bars = [], []
                for i, message in enumerate(live_values):
                    if i >= len(self.values) or message != self.values[i]:
                        await self._packet(message, revision)
                        current()
                updates = bar_value_messages(bars, self.bars) if self.bar_values else (
                    page_message(page, i, items, initial=False)
                    for i, (page, items) in enumerate(zip(pages, bars))
                    if i >= len(self.bars) or items != self.bars[i])
                for message in updates:
                    await self._packet(message, revision)
                    current()
                self.values, self.bars = deepcopy(live_values), deepcopy(bars)
                self.confirmed, self.phase = revision, "applied"
                self.structure, self.appearance = structure, appearance
                self.failed_revision = self.failure = None
                return revision
            except Refused as error:
                self.failed_revision, self.failure = revision, error.message
                self.session = self.confirmed = None
                self.phase = "refused"
                raise
            except (Exception, asyncio.CancelledError):
                self.session = self.confirmed = None
                self.phase = "waiting"
                raise

    async def ping(self):
        async with self.lock:
            if not self.confirmed: return False
            try:
                answer = await self._packet({"op": "ping"}, self.confirmed)
                if not answer.get("applied"): raise DeliveryError("Screen needs synchronization")
                return True
            except (Exception, asyncio.CancelledError):
                self.disconnected()
                raise

    async def auxiliary(self, message, *, session, revision):
        """Drop a response if the request's view/configuration was superseded."""
        async with self.lock:
            if self.session != session or self.confirmed != revision: return False
            message = {k: v for k, v in message.items() if k not in ("v", "session", "seq", "rev")}
            await self._packet(message, revision)
            return True
