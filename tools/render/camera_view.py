"""Open a camera full screen on a board that keeps no picture (the CYD: packages/features/camera-view.yaml), with the
real firmware on the host (tools/render/host.py) and the add-on's own camera_feed, and check what reaches the panel.

    python3 tools/render/camera_view.py cyd cyd-portrait

The board writes the picture to its glass in bands as it downloads, past LVGL, so the renders' PNG of what LVGL draws
shows a black page there. This reads the panel itself (the host's `render_panel`) and checks, for each variant:

- a tap on the camera tile opens the view, the program asks with its glass (`direct`), and the picture the add-on
  makes for that glass is on the panel pixel for pixel (to the 16 bits of the glass), in the middle of a black page;
- a tile that changes under the view leaves the picture whole;
- the next picture replaces the first;
- a tap anywhere closes the view, and the panel shows the page again as LVGL draws it.

It writes page.png, camera.png, next.png and closed.png per variant and exits 1 when a check fails.
"""
import argparse
import asyncio
import io
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
import camera_tiles  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402

CAMERA = ('camera.front_door', 'Front door')
NEIGHBOUR = ('light.demo', 'Table lamp')
# A panel of 16 bits keeps five or six bits a colour: a pixel may differ by that much from the 24-bit picture.
TOLERANCE = 8
# The glass turned back from the panel's own pixels, by the angle LVGL lays this variant out with.
TURN = {0: None, 90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_270}


def worst(a, b):
    """The largest difference of one colour of one pixel between two pictures of the same size."""
    return max(high for _, high in ImageChops.difference(a, b).getextrema())


class View(run.Run):
    def answer(self, call):
        if call.service != 'esphome.screen_camera':
            return
        self.asked.append(dict(call.data))
        task = asyncio.get_running_loop().create_task(self.link(dict(call.data)))
        task.add_done_callback(lambda t: t.exception() and self.failures.append(f'answer failed: {t.exception()!r}'))

    async def link(self, data):
        glass = camera_feed.direct_request(data)
        if glass is None:
            self.failures.append(f'a request without its glass: {data}')
            return
        self.glass = glass
        self.url = self.pictures.url('view.bmp', self.picture(day=True))
        await self.send({'v': 1, 'op': 'camera', 't': 'full', 'e': data['entity'], 'view': int(data['view']), 'u': self.url})

    def picture(self, day):
        """The camera's picture of now, as the add-on makes it for this glass. The link stays the same and serves the
        newest one, as the add-on's does."""
        self.body = camera_feed.encode_direct(camera_tiles.scene(*self.camera, day=day), self.glass)
        self.pictures.files['/view.bmp'] = self.body
        return self.body

    def expected(self, body):
        """The glass with this picture on it: in the middle of the view's black page."""
        with Image.open(io.BytesIO(body)) as picture:
            picture = picture.convert('RGB')
        glass = Image.new('RGB', self.canvas)
        glass.paste(picture, ((self.canvas[0] - picture.width) // 2 // 2 * 2, (self.canvas[1] - picture.height) // 2 // 2 * 2))
        return glass

    async def panel(self, name):
        """What is on the panel, turned to the way the glass hangs; kept as <name>.png."""
        path = self.out / f'{name}.ppm'
        path.unlink(missing_ok=True)
        await self.call('render_panel', path=str(path))
        end = time.monotonic() + 10
        while not path.exists():
            if time.monotonic() > end:
                raise RuntimeError(f'no panel picture at {path}')
            await asyncio.sleep(0.05)
        with Image.open(path) as image:
            image = image.convert('RGB')
        path.unlink()
        turn = TURN[int(self.item.rotation or self.landscape)]
        image = image.transpose(turn) if turn else image
        image.save(self.out / f'{name}.png')
        return image

    def check(self, what, ok, detail=''):
        self.checks += 1
        if not ok:
            self.failures.append(f'{what}{": " + detail if detail else ""}')

    async def drive(self):
        self.asked, self.checks = [], 0
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
        shape = json.loads((run.REPO / 'screen_manager/app/boards.json').read_text())[self.item.board]
        side = shape['orientations']['portrait' if self.item.rotation else 'landscape']
        self.landscape = shape['orientations']['landscape']['rotation']
        self.canvas = (side['width'], side['height'])
        grid = send_layout.Grid(side['columns'], side['rows'])
        self.sender = send_layout.api_sender(self.client, services)
        states = {CAMERA[0]: {'state': 'idle', 'attributes': {'friendly_name': CAMERA[1]}},
                  NEIGHBOUR[0]: {'state': 'off', 'attributes': {'brightness': 0}}}
        tiles = [dict(entity=CAMERA[0], name=CAMERA[1], slot=0), dict(entity=NEIGHBOUR[0], name=NEIGHBOUR[1], slot=1)]
        record = send_layout.migrate_legacy(dict(title='Camera', tiles=tiles), grid)
        compiled = send_layout.compile_tiles(record['layout'], grid)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        values = [send_layout.state_message(i, tile, states) for i, tile in enumerate(compiled)]
        await self.sender.synchronize(self.inbox.object_id, record, region, values, [[{'k': 'clock'}]])
        await self.call('render_page', page=0)
        await self.page_done(0)
        page = await self.render('page')

        # A tap on the camera tile opens the view; the program asks with its glass.
        spots = await self.slots()
        start = len(self.lines)
        await self.tap(*spots[CAMERA[0]])
        await self.until(lambda line: 'open ' + CAMERA[0] in line, 5, 'the view opening', start)
        await self.until(lambda line: 'camera: loaded' in line, 15, 'the first picture', start)
        self.check('the request names the glass', self.asked and self.asked[0].get('direct') == f'{self.canvas[0]}x{self.canvas[1]}',
                   str(self.asked[:1]))
        await asyncio.sleep(0.3)
        shown = await self.panel('camera')
        first = self.expected(self.body)
        self.check('the picture is on the panel', worst(shown, first) <= TOLERANCE, f'off by {worst(shown, first)}')
        # LVGL knows nothing of it: its own picture of the view is the black page (and no key, no name, no spinner).
        self.check('nothing of LVGL lies over the picture', (await self.render('lvgl', keep=False)).getextrema() == ((0, 0),) * 3)

        # A tile that changes under the view is not drawn over the picture.
        states[NEIGHBOUR[0]] = {'state': 'on', 'attributes': {'brightness': 255}}
        index = next(i for i, tile in enumerate(compiled) if tile['entity'] == NEIGHBOUR[0])
        await self.send(send_layout.state_message(index, compiled[index], states))
        await asyncio.sleep(1.0)
        under = await self.panel('camera')
        self.check('a tile changing under the view leaves the picture whole', worst(under, first) <= TOLERANCE, f'off by {worst(under, first)}')

        # The next picture, another one, replaces the first at the view's pace.
        second = self.expected(self.picture(day=False))
        start = len(self.lines)
        await self.until(lambda line: 'camera: loaded' in line, 20, 'the next picture', start)
        await asyncio.sleep(0.3)
        later = await self.panel('next')
        self.check('the next picture replaces the first', worst(later, second) <= TOLERANCE and worst(first, second) > 60,
                   f'off by {worst(later, second)}')

        # A tap anywhere closes the view; the panel is the page again, with the lamp as it is now.
        start = len(self.lines)
        await self.tap(self.canvas[0] // 2, self.canvas[1] // 2)
        await self.until(lambda line: 'closed ' + CAMERA[0] in line, 5, 'the view closing', start)
        again = await self.render('page-after', keep=False)
        closed = await self.panel('closed')
        # LVGL's own picture of the page has 24 bits and the panel 16, each way of rounding a blended edge its own.
        self.check('closing draws the page again', worst(closed, again) <= 3 * TOLERANCE, f'off by {worst(closed, again)}')
        self.check('the page shows the lamp on', worst(again, page) > 60)
        if self.failures:
            raise RuntimeError('; '.join(self.failures))
        return 1, self.checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variants', nargs='+')
    parser.add_argument('--out', type=Path, default=run.REPO / '.esphome' / 'camera-view' / 'out')
    parser.add_argument('--camera', default='1280x720')
    args = parser.parse_args()
    args.out = args.out.resolve()
    # No window: the panel is read back from SDL's own surface.
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_RENDER_DRIVER', 'software')
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
    camera = tuple(int(n) for n in args.camera.split('x'))
    pictures = run.Pictures()
    failed = False
    for key in args.variants:
        item = host.variant(key)
        build = host.Build(item, tree=run.REPO, work=None, esphome=esphome)
        started = time.monotonic()
        ok, output = build.compile()
        if not ok:
            print(f'{key}: BUILD FAILED\n{output[-3000:]}', flush=True)
            failed = True
            continue
        view = View(build, args.out / key, pictures, camera)
        try:
            summary = asyncio.run(view.run())
        except Exception as error:
            summary = f'FAILED: {type(error).__name__}: {error}'
            failed = True
        print(f'{key}: {summary} ({time.monotonic() - started:.0f} s) {view.warnings}', flush=True)
    print(args.out, flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
