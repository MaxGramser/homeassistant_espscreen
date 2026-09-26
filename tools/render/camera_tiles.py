"""Render a live camera that fills a 1x2 and a 2x2 card (app 0.3.8, firmware 0.3.3): fill or contain, with its name or
without, with the real firmware on the host (tools/render/host.py) and the add-on's own camera_feed and tile_art.

    python3 tools/render/camera_tiles.py guition waveshare43

The program asks for its picture the way it asks ESP Screens (the esphome.screen_camera event with an atlas); this
script answers as the add-on would (camera_feed.picture_modes, tile_art.encode), with a drawn porch as the camera: by
day on the 1x2 tile, the hard case for white text, and by night on the 2x2.
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
import camera_feed  # noqa: E402
import core  # noqa: E402
import tile_art  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

CAMERA = 'camera.front_door'
OVERLAYS = {'name': 'name at the bottom', 'none': 'nothing on the picture'}
NEIGHBOURS = [
    ('light.demo', 'Table lamp', {'state': 'on', 'attributes': {'brightness': 180}}),
    ('sensor.demo_temperature', 'Living room', {'state': '21.5', 'attributes': {'unit_of_measurement': '°C'}}),
    ('switch.demo_desk', 'Desk', {'state': 'off', 'attributes': {}}),
    ('binary_sensor.demo_door', 'Front door', {'state': 'off', 'attributes': {'device_class': 'door'}}),
    ('sensor.demo_energy', 'Usage today', {'state': '7.42', 'attributes': {'unit_of_measurement': 'kWh'}}),
    ('light.demo_ceiling', 'Ceiling light', {'state': 'off', 'attributes': {}}),
    ('scene.demo_evening', 'Evening', {'state': '2026-09-15T07:00:00+00:00', 'attributes': {}}),
    ('light.demo_hall', 'Hall', {'state': 'on', 'attributes': {'brightness': 120}}),
    ('sensor.demo_humidity', 'Humidity', {'state': '54', 'attributes': {'unit_of_measurement': '%'}}),
    ('switch.demo_heater', 'Heater', {'state': 'on', 'attributes': {}}),
    ('light.demo_garden', 'Garden lights', {'state': 'off', 'attributes': {}}),
    ('sensor.demo_outside', 'Outside', {'state': '14.2', 'attributes': {'unit_of_measurement': '°C'}}),
]


def scene(width, height, day):
    """The porch of run.porch by night, or a bright one by day: white text on a light picture is the hard case."""
    if not day:
        return run.porch(width, height)
    import io
    image = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=(int(150 + 60 * t), int(200 + 30 * t), 250))
    draw.rectangle([0, int(height * 0.18), width, height], fill=(236, 228, 214))
    for row in range(int(height * 0.18), height, 24):
        draw.line([(0, row), (width, row)], fill=(214, 204, 188), width=2)
    door = [int(width * 0.40), int(height * 0.30), int(width * 0.60), int(height * 0.92)]
    draw.rectangle(door, fill=(58, 110, 150), outline=(255, 255, 255), width=8)
    draw.ellipse([int(width * 0.54), int(height * 0.58), int(width * 0.57), int(height * 0.63)], fill=(230, 190, 90))
    draw.rectangle([int(width * 0.08), int(height * 0.55), int(width * 0.26), int(height)], fill=(96, 150, 80))
    draw.rectangle([int(width * 0.74), int(height * 0.55), int(width * 0.92), int(height)], fill=(96, 150, 80))
    draw.rectangle([int(width * 0.36), int(height * 0.92), int(width * 0.64), height], fill=(170, 140, 100))
    draw.rectangle([0, 0, width - 1, height - 1], outline=(255, 64, 64), width=6)
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=92)
    return out.getvalue()


class Study(run.Run):

    def answer(self, call):
        if call.service != 'esphome.screen_camera' or 'tiles' not in call.data:
            return
        task = asyncio.get_running_loop().create_task(self.live(dict(call.data)))
        # An answer to an ask from before the last layout is dropped, as the app's own is (Sender.auxiliary).
        task.add_done_callback(lambda t: t.exception() and 'superseded' not in str(t.exception()) and self.warnings.append(f'answer failed: {t.exception()!r}'))

    async def live(self, data):
        # A held answer shows the card while it waits for its picture: the spinner (firmware 0.3.3).
        while self.hold:
            await asyncio.sleep(0.1)
        entities = data['tiles'].split(',')
        atlas = tile_art.parse(data.get('atlas', ''), self.canvas, len(entities))
        if atlas is None:
            self.warnings.append(f'no atlas in {data}')
            return
        raw = scene(*self.camera, day=entities[0] == 'camera.front_door')
        grounds = [int(c, 16) for c in data['bg'].split(',')]
        modes = camera_feed.picture_modes({'firmware': core.FIRMWARE_VERSION}, self.options.get, entities)
        # As the add-on answers this firmware: 8-bit colour (app 0.3.8).
        screen = {'firmware': core.FIRMWARE_VERSION}
        body = tile_art.encode([raw] * len(entities), grounds, atlas, modes, camera_feed.compact_pictures(screen))
        self.served += 1
        url = self.pictures.url(f'live-{self.served}.bmp', body)
        async with self.turn:
            await self.send({'v': 1, 'op': 'camera', 't': 'live', 'e': data['tiles'], 'u': url, 'view': int(data['view'])})

    async def picture(self, what, tries=4):
        """Ask for the page's picture again and wait until it is drawn. A new layout makes the screen ask by itself,
        and an answer to that ask can cross the reset, so a missing picture is asked for once more."""
        for attempt in range(tries):
            start = len(self.lines)
            await self.call('render_live_reset')
            try:
                await self.until(lambda line: 'asked for the live tiles' in line, 10, f'{what}: the ask', start)
                await self.until(lambda line: 'live tiles loaded' in line, 15, f'{what}: the picture', start)
                await asyncio.sleep(0.8)
                return
            except RuntimeError:
                if attempt == tries - 1:
                    raise
                await asyncio.sleep(1)

    async def drive(self):
        self.served, self.turn, self.hold = 0, asyncio.Lock(), False
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
        self.subscribe_logs()
        self.client.subscribe_service_calls(self.answer)
        if 'render_skip_calibration' in self.services:
            await self.call('render_skip_calibration')
        await self.call('render_time', epoch=int(run.MOMENT.timestamp()))
        side = json.loads((run.REPO / 'screen_manager/app/boards.json').read_text())[self.item.board]['orientations']
        side = side['portrait' if self.item.rotation else 'landscape']
        grid = send_layout.Grid(side['columns'], side['rows'])
        self.canvas = (side['width'], side['height'])
        self.sender = send_layout.api_sender(self.client, services)
        cameras = [('camera.front_door', 'Front door'), ('camera.garden', 'Garden')]
        sizes = ['tall', 'square'] if grid.columns >= 2 else ['tall']
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        shots = 0
        for fit in ('fill', 'contain'):
            for overlay in OVERLAYS:
                states = {entity: {'state': 'idle', 'attributes': {'friendly_name': name}} for entity, name in cameras}
                tiles, neighbours, self.options = [], iter(NEIGHBOURS), {}
                for page, size in enumerate(sizes):
                    slot = page * grid.slots
                    entity, name = cameras[page]
                    options = {'display': 'live', 'refresh': 15, 'size': size, 'fit': fit, 'overlay': overlay}
                    tiles.append(dict(entity=entity, name=name, slot=slot, options=options))
                    taken = set(grid.footprint(slot, size))
                    free = [cell for cell in range(slot, slot + grid.slots) if cell not in taken]
                    for cell, (neighbour, label, state) in zip(free, neighbours):
                        tiles.append(dict(entity=neighbour, name=label, slot=cell))
                        states[neighbour] = state
                record = send_layout.migrate_legacy(dict(title='Cameras', tiles=tiles), grid)
                compiled = send_layout.compile_tiles(record['layout'], grid)
                # What the add-on answers from: the stored options of each camera tile (server.answer_live).
                self.options = {tile['entity']: tile.get('options', {}) for tile in compiled}
                values = [send_layout.state_message(i, tile, states) for i, tile in enumerate(compiled)]
                bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
                # One message at a time: an answer that crosses a new layout makes the screen refuse the layout.
                async with self.turn:
                    await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
                for page, size in enumerate(sizes):
                    await self.call('render_page', page=page)
                    await self.page_done(page)
                    if fit == 'fill':
                        self.hold = True
                        start = len(self.lines)
                        await self.call('render_live_reset')
                        await self.until(lambda line: 'asked for the live tiles' in line, 10, f'{size} waiting: the ask', start)
                        await asyncio.sleep(0.5)
                        await self.render(f'{size}-{overlay}-waiting', timeout=3)
                        self.hold = False
                    await self.picture(f'{size} {fit} {overlay}')
                    await self.render(f'{size}-{overlay}-{fit}')
                    shots += 1
        return len(sizes), shots


def sheets(out, keys):
    font = ImageFont.truetype(str(run.REPO / 'fonts/Roboto-500.ttf'), 22)
    small = ImageFont.truetype(str(run.REPO / 'fonts/Roboto-400.ttf'), 17)
    for key in keys:
        for size in ('tall', 'square'):
            paths = [[out / key / f'{size}-{overlay}-{fit}.png' for fit in ('fill', 'contain')] for overlay in OVERLAYS]
            if not paths[0][0].exists():
                continue
            w, h = Image.open(paths[0][0]).size
            scale = 2 if w <= 480 else 1
            cw, ch = w * scale, h * scale
            sheet = Image.new('RGB', (2 * cw + 72, len(OVERLAYS) * (ch + 56) + 72), '#f5f6f8')
            draw = ImageDraw.Draw(sheet)
            draw.text((24, 16), f'{key} · {w} × {h} · {"1×2" if size == "tall" else "2×2"}', font=font, fill='#17202c')
            for row, overlay in enumerate(OVERLAYS):
                for col, fit in enumerate(('fill', 'contain')):
                    x, y = 24 + col * (cw + 24), 60 + row * (ch + 56)
                    draw.text((x, y), f'{OVERLAYS[overlay]} · {fit}', font=small, fill='#56616d')
                    with Image.open(paths[row][col]) as shot:
                        sheet.paste(shot.resize((cw, ch), Image.Resampling.NEAREST), (x, y + 28))
            sheet.save(out / f'sheet-{key}-{size}.png')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variants', nargs='+')
    parser.add_argument('--out', type=Path, default=run.REPO / '.esphome' / 'camera-tiles' / 'out')
    parser.add_argument('--camera', default='1280x720')
    args = parser.parse_args()
    args.out = args.out.resolve()
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
    camera = tuple(int(n) for n in args.camera.split('x'))
    pictures = run.Pictures()
    done = []
    for key in args.variants:
        item = host.variant(key)
        build = host.Build(item, tree=run.REPO, work=None, esphome=esphome)
        started = time.monotonic()
        ok, output = build.compile()
        if not ok:
            print(f'{key}: BUILD FAILED\n{output[-3000:]}', flush=True)
            continue
        study = Study(build, args.out / key, pictures, camera)
        try:
            summary = asyncio.run(study.run())
            done.append(key)
        except Exception as error:
            summary = f'stopped: {type(error).__name__}: {error}'
        print(f'{key}: {summary} ({time.monotonic() - started:.0f} s) {study.warnings}', flush=True)
    sheets(args.out, done)
    print(args.out, flush=True)


if __name__ == '__main__':
    main()
