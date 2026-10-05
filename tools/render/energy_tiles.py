"""Render the energy card (app 0.4.77, firmware 0.47.0) with the real firmware on the host (tools/render/host.py): every
size the editor offers on the board, the houses of tests/fixtures/energy (moments read from a Home Assistant with a fake
house in its Energy settings), light and Dark mode, and a tap on the solar circle, which opens that sensor's history.

    python3 tools/render/energy_tiles.py guition cyd cyd-portrait waveshare43

Each card's numbers are the add-on's own (core.extras, energy_flow.payload), so a shot is what a screen shows for that
moment. The dots run while a shot is taken; a shot is kept once two snapshots in a row match, so the run waits for the
dots to stand still between frames, or keeps the last one after its timeout.
"""
import argparse
import asyncio
import json
import math
import os
import re
import shlex
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import host  # noqa: E402
import send_layout  # noqa: E402
import core  # noqa: E402
import history_card  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FIXTURES = run.REPO / 'tests/fixtures/energy'
SIZES = ('square', '3x2', '2x3', 'tall', 'wide', 'full')
# (name of the shot, the house, the card's size: None for every size the board offers)
PAGES = [('noon', 'full-noon', None), ('busy', 'full-busy', 'full'), ('ev-night', 'full-ev_night', 'full'),
         ('sell-peak', 'full-sell_peak', 'full'), ('solar-only', 'solar-solar_noon', 'full'),
         ('grid-only', 'grid-flat_evening', 'full'), ('no-settings', None, 'full')]
NEIGHBOURS = [
    ('light.demo', 'Table lamp', {'state': 'on', 'attributes': {'brightness': 180}}),
    ('sensor.demo_temperature', 'Living room', {'state': '21.5', 'attributes': {'unit_of_measurement': '°C'}}),
    ('switch.demo_desk', 'Desk', {'state': 'off', 'attributes': {}}),
    ('light.demo_ceiling', 'Ceiling light', {'state': 'off', 'attributes': {}}),
]
CIRCLE = re.compile(r'energy: circle (\S+) at (\d+),(\d+)')


def house(key):
    if not key:
        return {}, {}
    data = json.loads((FIXTURES / f'{key}.json').read_text())
    return data['prefs'], data['states']


def offered(shape, side, grid, size):
    """The editor's rule (web/src/model/ui-scale.ts energyFits): the card's content at least the least room of
    energy_card.h, with a page bar under the tiles."""
    columns, rows = (grid.columns, grid.rows) if size == 'full' else core.Grid(grid.columns, grid.rows).dimensions(size)
    if columns > grid.columns or rows > grid.rows:
        return False
    if size not in ('square', 'tall', 'wide', 'full') and not core.span_offered(columns, rows, grid):
        return False
    s, compact = shape['spacing'], shape['look'] == 'compact'
    dpi = shape['dpi']
    mm = lambda n: (dpi * n + 12) // 25

    def share(total, n, take):
        out = 0
        for i, left in zip(range(n), range(n, 0, -1)):
            track = (total + left // 2) // left
            total -= track
            out += track if i < take else 0
        return out
    width = share(side['width'] - 2 * s['margin'] - (grid.columns - 1) * s['gap'], grid.columns, columns) + (columns - 1) * s['gap'] - 2 * s['tile_pad'] - 2
    height = share(side['height'] - s['top'] - s['page_bar'] - (grid.rows - 1) * s['gap_y'], grid.rows, rows) + (rows - 1) * s['gap_y'] - 2 * (s['tile_pad'] + 1)
    return width >= mm(30) and height >= mm(25 if compact else 32)


def solar_day(entity, hours):
    """A sunny day of a solar array, in W, for the history card a tap opens."""
    start, end = history_card.window(hours, run.MOMENT)
    changes = []
    for i in range(0, hours * 12 + 1):
        moment = start + i * 300
        hour = ((moment - start) / 3600 + run.MOMENT.hour - hours) % 24
        changes.append((moment, round(max(0.0, math.sin((hour - 6.5) / 13 * math.pi)) * 5600, 1)))
    return history_card.line(entity, hours, changes, start, end, run.MOMENT.tzinfo, None, 'W')


class Study(run.Run):
    def __init__(self, build, out, pictures):
        super().__init__(build, out, pictures, (1280, 720))

    def answer(self, call):
        if call.service != 'esphome.screen_history':
            return
        data = dict(call.data)
        message = solar_day(data['entity'], int(data['hours']))
        task = asyncio.get_running_loop().create_task(
            self.sender.auxiliary({**message, 'view': int(data.get('view', 0))}, session=data.get('session'), revision=data.get('rev')))
        task.add_done_callback(lambda t: t.exception() and self.warnings.append(f'history failed: {t.exception()!r}'))

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
        self.client.subscribe_service_calls(self.answer)
        if 'render_skip_calibration' in self.services:
            await self.call('render_skip_calibration')
        await self.call('render_time', epoch=int(run.MOMENT.timestamp()))
        shape = json.loads((run.REPO / 'screen_manager/app/boards.json').read_text())[self.item.board]
        side = shape['orientations']['portrait' if self.item.rotation else 'landscape']
        grid = send_layout.Grid(side['columns'], side['rows'])
        self.sender = send_layout.api_sender(self.client, services)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        pages = []
        for name, key, size in PAGES:
            for one in ([size] if size else SIZES):
                if offered(shape, side, grid, one):
                    pages.append((f'{name}-{one}', key, one))
        tiles, states, moments = [], {}, []
        for page, (_, key, size) in enumerate(pages):
            first = page * grid.slots
            tiles.append(dict(entity='screen.energy', name='', slot=first, options={'size': size}))
            moments.append(house(key))
            taken = set(grid.footprint(first, size))
            for cell, neighbour in zip([c for c in range(first, first + grid.slots) if c not in taken], NEIGHBOURS):
                tiles.append(dict(entity=neighbour[0], name=neighbour[1], slot=cell))
                states[neighbour[0]] = neighbour[2]
        record = send_layout.migrate_legacy(dict(title='Energy', tiles=tiles), grid)
        compiled = send_layout.compile_tiles(record['layout'], grid)
        values, energy = [], iter(moments)
        for i, tile in enumerate(compiled):
            if tile['entity'] == 'screen.energy':
                prefs, house_states = next(energy)
                values.append(send_layout.state_message(i, tile, house_states, core.extras(tile, house_states, energy=prefs)))
            else:
                values.append(send_layout.state_message(i, tile, states))
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        shots = 0
        for look in ('light', 'dark'):
            if look == 'dark':
                self.client.switch_command(dark.key, True)
                await asyncio.sleep(1.0)
            for page, (name, key, size) in enumerate(pages):
                start = len(self.lines)
                await self.call('render_page', page=page)
                await self.page_done(page)
                await asyncio.sleep(0.5)
                await self.render(f'{name}-{look}', timeout=6)
                shots += 1
                # A tap on the solar circle opens its sensor's history, as Home Assistant's live view opens its more-info.
                if name == 'noon-full':
                    circles = {m[1]: (int(m[2]), int(m[3])) for line in self.lines[start:] for m in [CIRCLE.search(line)] if m}
                    solar = next((at for entity, at in circles.items() if 'solar' in entity), None)
                    if not solar:
                        self.warnings.append(f'no solar circle in the log: {circles}')
                        continue
                    await self.tap(*solar)
                    await asyncio.sleep(2.0)
                    await self.render(f'{name}-history-{look}', timeout=8)
                    shots += 1
                    await self.tap(30, 30)
                    await asyncio.sleep(0.8)
        self.client.switch_command(dark.key, False)
        return len(pages), shots


def sheet(out, key):
    shots = sorted(p for p in (out / key).glob('*-light.png'))
    if not shots:
        return
    names = [p.name[:-len('-light.png')] for p in shots]
    w, h = Image.open(shots[0]).size
    font = ImageFont.truetype(str(run.REPO / 'fonts/Roboto-500.ttf'), 18)
    image = Image.new('RGB', (2 * (w + 24) + 24, len(names) * (h + 48) + 24), '#f5f6f8')
    draw = ImageDraw.Draw(image)
    for row, name in enumerate(names):
        draw.text((24, 24 + row * (h + 48)), f'{key} · {name}', font=font, fill='#17202c')
        for col, look in enumerate(('light', 'dark')):
            path = out / key / f'{name}-{look}.png'
            if path.exists():
                with Image.open(path) as shot:
                    image.paste(shot, (24 + col * (w + 24), 48 + row * (h + 48)))
    image.save(out / f'sheet-{key}.png')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variants', nargs='+')
    parser.add_argument('--out', type=Path, default=run.REPO / '.esphome' / 'energy-tiles' / 'out')
    args = parser.parse_args()
    args.out = args.out.resolve()
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
    pictures = run.Pictures()
    for key in args.variants:
        item = host.variant(key)
        build = host.Build(item, tree=run.REPO, work=None, esphome=esphome)
        started = time.monotonic()
        ok, output = build.compile()
        if not ok:
            print(f'{key}: BUILD FAILED\n{output[-6000:]}', flush=True)
            continue
        study = Study(build, args.out / key, pictures)
        try:
            summary = asyncio.run(study.run())
            sheet(args.out, key)
        except Exception as error:
            summary = f'stopped: {type(error).__name__}: {error}'
        print(f'{key}: {summary} ({time.monotonic() - started:.0f} s) {study.warnings}', flush=True)


if __name__ == '__main__':
    main()
