"""Render map cards (app 0.4.33, firmware 0.20.0) with the real firmware on the host (tools/render/host.py) and the
add-on's own renderer: every size, light and Dark mode, framed around everyone, around home and around one person.

    python3 tools/render/map_tiles.py guition waveshare43 [--tiles DIR]

The program asks for its page's pictures the way it asks ESP Screens (the esphome.screen_camera event with its question,
`q`: the tile by its index, in the screen's look); this script answers as the add-on does (map_card.render_tile,
picture_paint). The streets are Home Assistant's vector tiles, read from `--tiles` (files z_x_y.mvt, as the add-on
fetched them); without them a card is drawn from its zones and people alone, as it is when Home Assistant has no tiles to
give. The people and places are made up: a household in the middle of Amsterdam.
"""
import argparse
import asyncio
import json
import os
import shlex
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import host  # noqa: E402
import send_layout  # noqa: E402
import map_card  # noqa: E402
import picture_question  # noqa: E402
import vector_tiles  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402


def place(entity, name, state, lat=None, lon=None, radius=None):
    attributes = {'friendly_name': name}
    if lat is not None:
        attributes.update(latitude=lat, longitude=lon)
    if radius is not None:
        attributes['radius'] = radius
    return entity, {'state': state, 'attributes': attributes}


STATES = dict([
    place('zone.home', 'Home', '2', 52.35870, 4.86820, 90),
    place('zone.office', 'Office', '1', 52.37600, 4.89780, 140),
    place('zone.school', 'School', '0', 52.35290, 4.89100, 110),
    place('person.alex', 'Alex Morgan', 'home', 52.35878, 4.86835),
    place('person.jo', 'Jo', 'home', 52.35862, 4.86800),
    place('person.sam', 'Sam', 'Office', 52.37590, 4.89800),
    place('person.robin', 'Robin', 'not_home', 52.36420, 4.88310),
    place('device_tracker.car', 'Car', 'not_home', 52.37120, 4.87150),
])
# Drawn avatars, no one's face: Alex and Sam have a picture in Home Assistant, the others their initials.
STATES['person.alex']['attributes']['entity_picture'] = '/api/image/serve/alex/512x512'
STATES['person.sam']['attributes']['entity_picture'] = '/api/image/serve/sam/512x512'


def avatar(background, skin, hair):
    image = Image.new('RGB', (256, 256), background)
    draw = ImageDraw.Draw(image)
    draw.ellipse((48, 170, 208, 330), fill=hair)
    draw.ellipse((78, 52, 178, 162), fill=skin)
    draw.chord((70, 36, 186, 130), 180, 360, fill=hair)
    return image


PHOTOS = {'person.alex': avatar((200, 228, 245), (236, 196, 170), (70, 50, 40)),
          'person.sam': avatar((246, 224, 200), (198, 150, 120), (30, 30, 34))}
EVERYONE = ['person.jo', 'person.sam', 'person.robin']
NEIGHBOURS = [
    ('light.demo', 'Table lamp', {'state': 'on', 'attributes': {'brightness': 180}}),
    ('sensor.demo_temperature', 'Living room', {'state': '21.5', 'attributes': {'unit_of_measurement': '°C'}}),
    ('switch.demo_desk', 'Desk', {'state': 'off', 'attributes': {}}),
    ('binary_sensor.demo_door', 'Front door', {'state': 'off', 'attributes': {'device_class': 'door'}}),
    ('sensor.demo_energy', 'Usage today', {'state': '7.42', 'attributes': {'unit_of_measurement': 'kWh'}}),
    ('light.demo_ceiling', 'Ceiling light', {'state': 'off', 'attributes': {}}),
    ('scene.demo_evening', 'Evening', {'state': '2026-09-15T07:00:00+00:00', 'attributes': {}}),
    ('light.demo_hall', 'Hall', {'state': 'on', 'attributes': {'brightness': 120}}),
]
# (name of the shot, the map tiles of one page: entity, name, size, options)
PAGES = [
    ('full', [('person.alex', 'Family', 'full', {'map': EVERYONE})]),
    ('square', [('person.alex', 'Family', 'square', {'map': EVERYONE})]),
    ('tall-wide', [('person.alex', 'Family', 'tall', {'map': EVERYONE}),
                   ('person.jo', 'Home', 'wide', {'map': ['person.sam', 'person.robin'], 'framing': 'home'})]),
    ('singles', [('person.alex', 'Alex', 'single', {'framing': 'person'}),
                 ('person.sam', 'Sam', 'single', {'framing': 'person', 'distance': 'street'})]),
    # The map of the screen's own cards (firmware 0.21.0): everyone Home Assistant knows the place of.
    ('map-tile', [('screen.map', '', 'square', {})]),
    # An ordinary person tile (firmware 0.21.0): a tap opens where they are, focused on them.
    ('person', [('person.sam', 'Sam', 'single', {'display': 'standard'})]),
]


class Study(run.Run):
    def __init__(self, build, out, pictures, streets):
        super().__init__(build, out, pictures, (1280, 720))
        self.streets = streets

    def answer(self, call):
        if call.service != 'esphome.screen_camera':
            return
        asked = run.asked(dict(call.data), self.screen)
        if asked is None:
            self.warnings.append(f'a question the add-on cannot read: {dict(call.data)}')
            return
        # A page's map tiles (`tile:<index>`), or a map tapped open (`map:<index>`, with a person a finger picked).
        kind = asked.question.sources[0].kind
        work = self.live(asked) if kind == 'tile' else self.full(asked) if kind == 'map' else None
        if work is None:
            return
        task = asyncio.get_running_loop().create_task(work)
        task.add_done_callback(lambda t: t.exception() and 'superseded' not in str(t.exception()) and self.warnings.append(f'answer failed: {t.exception()!r}'))

    async def live(self, asked):
        # Each tile drawn at its place's size in the screen's look, as the add-on draws it (Manager.map_render).
        dark = asked.question.dark
        raws = [lambda w, h, tile=self.compiled[int(source.ref)]: self.draw(tile, (w, h), dark) for source in asked.question.sources]
        body, _ = run.painted(asked.question, raws)
        self.served += 1
        url = self.pictures.url(f'map-{self.served}.bmp', body)
        async with self.turn:
            await self.reply(asked, url)

    def draw(self, tile, size, dark, full=False, focus=None, move=None):
        view = map_card.view_for(tile, STATES, size, self.board, None, full, focus, move)
        streets = {key: self.streets[key] for key in view.tiles() if key in self.streets}
        photos = {e: PHOTOS[e] for e in map_card.pictures_wanted(tile, STATES) if e in PHOTOS}
        return map_card.render_tile(tile, STATES, size, self.board, dark, streets, None, photos, full, focus, move)

    async def full(self, asked):
        """A map tapped open, as the add-on answers it (picture_sources.Sources._map, Manager.map_meta): drawn at the size
        of the screen's question, with where its markers are."""
        source = asked.question.sources[0]
        tile = self.compiled[int(source.ref)]
        if (tile.get('options') or {}).get('display') != 'map':
            # A person's own tile tapped: where that person is, on a map of them alone.
            tile = {'entity': tile['entity'], 'name': tile.get('name', ''), 'options': {'display': 'map', 'distance': 'neighbourhood'}}
        focus = source.param('focus')
        focus = focus if focus in map_card.shown(tile, STATES) else ''
        move = map_card.move_of(source.param('move') or None)

        def draw(w, h):
            self.full_box = (w, h)
            image = self.draw(tile, (w, h), asked.question.dark, True, focus or None, move)
            self.hits = image.info.get('hits', [])
            return image
        body, _ = run.painted(asked.question, [draw])
        self.served += 1
        url = self.pictures.url(f'map-full-{self.served}.bmp', body)
        sheet = {'h': self.hits[:16], 'f': focus}
        if focus:
            # As server.Manager.map_sheet answers: Home Assistant's icon, its word, the value at the right.
            name = STATES[focus]['attributes']['friendly_name']
            sheet['c'] = {'t': name, 'r': [['F0B53', 'Office', 'since 14:02'], ['F0081', 'Battery', '82%'],
                                           ['F0B53', 'Office', '14:02'], ['F0B53', 'Away', '08:31'], ['F0004', 'Home', '07:12']]}
        async with self.turn:
            await self.reply(asked, url, sheet)

    async def picture(self, what, tries=4):
        for attempt in range(tries):
            start = len(self.lines)
            await self.call('render_live_reset')
            try:
                await self.tile_pictures(what, start)
                await asyncio.sleep(0.8)
                return
            except RuntimeError:
                if attempt == tries - 1:
                    raise
                await asyncio.sleep(1)

    async def drive(self):
        self.served, self.turn, self.hits = 0, asyncio.Lock(), []
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
        self.canvas = (side['width'], side['height'])
        self.board = map_card.Board(shape)
        # The size of a map opened over the glass, for a finger on its markers: the board's full box until one is drawn
        # at the size the screen asked for (full).
        self.full_box = picture_question.box(self.screen, 'full') or self.canvas
        self.sender = send_layout.api_sender(self.client, services)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        states = dict(STATES)
        tiles, neighbours = [], iter(NEIGHBOURS)
        pages = [(name, cards) for name, cards in PAGES if all(size != 'wide' and size != 'square' or grid.columns >= 2 for _, _, size, _ in cards)]
        for page, (_, cards) in enumerate(pages):
            cells = range(page * grid.slots, (page + 1) * grid.slots)
            taken = set()
            for entity, name, size, options in cards:
                # The first place on the page the tile fits whole (a double-width tile starts in a column with room).
                slot = next(c for c in cells if c not in taken and fits(grid, c, size, taken, cells))
                tiles.append(dict(entity=entity, name=name, slot=slot, options={k: v for k, v in {'display': 'map', 'size': size, **options}.items()
                                                                            if not (k == 'display' and v == 'standard')}))
                taken |= set(grid.footprint(slot, size))
            for cell in [c for c in range(page * grid.slots, (page + 1) * grid.slots) if c not in taken]:
                neighbour = next(neighbours, None)
                if neighbour:
                    tiles.append(dict(entity=neighbour[0], name=neighbour[1], slot=cell))
                    states[neighbour[0]] = neighbour[2]
        record = send_layout.migrate_legacy(dict(title='Map', tiles=tiles), grid)
        self.compiled = send_layout.compile_tiles(record['layout'], grid)
        values = [send_layout.state_message(i, tile, states) for i, tile in enumerate(self.compiled)]
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        async with self.turn:
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        shots = 0
        for look in ('light', 'dark'):
            if look == 'dark':
                self.client.switch_command(dark.key, True)
                await asyncio.sleep(1.0)
            for page, (name, _) in enumerate(pages):
                await self.call('render_page', page=page)
                await self.page_done(page)
                if name != 'person':
                    await self.picture(f'{name} {look}')
                await self.render(f'{name}-{look}')
                shots += 1
                # A tap opens the map over the whole glass, as a camera does: the first card of the page.
                if name in ('square', 'singles', 'person'):
                    first = next(t for t in self.compiled if t.get('slot', 0) // grid.slots == page)
                    cells = side['width'] // grid.columns, (side['height'] - 60) // grid.rows
                    col, row = (first['slot'] % grid.slots) % grid.columns, (first['slot'] % grid.slots) // grid.columns
                    start = len(self.lines)
                    await self.tap(col * cells[0] + cells[0] // 2, 60 + row * cells[1] + cells[1] // 2)
                    # The full view's picture came down (picture_fetch's line for the view's slot, `camera`).
                    loaded = lambda line: 'camera: loaded' in line or 'camera: unchanged' in line
                    try:
                        await self.until(loaded, 15, f'{name} full', start)
                        await asyncio.sleep(2.5)
                        await self.render(f'{name}-full-{look}', timeout=8)
                        # A finger on Sam's marker: Sam in the middle, closer in, with Sam's card over the bottom.
                        hit = next((h for h in self.hits if h[0] == 'person.sam'), None)
                        if hit and name == 'square':
                            ox, oy = (side['width'] - self.full_box[0]) // 2, (side['height'] - self.full_box[1]) // 2
                            start = len(self.lines)
                            await self.tap(ox + hit[1], oy + hit[2])
                            await self.until(loaded, 15, f'{name} focus', start)
                            await asyncio.sleep(2.5)
                            await self.render(f'{name}-focus-{look}', timeout=8)
                            await self.tap(30, 30)
                            await asyncio.sleep(0.8)
                    except RuntimeError as error:
                        self.warnings.append(str(error))
                    await self.tap(30, 30)
                    await asyncio.sleep(0.8)
        self.client.switch_command(dark.key, False)
        return len(pages), shots


def fits(grid, slot, size, taken, cells):
    try:
        footprint = set(grid.footprint(slot, size))
    except ValueError:
        return False
    first = slot - slot % grid.slots
    return footprint <= set(cells) and not footprint & taken and \
        (size != 'wide' and size != 'square' or (slot - first) % grid.columns + 2 <= grid.columns)


def streets_from(folder):
    """{(z, x, y): decoded} of every tile in `folder` (z_x_y.mvt)."""
    found = {}
    for path in sorted(Path(folder).glob('*_*_*.mvt')) if folder else ():
        try:
            z, x, y = (int(n) for n in path.stem.split('_'))
            found[(z, x, y)] = vector_tiles.decode(path.read_bytes(), map_card.LAYERS)
        except ValueError:
            continue
    return found


def sheet(out, key, names):
    font = ImageFont.truetype(str(run.REPO / 'fonts/Roboto-500.ttf'), 22)
    shots = [[out / key / f'{name}-{look}.png' for name in names] for look in ('light', 'dark')]
    if not shots[0][0].exists():
        return
    w, h = Image.open(shots[0][0]).size
    image = Image.new('RGB', (len(names) * (w + 24) + 24, 2 * (h + 24) + 64), '#f5f6f8')
    ImageDraw.Draw(image).text((24, 18), f'{key} · {w} × {h}', font=font, fill='#17202c')
    for row, paths in enumerate(shots):
        for col, path in enumerate(paths):
            if path.exists():
                with Image.open(path) as shot:
                    image.paste(shot, (24 + col * (w + 24), 64 + row * (h + 24)))
    image.save(out / f'sheet-{key}.png')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variants', nargs='+')
    parser.add_argument('--out', type=Path, default=run.REPO / '.esphome' / 'map-tiles' / 'out')
    parser.add_argument('--tiles', type=Path, help='a folder of Home Assistant vector tiles, z_x_y.mvt')
    args = parser.parse_args()
    args.out = args.out.resolve()
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
    streets = streets_from(args.tiles)
    pictures = run.Pictures()
    for key in args.variants:
        item = host.variant(key)
        build = host.Build(item, tree=run.REPO, work=None, esphome=esphome)
        started = time.monotonic()
        ok, output = build.compile()
        if not ok:
            print(f'{key}: BUILD FAILED\n{output[-3000:]}', flush=True)
            continue
        study = Study(build, args.out / key, pictures, streets)
        try:
            summary = asyncio.run(study.run())
            sheet(args.out, key, [name for name, _ in PAGES if (args.out / key / f'{name}-light.png').exists()])
        except Exception as error:
            summary = f'stopped: {type(error).__name__}: {error}'
        print(f'{key}: {summary} ({time.monotonic() - started:.0f} s) {study.warnings}', flush=True)


if __name__ == '__main__':
    main()
