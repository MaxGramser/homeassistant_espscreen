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
import os
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


def page_document(spec, grid):
    """The page document of a spec: every tile loose by migrate_legacy, then each tile inside a block moved into it."""
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
                   'placement': {'row': r, 'column': c, 'columns': w, 'rows': h}, 'tiles': []}
        for tile in list(page['tiles']):
            p = tile['placement']
            if r <= p['row'] and p['row'] + p['rows'] <= r + h and c <= p['column'] and p['column'] + p['columns'] <= c + w:
                page['tiles'].remove(tile)
                section['tiles'].append({**tile, 'placement': {**p, 'row': p['row'] - r, 'column': p['column'] - c}})
        sections.append(section)
    if sections:
        page['sections'] = sections
    return record, plain


class Sections(run.Run):
    def __init__(self, build, out, pictures):
        super().__init__(build, out, pictures, (1280, 800))

    async def send(self, record, region, states):
        grid = send_layout.Grid(record['sourceGrid']['columns'], record['sourceGrid']['rows'])
        compiled = send_layout.compile_tiles(record['layout'], grid)
        values = [send_layout.state_message(i, tile, states) for i, tile in enumerate(compiled)]
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
            await self.send(chosen, region, states)
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
        return 1, shots


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
