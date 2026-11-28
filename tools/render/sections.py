"""Render pages with sections (docs/PAGES.md "Sections") with the real firmware on the host, light and dark.

    uv run --no-project --python 3.13 --with esphome==2026.9.0 --with pillow \
        python tools/render/sections.py jc8012p4a1 guition

The layout is a page document as the editor stores it, with sections, sent by the add-on's own Sender, so the screen gets
its sections the way a real one does (the page's message, the hello's `sections` feature, the summaries). States are
made up but shaped as Home Assistant reports them. Shots land in .esphome/render/sections/<variant>/. A page without
sections is rendered too (`plain-*`), which must look as it did before sections (tools/compare_renders.py against a
render of the same layout from before).
"""
import argparse
import asyncio
import json
import os
import re
import shlex
import sys
import time
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import host  # noqa: E402
import send_layout  # noqa: E402

NAMES = {(1, 1): 'single', (2, 1): 'wide', (1, 2): 'tall', (2, 2): 'square'}
DIM = {'supported_color_modes': ['brightness'], 'color_mode': 'brightness'}
TEMP = {'unit_of_measurement': '°C', 'device_class': 'temperature', 'state_class': 'measurement'}
HOUSE = {
    'light.ceiling': ('Ceiling', 'on', {'brightness': 180, **DIM}, {'icon': 'ceiling-light'}),
    'light.dining': ('Dining table', 'on', {'brightness': 120, **DIM}, {'icon': 'lamp'}),
    'light.sofa': ('Sofa lamp', 'off', DIM, {'icon': 'floor-lamp'}),
    'light.kitchen': ('Kitchen spots', 'on', {'brightness': 255, **DIM}, {'icon': 'light-recessed'}),
    'light.hallway': ('Hallway', 'off', DIM, {'icon': 'lightbulb'}),
    'light.desk': ('Desk', 'on', {'brightness': 90, **DIM}, {'icon': 'desk-lamp'}),
    'climate.living': ('Living room', 'heat', {'current_temperature': 20.5, 'temperature': 21, 'hvac_action': 'heating',
                                               'hvac_modes': ['off', 'heat', 'auto'], 'min_temp': 7, 'max_temp': 30,
                                               'target_temp_step': 0.5}, {'icon': 'radiator'}),
    'sensor.outside': ('Outside', '8.6', TEMP, {'icon': 'thermometer'}),
    'sensor.bedroom': ('Bedroom', '18.9', TEMP, {'icon': 'bed'}),
    'sensor.humidity': ('Humidity', '47', {'unit_of_measurement': '%', 'device_class': 'humidity', 'state_class': 'measurement'}, {'icon': 'water-percent'}),
    'lock.front': ('Front door', 'locked', {}, {}),
    'lock.back': ('Back door', 'unlocked', {}, {}),
    'binary_sensor.motion': ('Hallway motion', 'on', {'device_class': 'motion'}, {'icon': 'motion-sensor'}),
    'media_player.tv': ('TV', 'off', {'supported_features': 21437}, {'icon': 'television'}),
    'cover.living_blinds': ('Living room', 'open', {'current_position': 100, 'device_class': 'blind', 'supported_features': 15}, {'icon': 'blinds-open'}),
    'cover.kitchen_blinds': ('Kitchen', 'open', {'current_position': 60, 'device_class': 'blind', 'supported_features': 15}, {'icon': 'blinds-open'}),
}
# A player with its album cover over the whole card (display: cover), its picture answered as the add-on paints it.
PLAYING = {'volume_level': 0.42, 'media_title': 'Evening Drive', 'media_artist': 'Nova Coast', 'media_album_name': 'Low Sun',
           'supported_features': 8321599, 'entity_picture': '/api/media_player_proxy/media_player.x?token=x&cache=ram'}
HOUSE.update({
    'media_player.living': ('Living room', 'playing', PLAYING, {'display': 'cover'}),
    'media_player.kitchen': ('Kitchen', 'playing', PLAYING, {'display': 'cover'}),
    'media_player.office': ('Office', 'playing', PLAYING, {'display': 'cover'}),
    'media_player.den': ('Den', 'playing', PLAYING, {'display': 'cover'}),
    # Cards LVGL draws itself (draw callbacks): a meter's ring and bar, a blind's slats.
    'sensor.power': ('Power', '2.4', {'unit_of_measurement': 'kW', 'device_class': 'power', 'state_class': 'measurement'},
                     {'display': 'meter', 'min': 0, 'max': 5, 'icon': 'flash'}),
    'sensor.power_bar': ('Power', '3.1', {'unit_of_measurement': 'kW', 'device_class': 'power', 'state_class': 'measurement'},
                         {'display': 'meter', 'meter': 'bar', 'min': 0, 'max': 5, 'icon': 'flash'}),
    'cover.blinds': ('Blinds', 'open', {'current_position': 100, 'current_tilt_position': 60, 'device_class': 'blind',
                                        'supported_features': 255}, {'controls': 'tilt', 'icon': 'blinds-open'}),
})
# (title, icon, summary entity, column, row, columns, rows[, contrast[, its tiles follow]]) and the tiles (entity, column, row, columns, rows) on the
# page's grid: loose ones where no block is.
TEN = dict(grid=(6, 5), sections=[
    ('Lights', 'lightbulb-group', 'sensor.outside', 0, 1, 2, 3),
    ('Climate', 'thermometer', 'sensor.bedroom', 2, 1, 2, 3),
    ('Security', 'shield-home', '', 4, 1, 2, 3, True, True),
], tiles=[
    ('lock.front', 0, 0, 1, 1), ('media_player.tv', 1, 0, 1, 1), ('binary_sensor.motion', 2, 0, 1, 1),
    ('light.ceiling', 0, 1, 1, 1), ('light.dining', 1, 1, 1, 1), ('light.sofa', 0, 2, 1, 1), ('light.kitchen', 1, 2, 1, 1),
    ('light.hallway', 0, 3, 1, 1), ('light.desk', 1, 3, 1, 1),
    ('climate.living', 2, 1, 2, 1), ('sensor.humidity', 2, 2, 1, 1), ('sensor.outside', 3, 2, 1, 1),
    ('lock.back', 4, 1, 1, 1), ('cover.living_blinds', 5, 1, 1, 1), ('cover.kitchen_blinds', 4, 2, 1, 1),
])
FOUR = dict(grid=(2, 3), sections=[('Lights', 'lightbulb-group', 'sensor.outside', 0, 1, 2, 2)], tiles=[
    ('sensor.outside', 0, 0, 1, 1), ('lock.front', 1, 0, 1, 1),
    ('light.ceiling', 0, 1, 1, 1), ('light.sofa', 1, 1, 1, 1), ('light.desk', 0, 2, 1, 1), ('light.kitchen', 1, 2, 1, 1),
])
PAGES = {'jc8012p4a1': TEN, 'guition': FOUR, 'reterminald1001': TEN}
# Pictures in sections: a cover's corners are rounded over what is behind its card, the page, a section's panel, a
# contrast section's dark panel, and the other look's panel where the tiles follow the contrast.
COVERS = dict(grid=(6, 5), sections=[
    ('Music', 'music', '', 0, 0, 2, 3, True),
    ('Following', 'music', '', 2, 0, 2, 3, True, True),
    ('Plain', 'speaker', '', 4, 0, 2, 3),
], tiles=[
    ('media_player.living', 0, 0, 2, 2), ('media_player.tv', 0, 2, 2, 1),
    ('media_player.kitchen', 2, 0, 2, 2), ('light.ceiling', 2, 2, 2, 1),
    ('media_player.office', 4, 0, 2, 2), ('light.desk', 4, 2, 1, 1),
    ('media_player.den', 0, 3, 2, 2),
])
WITH_COVERS = {'jc8012p4a1', 'reterminald1001'}
# What LVGL draws itself in a following section and the same cards loose on the page: drawn in their card's look.
DRAWN = dict(grid=(6, 5), sections=[
    ('Following', 'flash', '', 0, 0, 4, 2, True, True),
], tiles=[
    ('sensor.power', 0, 0, 2, 2), ('sensor.power_bar', 2, 0, 1, 2), ('cover.blinds', 3, 0, 1, 2),
    ('sensor.power', 0, 3, 2, 2), ('sensor.power_bar', 2, 3, 1, 2), ('cover.blinds', 3, 3, 1, 2),
])


def page_document(spec, grid):
    """The page document of a spec: every tile on its page by migrate_legacy, and the sections as their blocks (a tile is
    a section's by lying in its block, page_layout.section_of)."""
    columns, rows = spec['grid']
    tiles = []
    for entity, c, r, w, h in spec['tiles']:
        name, _, _, options = HOUSE[entity]
        tiles.append(dict(entity=entity, name=name, slot=r * columns + c, options={**options, 'size': NAMES.get((w, h), f'{w}x{h}')}))
    record = send_layout.migrate_legacy(dict(title='Home', tiles=tiles), grid)
    record['sourceGrid'] = {'columns': columns, 'rows': rows}
    plain = deepcopy(record)
    page = record['layout']['pages'][0]
    sections = []
    for n, (title, icon, summary, c, r, w, h, *contrast) in enumerate(spec['sections']):
        section = {'id': f'5ec7{n:012x}', 'title': title, **({'icon': icon} if icon else {}), **({'summary': summary} if summary else {}),
                   **({'contrast': True} if contrast and contrast[0] else {}),
                   **({'contrastTiles': True} if len(contrast) > 1 and contrast[1] else {}),
                   'placement': {'row': r, 'column': c, 'columns': w, 'rows': h}}
        sections.append(section)
    if sections:
        page['sections'] = sections
    return record, plain


class Sections(run.Run):
    def __init__(self, build, out, pictures):
        super().__init__(build, out, pictures, (1280, 800))

    async def send_pages(self, record, region, states):
        grid = send_layout.Grid(record['sourceGrid']['columns'], record['sourceGrid']['rows'])
        compiled = send_layout.compile_tiles(record['layout'], grid)
        from core import extras
        import media_library
        values = [send_layout.state_message(i, tile, states, extras(tile, states)) for i, tile in enumerate(compiled)]
        # A player's cover and its two colours, as the add-on sends them with the state.
        for value in values:
            attributes = states.get(value['entity'], {}).get('attributes', {})
            if attributes.get('entity_picture'):
                value.setdefault('x', {}).update(media_library.player_extras(attributes, 0, '2B484F,121E20'))
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        # The summaries as the add-on words them: the entity's state with its unit.
        sums = [[(f"{states[s['summary']]['state']} {states[s['summary']]['attributes'].get('unit_of_measurement', '')}".strip()
                  if s.get('summary') else '') for s in page.get('sections', [])] for page in record['layout']['pages']]
        await self.sender.synchronize(self.inbox.object_id, record, region, values, bars, sums=sums)

    async def drive(self):
        self.client = run.APIClient('127.0.0.1', self.item.port, None)
        for _ in range(240):
            if self.process.poll() is not None:
                raise RuntimeError(f'the program exited with {self.process.returncode}')
            try:
                await self.client.connect(login=True)
                break
            except Exception:
                await asyncio.sleep(0.5)
        entities, services = await self.client.list_entities_services()
        self.services = {s.name: s for s in services}
        self.inbox = next(e for e in entities if type(e).__name__ == 'TextInfo' and e.name == 'Tile settings')
        dark = next(e for e in entities if getattr(e, 'name', '') == 'Dark mode')
        self.subscribe_logs()
        if 'render_skip_calibration' in self.services:
            await self.call('render_skip_calibration')
        await self.call('render_time', epoch=int(run.MOMENT.timestamp()))
        spec = PAGES[self.item.board]
        columns, rows = spec['grid']
        if self.item.rotation:
            columns, rows = rows, columns
            spec = dict(spec, grid=(columns, rows))
        grid = send_layout.Grid(columns, rows)
        self.sender = send_layout.api_sender(self.client, services)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        states = {entity: {'state': state, 'attributes': attributes} for entity, (_, state, attributes, _) in HOUSE.items()}
        record, plain = page_document(spec, grid)
        shots = 0
        for name, chosen in (('sections', record), ('plain', plain)):
            await self.send_pages(chosen, region, states)
            for look in ('light', 'dark'):
                self.client.switch_command(dark.key, look == 'dark')
                await asyncio.sleep(1.0)
                await self.call('render_page', page=0)
                await self.page_done(0)
                await asyncio.sleep(0.8)
                await self.render(f'{name}-{look}', timeout=6)
                shots += 1
            self.client.switch_command(dark.key, False)
            await asyncio.sleep(0.5)
        if self.item.board in WITH_COVERS and not self.item.rotation:
            shots += await self.covers(region, states, dark)
            shots += await self.drawn(region, states, dark)
            shots += await self.every_card(dark)
            shots += await self.kept_page(dark)
            await self.receiver()
        # Every trade of a card's shared styles between the looks was proven in the program (theme::restyle_checked).
        # A failed trade fails the run (run.Run.run, with the card look's other checks).
        checked = [line for line in self.lines if 'restyle check:' in line]
        if checked:
            self.warnings.append(checked[-1].split('restyle check:', 1)[1].strip())
        return 1, shots

    def trades(self):
        """How many times a card has traded its styles between the looks so far (theme::restyle_checked's count)."""
        counts = [int(line.split('restyle check:', 1)[1].split()[0]) for line in self.lines if 'restyle check:' in line]
        return counts[-1] if counts else 0

    async def kept_page(self, dark):
        """A kept page with a following section (docs/KEPT_PAGES.md): turning to another page and back trades no card's
        styles again and draws the page as it was, pixel for pixel."""
        from datetime import datetime, timezone
        grid = send_layout.Grid(*COVERS['grid'])
        record, values, bars, region = send_layout.configuration(grid, pages=2, now=getattr(run, 'MOMENT', datetime.now(timezone.utc)))
        page = record['layout']['pages'][0]
        page['sections'] = [{'id': '5eca000000000001', 'title': 'Kept', 'icon': 'lightbulb-group', 'contrast': True, 'contrastTiles': True,
                             'placement': {'row': 0, 'column': 0, 'columns': grid.columns, 'rows': grid.rows}}]
        await self.sender.synchronize(self.inbox.object_id, record, region, values, bars, sums=[[''], []])
        async def turn():
            for to in (1, 0):
                await self.call('render_page', page=to)
                await self.page_done(to)
                await asyncio.sleep(0.8)
        # The first turn to page 2 may find it not yet prepared and take page 1's cards for it; after it both are kept.
        await self.call('render_page', page=0)
        await self.page_done(0)
        await turn()
        await asyncio.sleep(3.0)
        before, traded = await self.render('kept-before', timeout=6), self.trades()
        await turn()
        after = await self.render('kept-after', timeout=6)
        # Kept (KEPT_PAGES_HOST=1, the path of a board with PSRAM): no card trades again. Without it the host keeps no
        # page and each turn hands the cards to the other page, trading as they go (each trade proven by restyle_checked).
        kept = os.environ.get('KEPT_PAGES_HOST') == '1'
        if kept and self.trades() != traded:
            raise RuntimeError(f'a kept page traded its cards\' styles again on its way back: {traded} -> {self.trades()} trades')
        if before.tobytes() != after.tobytes():
            raise RuntimeError('a kept page with a following section came back drawn otherwise')
        self.warnings.append(f'page with a following section turned and back: the same pixels, {self.trades() - traded} trades on the way'
                             + (' (kept: none)' if kept else ' (no page kept on this host)'))
        return 2

    async def receiver(self):
        """The screen's own reading of a page's sections and of their summaries (page_receiver.cpp), case by case, each
        sent as the add-on's Sender sends it, with the page message changed on its way where a case asks: what it places
        (module_sections.h's "page N: K drawn" and, on the host, "none drawn"), what it refuses ("Error: sections", the layout before it
        staying whole), a `sums` update right or wrong, and a layout from an app that knows no sections."""
        from datetime import datetime, timezone
        grid = send_layout.Grid(*COVERS['grid'])
        record, values, bars, region = send_layout.configuration(grid, pages=2, now=getattr(run, 'MOMENT', datetime.now(timezone.utc)))
        page = record['layout']['pages'][0]
        page['sections'] = [
            {'id': '5ecb000000000001', 'title': 'Living room downstairs', 'icon': 'sofa', 'summary': 'sensor.outside',
             'placement': {'row': 0, 'column': 0, 'columns': 3, 'rows': 2}},
            {'id': '5ecb000000000002', 'title': 'Kitchen', 'contrast': True, 'contrastTiles': True,
             'placement': {'row': 0, 'column': 3, 'columns': 3, 'rows': 2}}]
        sums = [['8.6 °C', ''], []]
        service = self.services['screen_message']
        change = {}  # 'page': how a page message is changed on its way; 'unknowing': the hello says no `sections`

        async def send(message):
            if change.get('page') and message.get('op') == 'page' and message.get('p') == 0:
                message = change['page'](deepcopy(message))
            answer = await self.client.execute_service(service, {'message': json.dumps(message, ensure_ascii=False, separators=(',', ':'))},
                                                       return_response=True)
            if answer is None or not answer.success:
                raise RuntimeError(answer.error_message if answer else 'No screen response')
            data = json.loads(answer.response_data)
            if change.get('unknowing') and message.get('op') == 'hello' and isinstance(data.get('features'), list):
                data['features'] = [name for name in data['features'] if name != 'sections']
            return data
        sender = send_layout.Sender(send)
        revision = [0]

        async def deliver(what):
            """The layout sent whole again under a new revision (another page title, through a fresh session, so not as a
            paint update), its page 0 placed; the line that says what it drew."""
            revision[0] += 1
            sender.session = sender.confirmed = None
            page['topbar']['title'] = {'source': 'text', 'text': f'Sections {revision[0]}'}
            start = len(self.lines)
            await sender.synchronize(self.inbox.object_id, record, region, values, bars, sums=sums)
            await self.call('render_page', page=1)
            await self.call('render_page', page=0)
            await self.page_done(0)
            said = lambda line: re.search(r'sections.*page 0: (\d+ drawn|none drawn)', line)
            await self.until(said, 10, what, start)
            # The page may be placed more than once on its way (prepared, then shown): what it ends with counts.
            await asyncio.sleep(1.0)
            self.said = [line for line in self.lines[start:] if 'sections' in line and 'page 0' in line]
            return [line for line in self.lines[start:] if said(line)][-1]

        def drawn(line):
            found = re.search(r'page 0: (\d+|none) drawn', line)
            return 0 if found[1] == 'none' else int(found[1])

        checked = []
        # 1. A page with two sections: both drawn.
        if drawn(await deliver('a page with two sections')) != 2:
            raise RuntimeError(f'receiver: a page with two sections was not drawn with two: {self.said}')
        checked.append('placed')
        # 2. Its summaries anew, one text each; a count that is not the page's, a page without sections and a page that is
        # not there are refused, and leave the summaries as they were.
        start = len(self.lines)
        await sender._packet({'op': 'sums', 'p': 0, 't': ['9.1 °C', 'Busy']}, sender.confirmed)
        await self.until(lambda line: 'page 0: summaries 9.1 °C|Busy' in line, 5, 'a sums update', start)
        for wrong in ({'p': 0, 't': ['only one']}, {'p': 1, 't': ['no sections here']}, {'p': 7, 't': []}, {'p': 0, 't': 'text'}):
            try:
                await sender._packet({'op': 'sums', **wrong}, sender.confirmed)
            except Exception:
                continue
            raise RuntimeError(f'receiver: a sums update was taken that should not be: {wrong}')
        if any('summaries' in line and 'page 0' in line for line in self.lines[start:] if '9.1 °C|Busy' not in line):
            raise RuntimeError('receiver: a refused sums update changed the summaries')
        checked.append('sums')

        # 3. Page messages whose sections the screen must refuse, whole: what does not fit, what is not a section.
        def sections_as(value):
            def changed(message):
                message['sections'] = value(message['sections']) if callable(value) else value
                return message
            return changed
        bad = {
            'not a list': sections_as('two'),
            'a section of five fields': sections_as(lambda wire: [wire[0][:5], wire[1]]),
            'a column that is text': sections_as(lambda wire: [['0', *wire[0][1:]], wire[1]]),
            'a column past any grid': sections_as(lambda wire: [[9, *wire[0][1:]], wire[1]]),
            'a section past the grid': sections_as(lambda wire: [wire[0], [4, 0, 3, 2, *wire[1][4:]]]),
            'two sections over each other': sections_as(lambda wire: [wire[0], [2, 1, 2, 2, *wire[1][4:]]]),
            'a section without a title': sections_as(lambda wire: [[*wire[0][:5], '', *wire[0][6:]], wire[1]]),
            'seventeen sections': sections_as(lambda wire: [[c % 6, c // 6, 1, 1, '', f'S{c}'] for c in range(17)]),
        }
        for what, how in bad.items():
            change['page'] = how
            try:
                await deliver(what)
            except Exception as error:
                if 'Error: sections' not in str(error):
                    raise RuntimeError(f'receiver: {what}: refused otherwise than "Error: sections": {error}')
            else:
                raise RuntimeError(f'receiver: {what}: the screen took it')
            change.pop('page')
            checked.append(what)
        # The layout before them is whole again with its next delivery: both sections drawn.
        if drawn(await deliver('the layout after the refused ones')) != 2:
            raise RuntimeError(f'receiver: after the refused pages the layout did not come back with its two sections: {self.said}')
        # 4. An app that knows no sections (its pages say none, as every app before them): the page has none, its
        # decorations go; and back.
        change['unknowing'] = True
        # (deliver starts a new session: its hello now names no sections)
        if drawn(await deliver('a layout from an app that knows no sections')) != 0:
            raise RuntimeError(f'receiver: a layout without sections kept the decorations of the one before: {self.said}')
        change.pop('unknowing')
        if drawn(await deliver('sections again')) != 2:
            raise RuntimeError(f'receiver: sections did not come back after a layout without them: {self.said}')
        checked.append('an app without sections')
        self.warnings.append(f'receiver: {len(checked)} section cases held ({", ".join(checked)})')

    async def every_card(self, dark):
        """Every card the harness feeds (diagnostics/send_layout.py: the demo layout and the direct controls), each page
        wrapped whole in one section: once with its tiles in the contrast (the other look), once in contrast only."""
        from datetime import datetime, timezone
        now = getattr(run, 'MOMENT', datetime.now(timezone.utc))
        grid = send_layout.Grid(*COVERS['grid'])
        shots = 0
        for name, controls in (('demo', False), ('controls', True)):
            record, values, bars, region = send_layout.configuration(grid, controls=controls, now=now)
            for kind, follow in (('following', True), ('contrast', False)):
                chosen = deepcopy(record)
                for n, page in enumerate(chosen['layout']['pages']):
                    page['sections'] = [{'id': f'5ec8{n:012x}', 'title': 'Everything', 'icon': 'lightbulb-group', 'contrast': True,
                                         **({'contrastTiles': True} if follow else {}),
                                         'placement': {'row': 0, 'column': 0, 'columns': grid.columns, 'rows': grid.rows}}]
                sums = [[''] for _ in chosen['layout']['pages']]
                await self.sender.synchronize(self.inbox.object_id, chosen, region, values, bars, sums=sums)
                for page in range(len(chosen['layout']['pages'])):
                    for look in ('light', 'dark'):
                        self.client.switch_command(dark.key, look == 'dark')
                        await asyncio.sleep(1.0)
                        await self.call('render_page', page=page)
                        await self.page_done(page)
                        await asyncio.sleep(0.8)
                        await self.render(f'every-{name}-{kind}-p{page}-{look}', timeout=6)
                        shots += 1
                self.client.switch_command(dark.key, False)
        return shots

    async def drawn(self, region, states, dark):
        """Cards whose parts LVGL draws in a draw callback (a meter, a blind's slats), in a following section and loose."""
        record, _ = page_document(DRAWN, send_layout.Grid(*DRAWN['grid']))
        await self.send_pages(record, region, states)
        for look in ('light', 'dark'):
            self.client.switch_command(dark.key, look == 'dark')
            await asyncio.sleep(1.0)
            await self.call('render_page', page=0)
            await self.page_done(0)
            await asyncio.sleep(0.8)
            await self.render(f'drawn-{look}', timeout=6)
        self.client.switch_command(dark.key, False)
        return 2

    async def covers(self, region, states, dark):
        """Covers in sections, each look with its own question (the ground is part of it), answered as the add-on paints
        it: the corners must take the colour behind the card, never a light frame on a dark panel."""
        import media_art
        calls = []
        self.client.subscribe_service_calls(calls.append)
        record, _ = page_document(COVERS, send_layout.Grid(*COVERS['grid']))
        shots, served = 0, 0
        # One cover at a time (the host keeps few pictures): the others play without a picture.
        for player, look in [(p, l) for p in ('media_player.living', 'media_player.kitchen') for l in ('light', 'dark')]:
            alone = {e: ({**v, 'attributes': {k: a for k, a in v['attributes'].items() if k != 'entity_picture'}}
                         if e.startswith('media_player.') and e != player else v) for e, v in states.items()}
            await self.send_pages(record, region, alone)
            self.client.switch_command(dark.key, look == 'dark')
            await asyncio.sleep(1.0)
            await self.call('render_page', page=0)
            await self.page_done(0)
            end = time.monotonic() + 8
            while time.monotonic() < end:
                for call, read in self.unanswered(calls):
                    body, question = run.painted(read.question, [media_art.png(served % 4, 640)])
                    grounds = sorted({f'{p.ground:06X}' for p in question.places if getattr(p, 'ground', None) is not None})
                    print(f'covers {look}: {read.what} asked over {grounds}', flush=True)
                    await self.reply(read, self.pictures.url(f'{self.item.key}-cover-{served}.bmp', body))
                    call.data['_answered'] = '1'
                    served += 1
                await asyncio.sleep(0.1)
            await self.render(f'covers-{player.split(".")[1]}-{look}', timeout=6)
            shots += 1
        self.client.switch_command(dark.key, False)
        return shots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variants', nargs='+')
    parser.add_argument('--out', type=Path, default=run.REPO / '.esphome' / 'render' / 'sections')
    args = parser.parse_args()
    args.out = args.out.resolve()
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
    pictures = run.Pictures()
    failed = False
    for key in args.variants:
        item = host.variant(key)
        build = host.Build(item, tree=run.REPO, work=None, esphome=esphome)
        started = time.monotonic()
        ok, output = build.compile()
        if not ok:
            print(f'{key}: BUILD FAILED\n{output[-6000:]}', flush=True)
            failed = True
            continue
        shot = Sections(build, args.out / key, pictures)
        try:
            summary = asyncio.run(shot.run())
        except Exception as error:
            import traceback
            traceback.print_exc()
            summary, failed = f'stopped: {type(error).__name__}: {error}', True
        print(f'{key}: {summary} shots ({time.monotonic() - started:.0f} s) {shot.warnings}', flush=True)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
