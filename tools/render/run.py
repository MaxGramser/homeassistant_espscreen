"""Build every board as a host program, run its self test, and render what it draws (tools/render/host.py).

For each variant (a board of the catalog, lying down and, where its glass is not square, standing up) this compiles the
real firmware for the host, starts it, and drives it over its API with no Home Assistant involved:

- the demo layout of diagnostics/send_layout.py (every kind of card, fixed states at a fixed moment);
- the firmware's own self test (ui_self_test): every page and overlay rendered, each page's cards and bar checked,
  and on every board the geometry check that nothing falls outside its area. A FAIL fails the run;
- PNGs of every page, of the alerts (plain, long, with a button, with two buttons and button colors), of an alert with a camera picture
  (one button and two) on the boards
  that draw pictures (made by the add-on's own camera_feed for the frame this screen's card makes for it), and of
  page 1 in Dark mode.

    python3 tools/render/run.py                       every variant, into .esphome/render/out/
    python3 tools/render/run.py guition cyd-portrait  those variants
    python3 tools/render/run.py --tree ../main --out .esphome/render/base
                                                      another tree (a checkout of an older commit), to compare with
                                                      tools/compare_renders.py

Run it with the Python of ESPHome (it needs aioesphomeapi and Pillow); ESPHOME names the esphome command, SDL2 must be
installed. It exits 1 when a variant does not build, does not start, or fails its self test.
"""
import argparse
import asyncio
import http.server
import io
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aioesphomeapi import APIClient, LogLevel
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'diagnostics'))
sys.path.insert(0, str(REPO / 'screen_manager' / 'app'))
import host  # noqa: E402
import send_layout  # noqa: E402

# Every render shows the same moment: Tuesday 15 September 2026, 10:08 in Amsterdam.
MOMENT = datetime(2026, 9, 15, 10, 8, tzinfo=ZoneInfo('Europe/Amsterdam'))
LONG_TITLE = 'The washing machine in the basement has finished its extra long cotton cycle'
LONG_SUBTITLE = ('The drum has been standing full of wet laundry for almost two hours now, so it will start to smell '
                 'soon. Hang it up in the attic or move it to the dryer, then tap the button to clear this reminder.')
ALERTS = (
    ('alert-plain', dict(title='Someone is at the door', subtitle='Front door camera\nTap Coming to let them know', icon='doorbell')),
    ('alert-long', dict(title=LONG_TITLE, subtitle=LONG_SUBTITLE, icon='washing-machine')),
    ('alert-button', dict(title='Doorbell', subtitle='', icon='doorbell', button_text='Coming')),
    # Two buttons (show_alert_choice, firmware 0.3.3+): in the keys' own paints, in key colours, and on a coloured card.
    ('alert-choice', dict(title='Someone is at the door', subtitle='Front door camera', icon='doorbell',
                          button_text='Open', button2_text='Not now')),
    ('alert-choice-colors', dict(title='Open the garage?', subtitle='The car is on the driveway', icon='garage',
                                 button_text='Accept', button_color='green', button2_text='Decline', button2_color='red')),
    ('alert-choice-card', dict(title='Washing machine done', subtitle='Hang the laundry up or move it to the dryer',
                               icon='washing-machine', color='blue', button_text='Heard', button2_text='Remind me',
                               button2_color='gray')),
)
CHOICE_FIELDS = ('button_color', 'button2_text', 'button2_color')
# The starting screen's steps (firmware 0.38.0, render_boot): a network, its address, Home Assistant, Tessera, a Wi-Fi
# problem with and without a hotspot, and an update. `waited` is how long the step has taken, in ms.
BOOT_DEFAULTS = dict(connected=False, joined=False, ssid='', rssi=0, address='', scanned=False, seen=False, seen_rssi=0,
                     reason=0, failures=0, ha=0, waited=0, hotspot='', password='', ota=-1, empty=False)
NETWORK = dict(connected=True, ssid='Home network', rssi=-61, address='192.168.1.40')
BOOT_STATES = (
    ('starting-wifi', dict(ssid='Home network', waited=1000)),
    ('starting-wifi-password', dict(ssid='Home network', scanned=True, seen=True, seen_rssi=-57, reason=15, failures=3, waited=24000)),
    ('starting-wifi-missing', dict(ssid='Home network', scanned=True, failures=2, waited=41000)),
    ('starting-address', dict(ssid='Home network', joined=True, waited=4000)),
    ('starting-home-assistant', dict(NETWORK, waited=6000)),
    ('starting-home-assistant-hint', dict(NETWORK, waited=95000)),
    ('starting-tessera-hint', dict(NETWORK, ha=1, waited=48000)),
    # Tessera has no tiles for this screen yet (firmware 0.45.0): where to choose them, over a mosaic of its page.
    ('starting-first-tiles', dict(NETWORK, ha=1, empty=True)),
    ('starting-wifi-problem', dict(ssid='Home network', scanned=True, seen=True, seen_rssi=-86, reason=15, failures=6,
                                   hotspot='Kitchen Setup', password='a1b2c3d4')),
    ('starting-wifi-problem-usb', dict(ssid='Home network', reason=202, failures=6, hotspot='-')),
    ('updating', dict(NETWORK, ha=1, ota=45)),
)
PROBE = re.compile(r'probe page=(-?\d+) applied=(-?\d+) shown=(\d+) tiles=(\d+) alert=(\d) pages=(\d+)')
HEADER = re.compile(r'state page=(-?\d+) name=\[(.*?)\] shown=\[(.*?)\] name_box=(-?\d+),(-?\d+),(-?\d+),(-?\d+)')
NAVIGATION = re.compile(r'navigation page=(-?\d+) footer=(\d) back=(\d) grid_height=(\d+) tile=(-?\d+),(-?\d+) prev=(-?\d+),(-?\d+) header=(-?\d+),(-?\d+)')
ALERT = re.compile(r'alert on=(\d) ' + ' '.join(f'{part}=(-?\\d+),(-?\\d+),(-?\\d+),(-?\\d+)'
                                              for part in ('card', 'frame', 'icon', 'title', 'subtitle', 'button', 'button2')))
# A page's own title (app 0.2.123): a long one among them, the kind that stood in dots after a page change (GitHub #27).
PAGE_TITLES = ['Demo cards', 'Living room downstairs', 'Kitchen']
MEDIA = re.compile(r'media open=(\d) back=(\S*) pill=(\S*) libkey=(\S*) knob=(\S*) keys=(\S*) faults=(.*?) \| (.*)$')
SAVER = re.compile(r'saver dimmed=(\d) keys=(\S*) words_right=(-?\d+)$')
ALARM = re.compile(r'alarm open=(\d) pad=(\d) back=(\S*) title=\[(.*?)\] status=\[(.*?)\] line=\[(.*?)\] modes=(\S*) keys=(\S*) faults=(.*?) locked=(\d+)$')


def overlap(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def alert_faults(state):
    """What is wrong with an alert card as LVGL placed it: a part outside the card, or two parts over each other."""
    parts = {name: box for name, box in state.items() if name != 'card' and box[2] >= box[0]}
    card, faults = state['card'], []
    for name, box in parts.items():
        if not (card[0] <= box[0] and box[2] <= card[2] and card[1] <= box[1] and box[3] <= card[3]):
            faults.append(f'{name} {box} outside the card {card}')
    names = list(parts)
    for i, one in enumerate(names):
        for other in names[i + 1:]:
            if overlap(parts[one], parts[other]):
                faults.append(f'{one} {parts[one]} over {other} {parts[other]}')
    return faults


def porch(width, height):
    """A drawn porch at night for the camera: sky, wall, a lit door, a lamp and a doormat inside a red frame, so a crop,
    a squeeze or an offset of the picture shows in a render. Deterministic, no photo."""
    image = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=(int(24 + 40 * t), int(34 + 50 * t), int(60 + 40 * t)))
    draw.rectangle([0, int(height * 0.18), width, height], fill=(150, 120, 100))
    for row in range(int(height * 0.18), height, 24):
        draw.line([(0, row), (width, row)], fill=(128, 100, 84), width=2)
    door = [int(width * 0.40), int(height * 0.30), int(width * 0.60), int(height * 0.92)]
    draw.rectangle(door, fill=(40, 70, 60), outline=(230, 220, 190), width=8)
    draw.ellipse([int(width * 0.66), int(height * 0.34), int(width * 0.70), int(height * 0.42)], fill=(255, 220, 120))
    draw.rectangle([int(width * 0.36), int(height * 0.92), int(width * 0.64), height], fill=(90, 60, 40))
    draw.rectangle([0, 0, width - 1, height - 1], outline=(255, 64, 64), width=6)
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=92)
    return out.getvalue()


class Pictures:
    """A little web server for the camera pictures the renders show, the way ESP Screens serves them (camera port)."""

    def __init__(self):
        self.files = {}
        files = self.files

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = files.get(self.path)
                self.send_response(200 if body else 404)
                self.send_header('Content-Type', 'image/bmp')
                self.send_header('Content-Length', str(len(body or b'')))
                self.end_headers()
                self.wfile.write(body or b'')

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self, name, body):
        self.files[f'/{name}'] = body
        return f'http://127.0.0.1:{self.server.server_address[1]}/{name}'


def alert_picture(item, camera):
    """(BMP bytes, box) of the camera picture an alert on this variant gets: sized by the add-on's own rule for the frame
    this screen's card makes for it (camera_feed.alert_box), encoded as the add-on encodes it."""
    import camera_feed
    import core
    raw = porch(*camera)
    screen = {'board': item.board, 'orientation': 'portrait' if item.rotation else 'landscape',
              'firmware_known': core.FIRMWARE_VERSION}
    box = camera_feed.alert_box(screen, camera_feed.picture_size(raw))
    return camera_feed.encode(raw, box, exact=box != camera_feed.box(screen, 'thumb')), box


def free(port):
    with socket.socket() as probe:
        return probe.connect_ex(('127.0.0.1', port)) != 0


class Run:
    """One variant's program, driven over its API."""

    def __init__(self, build, out, pictures, camera, only=None):
        self.build, self.item, self.out, self.pictures, self.camera = build, build.variant, out, pictures, camera
        self.only = only
        self.lines, self.warnings, self.failures = [], [], []

    async def call(self, name, **args):
        await self.client.execute_service(self.services[name], args)

    def subscribe_logs(self):
        self.client.subscribe_logs(lambda m: self.lines.append(re.sub(r'\x1b\[[0-9;]*m', '', m.message.decode(errors='replace')
                                                                      if isinstance(m.message, bytes) else m.message)),
                                   log_level=LogLevel.LOG_LEVEL_DEBUG, dump_config=False)

    async def offline_swipe(self, forward, expected):
        """Schedule SDL input, then actually disconnect the only API client."""
        await self.call('render_offline_swipe', forward=forward)
        await asyncio.sleep(0.1)
        await self.client.disconnect()
        await asyncio.sleep(2)
        await self.client.connect(login=True)
        self.subscribe_logs()
        start = len(self.lines)
        await self.call('render_offline_result')
        line = await self.until(lambda line: 'offline verified=' in line, 10, 'offline input diagnostic', start)
        assert 'offline verified=1' in line, 'An API client stayed connected during the gesture'
        actual = await self.state()
        assert actual['page'] == expected, f'Offline swipe reached the wrong page: {actual}'

    async def until(self, test, timeout, what, start=None):
        start, end = len(self.lines) if start is None else start, time.monotonic() + timeout
        while time.monotonic() < end:
            for line in self.lines[start:]:
                if test(line):
                    return line
            await asyncio.sleep(0.05)
        raise RuntimeError(f'{what}: nothing after {timeout} s')

    async def tile_pictures(self, what, start, timeout=15):
        """Every tile picture the screen asked for since `start` has had its try (tile_picture.h): each tile asks alone,
        and the page is drawn once the last answer is on its card."""
        asked = lambda: sum('asked for the picture of tile' in line for line in self.lines[start:])
        ended = lambda: sum(re.search(r'tile \d+: (picture loaded|no picture|the picture failed)', line) is not None
                            for line in self.lines[start:])
        await self.until(lambda line: 'asked for the picture of tile' in line, 10, f'{what}: the ask', start)
        end = time.monotonic() + timeout
        while ended() < asked():
            if time.monotonic() > end:
                raise RuntimeError(f'{what}: {ended()} of {asked()} pictures after {timeout} s')
            await asyncio.sleep(0.05)

    async def probe(self):
        start = len(self.lines)
        await self.call('render_probe')
        line = await self.until(lambda l: PROBE.search(l), 10, 'render_probe', start)
        return tuple(int(v) for v in PROBE.search(line).groups())

    async def page_done(self, page, timeout=20):
        """The page is placed and its cards drawn."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            p = await self.probe()
            if p[0] == page and p[1] == page and p[2] > 0:
                return p
            await asyncio.sleep(0.2)
        raise RuntimeError(f'page {page + 1} never finished: {p}')

    async def snapshot(self, path):
        path.unlink(missing_ok=True)
        await self.call('render_png', path=str(path))
        end = time.monotonic() + 15
        while time.monotonic() < end:
            if path.exists():  # render_png writes <path>.part and renames it when it is complete
                with Image.open(path) as image:
                    return image.convert('RGB')
            await asyncio.sleep(0.05)
        raise RuntimeError(f'no snapshot at {path}')

    async def render(self, name, keep=True, timeout=25):
        """Snapshots until two in a row match (at least 0.4 s apart); the last is kept as <name>.png."""
        start, previous = time.monotonic(), None
        while True:
            image = await self.snapshot(self.out / f'{name}.ppm')
            if previous is not None and image.tobytes() == previous.tobytes():
                break
            if time.monotonic() - start > timeout:
                self.warnings.append(f'{name}: never two equal snapshots in {timeout} s, kept the last')
                break
            previous = image
            await asyncio.sleep(0.4)
        (self.out / f'{name}.ppm').unlink(missing_ok=True)
        if keep:
            image.save(self.out / f'{name}.png')
        return image

    async def send(self, message):
        if not await self.sender.auxiliary(message, session=self.sender.session, revision=self.sender.confirmed):
            raise RuntimeError('The render configuration was superseded')

    async def alert(self, name, reference, **given):
        """One alert over page 1, rendered and dismissed; page 1 must then look as it did."""
        args = dict(title='', subtitle='', icon='', color='', button_text='', timeout=0, flash=False)
        choice = any(field in given for field in CHOICE_FIELDS)
        if choice:
            args.update({field: '' for field in CHOICE_FIELDS})
        args.update(given)
        start = len(self.lines)
        await self.call('show_alert_choice' if choice else 'show_alert', **args)
        await self.until(lambda l: '[alert' in l and 'show "' in l, 10, f'{name}: the alert never showed', start)
        state = await self.state()
        self.failures += [f'{name}, as it opens: {fault}' for fault in alert_faults(state['boxes'])]
        if name.startswith('alert-camera'):
            if state['boxes']['frame'][2] < state['boxes']['frame'][0]:
                self.failures.append(f'{name}: no frame for the picture while it loads')
            await self.render(f'{name}-waiting')
            await self.camera_link(start)
            state = await self.state()
            self.failures += [f'{name}, with its picture: {fault}' for fault in alert_faults(state['boxes'])]
        await self.render(name)
        start = len(self.lines)
        await self.call('dismiss_alert')
        await self.until(lambda l: 'dismissed: remote' in l, 10, f'{name}: the alert was never dismissed', start)
        await self.page_done(0)
        after = await self.render(f'_after-{name}', keep=False)
        if after.tobytes() != reference.tobytes():
            self.failures.append(f'{name}: page 1 looks different after the alert was dismissed')

    async def camera_link(self, start):
        body, box = alert_picture(self.item, self.camera)
        url = self.pictures.url(f'{self.item.key}-alert.bmp', body)
        await self.send({'v': 1, 'op': 'camera', 't': 'alert', 'e': 'camera.front_door', 'u': url})
        line = await self.until(lambda l: 'alert picture shown' in l or 'alert picture failed' in l, 20,
                                'alert-camera: the picture never loaded', start)
        if 'failed' in line:
            raise RuntimeError(f'alert-camera: {line}')
        self.warnings.append(f'alert-camera: a {self.camera[0]} x {self.camera[1]} camera, sent at {box[0]} x {box[1]}')

    async def state(self):
        """The page title as its label shows it, and every part of the alert card, read back now."""
        start = len(self.lines)
        await self.call('render_state')
        line = await self.until(lambda l: ALERT.search(l), 10, 'render_state', start)
        header = next(HEADER.search(l) for l in self.lines[start:] if HEADER.search(l))
        values = [int(v) for v in ALERT.search(line).groups()]
        boxes = {name: tuple(values[1 + 4 * i:5 + 4 * i]) for i, name in enumerate(('card', 'frame', 'icon', 'title', 'subtitle', 'button', 'button2'))}
        return {'page': int(header[1]), 'name': header[2], 'shown': header[3], 'alert': values[0], 'boxes': boxes}

    async def swipe(self, forward):
        """A finger across the tiles, the way a page is changed on the glass; returns the title label as it was read back
        every 50 ms from the release until it had been the same for a second."""
        width, height = self.canvas
        y = int(height * 0.6)
        # From the edge of the glass, as a page is changed on the glass: a wipe over the tiles is never a page flip on the
        # capacitive boards (features/capacitive-touch.yaml, the edge swipe). The touch panel is read every few tens of
        # milliseconds, so the finger rests on the edge long enough to be seen there, then moves the way a finger does,
        # a little further at every read (LVGL's gesture, the CYD's page swipe, starts counting again when it stops).
        start, stop = (0.99, 0.3) if forward else (0.01, 0.7)
        # Update faster than the touchscreen/LVGL read timers. Leaving the
        # virtual finger still for 20 ms between jumps creates zero-velocity
        # reads and can reset LVGL's gesture accumulator on the small CYD.
        # A physical moving finger does not stop between sensor samples.
        points = [int(width * (start + (stop - start) * i / 28)) for i in range(29)]
        await self.call('render_finger', x=points[0], y=y, down=True)
        await asyncio.sleep(0.15)
        for x in points[1:]:
            await self.call('render_finger', x=x, y=y, down=True)
            await asyncio.sleep(0.005)
        await self.call('render_finger', x=points[-1], y=y, down=False)
        seen, steady, end = [], 0, time.monotonic() + 6
        while time.monotonic() < end:
            state = await self.state()
            seen.append(state)
            steady = steady + 1 if len(seen) > 1 and (state['page'], state['shown']) == (seen[-2]['page'], seen[-2]['shown']) else 0
            if steady >= 20:
                break
            await asyncio.sleep(0.05)
        return seen

    async def moments(self, pages):
        """A page change by a finger, forward and back to page 1, with the title read back in the moment after it."""
        if pages < 2:
            return 0
        # "Swipe between pages" is off until someone turns it on; its switch, as Home Assistant turns it on.
        self.client.switch_command(self.swipe_switch.key, True)
        await asyncio.sleep(0.3)
        await self.call('render_page', page=0)
        await self.page_done(0)
        count = 0
        for forward, target in ((True, 1), (False, 0)):
            seen = await self.swipe(forward)
            count += len(seen)
            if seen[-1]['page'] != target:
                self.failures.append(f'swipe {"forward" if forward else "back"}: page {seen[-1]["page"] + 1}, not {target + 1}')
                continue
            final = seen[-1]['shown']
            if seen[-1]['name'] != PAGE_TITLES[target]:
                self.failures.append(f'page {target + 1} is named {seen[-1]["name"]!r}, not {PAGE_TITLES[target]!r}')
            for state in seen:
                if state['page'] == target and '...' in state['shown'] and '...' not in final:
                    self.failures.append(f'page {target + 1}: its title stood as {state["shown"]!r} for a moment, then {final!r}')
                    break
            self.warnings.append(f'swipe to page {target + 1}: title {final!r}, {len(seen)} read-backs')
        return count

    async def self_test(self):
        start = len(self.lines)
        await self.call('ui_self_test')
        await self.until(lambda l: 'UI_TEST COMPLETE' in l, 120, 'the self test never completed', start)
        lines = self.lines[start:]
        checks = [l for l in lines if 'page_check=' in l]
        failed = [l for l in lines if 'page_check=FAIL' in l or 'GEOMETRY FAIL' in l or 'Light sliders: FAIL' in l]
        if not checks:
            self.failures.append('self test: no page_check line')
        self.failures += [f'self test: {l.strip()}' for l in failed]
        return len(checks)

    async def navigation_state(self):
        start = len(self.lines)
        await self.call('render_navigation')
        line = await self.until(lambda line: NAVIGATION.search(line), 10, 'navigation probe', start)
        ink = next(re.search(r'leading heights home=(\d+) back=(\d+)', line) for line in self.lines[start:] if 'leading heights home=' in line)
        assert int(ink[1]) > 0 and abs(int(ink[1]) - int(ink[2])) <= 1, 'Back must match Home ink height within raster rounding'
        values = [int(value) for value in NAVIGATION.search(line).groups()]
        return dict(page=values[0], footer=bool(values[1]), back=bool(values[2]), height=values[3],
                    tile=values[4:6], previous=values[6:8], header=values[8:10])

    async def tap_navigation(self, control, target, titles):
        before = await self.navigation_state()
        x, y = before[control]
        if x < 0 or y < 0:
            raise RuntimeError(f'{control} is hidden on page {before["page"] + 1}')
        await self.call('render_finger', x=x, y=y, down=True)
        await asyncio.sleep(0.2)
        await self.call('render_finger', x=x, y=y, down=False)
        end = time.monotonic() + 8
        while time.monotonic() < end:
            state = await self.state()
            if state['page'] == target:
                if state['name'] != titles[target] or '...' in state['shown']:
                    raise RuntimeError(f'Tap reached page {target + 1} with a stale/truncated title: {state}')
                break
            await asyncio.sleep(0.05)
        else:
            raise RuntimeError(f'{control} tap did not reach page {target + 1}: {state}')
        after = await self.navigation_state()
        if after['height'] != before['height']:
            raise RuntimeError(f'Tile height changed across a page tap: {before} -> {after}')
        await asyncio.sleep(0.2)  # separate fingers, including the repeat-action guard
        return after

    async def appearance_edits(self, grid):
        from core import state_message
        from layout_migrations import migrate_legacy
        from page_layout import compile_tiles
        from page_delivery import Refused
        record = migrate_legacy({'title': 'Before edit', 'tiles': [
            {'entity': 'light.test', 'name': 'Before name', 'slot': 0}]}, grid)
        states = {'light.test': {'state': 'on', 'attributes': {'brightness': 140, 'supported_color_modes': ['brightness']}}}
        def values():
            return [state_message(i, tile, states) for i, tile in enumerate(compile_tiles(record['layout'], grid))]
        region = {'keepalive': 120, 'clock_24h': True, 'numbers': 'point', 'group_min': 1, 'percent_space': False}
        await self.sender.synchronize(self.inbox.object_id, record, region, values(), [[]])
        await self.render('_appearance-start', keep=False)
        async def probe(control=0):
            start = len(self.lines)
            await self.call('render_appearance_probe', control=control)
            line = await self.until(lambda line: 'appearance tiles=' in line, 5, 'appearance probe', start)
            return re.search(r'appearance tiles=(\S+) pages=(\S+) detail=(\S+) active=(-?\d+) visible=(\d) title=\[(.*?)\] name=\[(.*?)\] blue=(\d)', line).groups()
        before = await probe(1)
        assert before[4] == '1', before
        reference = await self.render('_appearance-open', keep=False)
        revision = self.sender.confirmed
        try:
            await self.sender._packet({'op': 'appearance', 'base': revision, 'title': 'Must not appear', 'pages': [],
                                       'tiles': [{'i': 0, 'name': 'Invalid batch', 'background': 'red'},
                                                 {'i': 64, 'name': 'Invalid', 'background': 'blue'}]}, 'fffffffffffffffe')
        except Refused:
            pass
        else: raise AssertionError('Out-of-range appearance edit was accepted')
        assert (await self.render('_appearance-refused', keep=False)).tobytes() == reference.tobytes()
        assert await probe() == before, 'Refused appearance edit mutated the model'
        record['layout']['title'] = 'After edit'
        record['layout']['pages'][0]['tiles'][0]['appearance'].update(label='After name', background='blue')
        old_session = self.sender.session
        await self.sender.synchronize(self.inbox.object_id, record, region, values(), [[]])
        after = await probe()
        assert self.sender.session == old_session, 'A cosmetic save renegotiated a full layout'
        assert after[:5] == before[:5], (before, after)
        assert after[5:] == ('After edit', 'After name', '1'), after
        assert await self.sender.ping()
        await self.render('appearance-card-kept-open')
        await probe(-1)

    async def detail_navigation(self, grid, entities):
        """Real touchscreen taps, nested Back, hidden footer and excluded swipes.

        This replaces the demo only after its render checks. There are no HA
        actions: every card navigates to a page. No test hooks ship on a board.
        """
        from core import state_message
        from layout_migrations import migrate_legacy
        from page_layout import compile_tiles
        # Larger grids can have only three pages within the existing 64-cell
        # limit. Keep a nested detail route on those boards too.
        extra_overview = grid.pages >= 4
        titles = ['Lighting', *(['Overview'] if extra_overview else []), 'Details', 'Nested']
        home_page, detail_page, nested_page = int(extra_overview), len(titles) - 2, len(titles) - 1
        targets = [detail_page + 1] * detail_page + [nested_page + 1, 1]
        record = migrate_legacy({'title': 'Navigation', 'pages': len(titles), 'page_titles': titles, 'tiles': [
            {'entity': f'screen.page_{target}', 'name': titles[target - 1], 'slot': index * grid.slots}
            for index, target in enumerate(targets)]}, grid)
        document = record['layout']
        document['homePageId'] = document['pages'][home_page]['id']
        for page in document['pages'][detail_page:]: page['navigation']['excludeFromPagination'] = True
        values = [state_message(i, tile, {}) for i, tile in enumerate(compile_tiles(document, grid))]
        bars = [[{'k': 'clock'}] for _ in document['pages']]
        region = {'keepalive': 120, 'clock_24h': True, 'numbers': 'point', 'group_min': 1, 'percent_space': False}
        await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        # The real ArduinoJson receiver must refuse every malformed destination
        # atomically, and keep the current layout after an oversize replacement.
        from page_delivery import Refused
        reference = await self.render('_before-refusal', keep=False)
        for message, revision in [
            ({'op': 'bar_value', 'item': {'k': 'text', 't': 'Must not appear'}, 'targets': [0, 48]}, self.sender.confirmed),
            ({'op': 'bar_value', 'item': {'k': 'text', 't': 'Must not appear'}, 'targets': [0, 0]}, self.sender.confirmed),
            ({'op': 'begin', 'inbox': self.inbox.object_id, 'title': 'Too large', 'pages': 1,
              'tiles': 65, 'home': 0, **region}, 'ffffffffffffffff'),
        ]:
            try:
                await self.sender._packet(message, revision)
            except Refused:
                pass
            else:
                raise AssertionError('Malformed packet was not refused')
            restored = await self.render('_after-refusal', keep=False)
            assert restored.tobytes() == reference.tobytes(), 'Refusal changed the active layout or a bar'
        assert await self.sender.ping(), 'The original configuration must remain active after refusal'
        buttons = next(e for e in entities if getattr(e, 'name', '') == 'Page buttons')
        home = next(e for e in entities if getattr(e, 'name', '') == 'Show home button')
        self.client.switch_command(self.swipe_switch.key, True)
        for footer in (True, False):
            self.client.switch_command(buttons.key, footer)
            self.client.switch_command(home.key, footer)  # Back also works with ordinary Home disabled.
            await self.call('show_page', page=1)
            await self.page_done(0)
            await asyncio.sleep(0.3)
            start = await self.navigation_state()
            assert start['footer'] == footer, start
            back_control = 'previous' if footer else 'header'
            detail = await self.tap_navigation('tile', detail_page, titles)
            assert detail['footer'] == footer and detail['back'] != footer, detail
            await self.render('detail-footer' if footer else 'detail-header')
            await self.tap_navigation('tile', nested_page, titles)
            await self.tap_navigation(back_control, detail_page, titles)
            await self.tap_navigation(back_control, 0, titles)  # source is not Home
            await self.call('show_page', page=nested_page + 1)  # external entry has no prior route
            await self.page_done(nested_page)
            await self.tap_navigation(back_control, home_page, titles)
            await self.call('show_page', page=1)
            await self.page_done(0)
            assert (await self.swipe(True))[-1]['page'] == home_page, 'swipe must stay within included pages'
            assert (await self.swipe(True))[-1]['page'] == home_page, 'swipe must stop before excluded pages'
            await self.call('show_page', page=detail_page + 1)
            await self.page_done(detail_page)
            assert (await self.swipe(False))[-1]['page'] == detail_page, 'detail pages have no sequential exit'
            self.warnings.append(f'Detail Back: nested/source/Home fallback, stable height and swipes; footer={footer}')
        self.client.switch_command(buttons.key, True)
        self.client.switch_command(home.key, True)
        await asyncio.sleep(0.3)
        await self.call('show_page', page=1)
        await self.page_done(0)
        reference = await self.render('_before-protocol-error', keep=False)
        for version, problem in ((1, 1), (99, 2)):
            await self.sender.send({'v': version, 'op': 'layout'})
            # A setting may arrive while the error blocks navigation. Re-place
            # the underlying page, then require its arrows to recover too.
            self.client.switch_command(buttons.key, False)
            await asyncio.sleep(0.2)
            self.client.switch_command(buttons.key, True)
            await asyncio.sleep(0.2)
            # The API acknowledges before the queued LVGL refresh; wait for
            # a stable rendered frame before inspecting its widget geometry.
            await self.render(f'protocol-error-{version}')
            start = len(self.lines)
            await self.call('render_problem')
            line = await self.until(lambda line: 'problem=' in line, 5, 'Missing error view diagnostic', start)
            assert f'problem={problem} covers=1 spinner=0' in line, line
            # A covered navigation tile must not respond to a real touch.
            await self.tap_navigation('tile', 0, titles)
            self.sender.disconnected()
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
            await self.page_done(0)
            restored = await self.render('_after-protocol-error', keep=False)
            if restored.tobytes() != reference.tobytes():
                reference.save(self.out / 'recovery-expected.png')
                restored.save(self.out / 'recovery-actual.png')
            assert restored.tobytes() == reference.tobytes(), 'Recovery must restore the same complete screen'
        await self.call('show_page', page=1)
        await self.page_done(0)
        await self.offline_swipe(True, home_page)
        await self.offline_swipe(False, 0)
        self.warnings.append('Offline swipes passed with the API client disconnected; active layout survived malformed updates')
        return await self.self_test()

    async def rectangular_tiles(self, grid):
        """Real cards in multi-row cells, beside ordinary neighbors, on every board."""
        if grid.rows < 2: return 0
        checks = 0
        for size in ['tall', *(['square'] if grid.columns >= 2 else [])]:
            examples = ([('light.demo', {'inline': 'slider'}), ('sensor.demo_temperature', {'display': 'graph'}),
                         ('screen.clock', {'display': 'analog'})] if size == 'tall' else
                        [('media_player.demo_sonos', {'controls': 'playback'}), ('climate.demo_ac', {}),
                         ('screen.clock', {'display': 'analog'})])
            states = {**send_layout.demo_states(MOMENT), **send_layout.controls_states(MOMENT)}
            tiles = []
            for page, (entity, options) in enumerate(examples[:grid.pages]):
                slot = page * grid.slots
                tiles.append(dict(entity=entity, name=f'{size} card', slot=slot, options={**options, 'size': size}))
                occupied = set(grid.footprint(slot, size))
                neighbor = next((cell for cell in range(slot, slot + grid.slots) if cell not in occupied), None)
                if neighbor is not None:
                    entity = f'sensor.neighbor_{page}'
                    tiles.append(dict(entity=entity, name='Neighbor', slot=neighbor))
                    states[entity] = {'state': '21', 'attributes': {'unit_of_measurement': '°C'}}
            record = send_layout.migrate_legacy(dict(title='Rectangles', tiles=tiles), grid)
            values = []
            for index, tile in enumerate(send_layout.compile_tiles(record['layout'], grid)):
                message = send_layout.state_message(index, tile, states)
                if tile['entity'] == 'sensor.demo_temperature': message['history'] = {'hours': 24, 'values': [18, 20, 19, 23, 21]}
                values.append(message)
            bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
            region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
            checks += await self.self_test()
            for page in range(len(bars)):
                await self.call('render_page', page=page)
                await self.page_done(page)
                await self.render(f'{size}-{page + 1}')
        return checks

    async def bedside_clock(self, grid):
        """The bedside clock over its page with three keys (firmware 0.8.0+), on every board and both orientations: its
        digits come from a size the looks work out from the glass (FONT_BEDSIDE_SIZE), and the self test fails a board
        where they fit in no arrangement or a key falls outside its clock. A key is a tile without a cell (`in`)."""
        states = {**send_layout.demo_states(MOMENT), **send_layout.controls_states(MOMENT),
                  'lock.demo_front': {'state': 'locked', 'attributes': {'friendly_name': 'Front door'}}}
        tiles = [dict(entity='screen.nightstand', name='', slot=0, options={'size': 'full', 'background': 'none'}),
                 *(dict(entity=entity, name=name, key=place, **{'in': 'screen.nightstand'}) for place, (entity, name) in
                   enumerate([('light.demo', 'Lamp'), ('sensor.demo_temperature', 'Bedroom'), ('lock.demo_front', 'Front door')]))]
        record = send_layout.migrate_legacy(dict(title='Bedroom', tiles=tiles), grid)
        values = [send_layout.state_message(i, tile, states) for i, tile in enumerate(send_layout.compile_tiles(record['layout'], grid))]
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        await self.sender.synchronize(self.inbox.object_id, record, region, values, [[{'k': 'clock'}]])
        checks = await self.self_test()
        await self.call('render_page', page=0)
        await self.page_done(0)
        await self.render('bedside')
        return checks

    async def alarm_probe(self):
        start = len(self.lines)
        await self.call('render_alarm')
        line = await self.until(lambda l: ALARM.search(l), 10, 'render_alarm', start)
        m = ALARM.search(line)
        points = lambda text: [tuple(int(n) for n in p.rstrip('d').split(',')) + (p.endswith('d'),) for p in text.split(';') if p]
        return {'open': m[1] == '1', 'pad': m[2] == '1', 'back': tuple(int(n) for n in m[3].split(',')) if m[3] else None,
                'title': m[4], 'status': m[5], 'line': m[6], 'modes': points(m[7]), 'keys': points(m[8]), 'faults': m[9],
                'locked': int(m[10])}

    async def tap(self, x, y):
        await self.call('render_finger', x=x, y=y, down=True)
        await asyncio.sleep(0.15)
        await self.call('render_finger', x=x, y=y, down=False)
        await asyncio.sleep(0.3)

    async def alarm_until(self, test, what, timeout=8):
        end = time.monotonic() + timeout
        while True:
            card = await self.alarm_probe()
            if test(card):
                return card
            if time.monotonic() > end:
                raise RuntimeError(f'alarm: {what}: {card}')
            await asyncio.sleep(0.15)

    async def alarm_panel(self, grid):
        """The alarm panel (firmware 0.3.3+) the way it is used: a finger on the tile opens its card, a mode opens the
        keypad, the digits and OK send Home Assistant's action with the code, Home Assistant answers and its states come
        back through the add-on's own messages. Someone coming in wakes the card with the keypad; three wrong codes lock
        it. Every key a finger's size and inside the glass, checked on every board by the card itself (render_alarm)."""
        from core import alarm_extras, state_message
        entity = 'alarm_control_panel.demo_home'
        calls = []
        self.client.subscribe_service_calls(calls.append)
        def alarm(state, delay=None, **attributes):
            attrs = {'friendly_name': 'Alarm', 'code_format': 'number', 'code_arm_required': True, 'changed_by': None,
                     'supported_features': 1 | 2 | 4 | 8 | 32, **attributes}
            if delay:
                attrs['delay'] = delay
            # The screen's clock stands at MOMENT (render_time), so a delay starts there.
            return {'state': state, 'attributes': attrs, 'last_changed': MOMENT.isoformat()}
        states = {entity: alarm('disarmed'), 'sensor.hall': {'state': '21.5', 'attributes': {'unit_of_measurement': '°C'}}}
        record = send_layout.migrate_legacy(dict(title='Alarm', tiles=[
            dict(entity=entity, name='Alarm', slot=0), dict(entity='sensor.hall', name='Hall', slot=1)]), grid)
        tiles = send_layout.compile_tiles(record['layout'], grid)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        async def push():
            values = []
            for index, tile in enumerate(tiles):
                extra = alarm_extras(states[tile['entity']], None) if tile['entity'] == entity else None
                values.append(state_message(index, tile, states, extra or None))
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        await push()
        await self.call('render_page', page=0)
        await self.page_done(0)
        faults = []
        def keep(card, where):
            if card['faults']:
                faults.append(f'{where}: {card["faults"]}')
        async def call_for(service, since):
            end = time.monotonic() + 8
            while time.monotonic() < end:
                found = [c for c in calls[since:] if c.service == service]
                if found:
                    return found[-1]
                await asyncio.sleep(0.05)
            raise RuntimeError(f'alarm: the screen never sent {service}: {[c.service for c in calls[since:]]}')
        async def type_code(card, digits):
            for digit in digits:
                x, y, _ = card['keys'][10 if digit == '0' else int(digit) - 1]
                await self.tap(x, y)
        await self.render('_alarm-home', keep=False)
        tile = (await self.navigation_state())['tile']
        await self.tap(*tile)
        card = await self.alarm_until(lambda c: c['open'] and not c['pad'], 'the tile never opened its card')
        keep(card, 'card')
        if len(card['modes']) != 5:
            faults.append(f'card: {len(card["modes"])} mode keys, not the five the panel supports (trigger left out)')
        await self.render('alarm-card')
        # Arm away: the keypad, a code, OK. The screen sends the action with the code; Home Assistant answers and the
        # panel goes through its exit delay to armed away.
        await self.tap(*card['modes'][1][:2])
        card = await self.alarm_until(lambda c: c['pad'] and len(c['keys']) == 12, 'Away never opened the keypad')
        keep(card, 'keypad')
        await self.render('alarm-keypad')
        await type_code(card, '1234')
        await self.render('alarm-keypad-typed')
        since = len(calls)
        await self.tap(*card['keys'][11][:2])
        sent = await call_for('alarm_control_panel.alarm_arm_away', since)
        if sent.data.get('code') != '1234' or sent.data.get('entity_id') != entity or not sent.call_id:
            faults.append(f'arm away went out as {sent.service} {sent.data} call_id={sent.call_id}')
        self.client.send_homeassistant_action_response(sent.call_id, True, '', b'')
        states[entity] = alarm('arming', delay=30)
        await push()
        card = await self.alarm_until(lambda c: not c['pad'] and 'Arming' in c['status'], 'the keypad never gave way to the card')
        keep(card, 'arming')
        await self.snapshot(self.out / 'alarm-arming.png')
        states[entity] = alarm('armed_away', changed_by='Sam')
        await push()
        await asyncio.sleep(0.25)
        await self.snapshot(self.out / 'alarm-arriving.png')
        card = await self.alarm_until(lambda c: 'Armed away' in c['status'], 'the card never said armed away')
        await asyncio.sleep(1.6)
        await self.render('alarm-armed')
        # Someone comes in: the screen, on page 1 with the card closed, wakes with the keypad to disarm.
        await self.tap(*card['back'][:2])
        await self.alarm_until(lambda c: not c['open'], 'Back never closed the card')
        states[entity] = alarm('pending', delay=30)
        await push()
        card = await self.alarm_until(lambda c: c['open'] and c['pad'] and c['title'] == 'Disarm', 'pending never opened the keypad')
        keep(card, 'pending keypad')
        await self.snapshot(self.out / 'alarm-pending.png')
        # A wrong code refused by Home Assistant (the manual alarm's ServiceValidationError), then the right one.
        await type_code(card, '9999')
        since = len(calls)
        await self.tap(*card['keys'][11][:2])
        sent = await call_for('alarm_control_panel.alarm_disarm', since)
        self.client.send_homeassistant_action_response(sent.call_id, False, 'Invalid alarm code provided', b'')
        card = await self.alarm_until(lambda c: c['line'] == 'Wrong code', 'a refused code never said so')
        await self.render('alarm-wrong-code', timeout=3)
        refused = [c for c in calls if c.service == 'esphome.screen_alarm_code_refused']
        if not refused or 'code' in refused[-1].data or refused[-1].data.get('failures') != '1':
            faults.append(f'the refusal event: {[c.data for c in refused]}')
        await type_code(card, '1234')
        since = len(calls)
        await self.tap(*card['keys'][11][:2])
        sent = await call_for('alarm_control_panel.alarm_disarm', since)
        self.client.send_homeassistant_action_response(sent.call_id, True, '', b'')
        states[entity] = alarm('disarmed', changed_by='Sam')
        await push()
        card = await self.alarm_until(lambda c: c['open'] and not c['pad'] and 'Disarmed' in c['status'], 'disarming never showed the card')
        await asyncio.sleep(1)
        await self.render('alarm-disarmed')
        # Three wrong codes lock the keypad for 30 s, and Home Assistant hears of each.
        await self.tap(*card['modes'][0][:2])
        card = await self.alarm_until(lambda c: c['pad'], 'Home never opened the keypad')
        for attempt in range(3):
            await type_code(card, '0000')
            since = len(calls)
            await self.tap(*card['keys'][11][:2])
            sent = await call_for('alarm_control_panel.alarm_arm_home', since)
            self.client.send_homeassistant_action_response(sent.call_id, False, 'Invalid alarm code provided', b'')
            card = await self.alarm_until(lambda c: c['line'] in ('Wrong code',) or c['locked'], f'wrong code {attempt + 1} never counted')
            await asyncio.sleep(0.4)
        card = await self.alarm_until(lambda c: c['locked'] > 25 and all(k[2] for k in c['keys']), 'three wrong codes never locked the keypad')
        await self.render('alarm-locked', timeout=3)
        refused = [c for c in calls if c.service == 'esphome.screen_alarm_code_refused']
        if refused[-1].data.get('locked') != '30':
            faults.append(f'the third wrong code locked for {refused[-1].data.get("locked")} s, not 30')
        # The alarm goes off: the screen opens the keypad to disarm by itself (still locked here), and Back shows the
        # card with its big Disarm key.
        states[entity] = alarm('triggered')
        await push()
        card = await self.alarm_until(lambda c: c['pad'] and c['title'] == 'Disarm' and c['status'] == 'Triggered',
                                      'going off never opened the keypad to disarm')
        await self.tap(*card['back'][:2])
        card = await self.alarm_until(lambda c: c['open'] and not c['pad'] and len(c['modes']) == 1, 'triggered never showed the Disarm key')
        keep(card, 'triggered')
        await self.snapshot(self.out / 'alarm-triggered.png')
        # A panel without a code: a mode goes straight out, without a keypad.
        states[entity] = alarm('disarmed', code_format=None)
        await push()
        card = await self.alarm_until(lambda c: len(c['modes']) == 5, 'the codeless card never came')
        since = len(calls)
        await self.tap(*card['modes'][3][:2])
        sent = await call_for('alarm_control_panel.alarm_arm_vacation', since)
        if 'code' in sent.data:
            faults.append(f'a codeless panel was sent a code: {sent.data}')
        await self.tap(*card['back'][:2])
        await self.call('render_page', page=0)
        states[entity] = alarm('arming')
        await push()
        await asyncio.sleep(0.5)
        await self.snapshot(self.out / 'alarm-tile-arming.png')
        self.failures += [f'alarm: {f}' for f in faults]
        self.warnings.append(f'alarm panel: card, keypad, arm with code, entry delay, wrong code, lock, trigger, codeless; {len(calls)} calls')
        return 1

    async def slots(self):
        start = len(self.lines)
        await self.call('render_slots')
        line = await self.until(lambda l: 'slots ' in l, 10, 'render_slots', start)
        found = {}
        for item in line.split('slots ', 1)[1].strip().split(';'):
            if '@' in item:
                entity, point = item.split('@')
                found[entity] = tuple(int(n) for n in point.split(','))
        return found

    async def hold(self, x, y):
        await self.call('render_finger', x=x, y=y, down=True)
        await asyncio.sleep(1.0)
        await self.call('render_finger', x=x, y=y, down=False)
        await asyncio.sleep(0.4)

    async def lock_panel(self, grid):
        """The lock (firmware 0.5.0+) the way it is used: a tap locks at once, a locked lock asks for a second tap on its
        tile, the card (hold) has Lock or Unlock and Open door with its own second tap, a jammed lock shows both keys, a
        lock-only tile never unlocks, and a lock with a code opens the alarm panel's keypad. Home Assistant's answers and
        states come back through the add-on's own messages. Every key a finger's size and inside the glass (render_alarm,
        which reads any open card)."""
        from core import lock_extras, state_message
        calls = []
        self.client.subscribe_service_calls(calls.append)
        def lock(state, name, features=0, **attributes):
            return {'state': state, 'attributes': {'friendly_name': name, 'supported_features': features, **attributes},
                    'last_changed': MOMENT.isoformat()}
        states = {'lock.front_door': lock('locked', 'Front door', changed_by='Keypad'),
                  'lock.back_door': lock('unlocked', 'Back door', 1),
                  'lock.gate': lock('locked', 'Gate'),
                  'lock.garage': lock('jammed', 'Garage'),
                  'lock.shed': lock('locking', 'Shed'),
                  'lock.cellar': lock('unavailable', 'Cellar')}
        order = list(states)
        tiles_in = [dict(entity=e, name=states[e]['attributes']['friendly_name'], slot=i) for i, e in enumerate(order)]
        tiles_in[2]['options'] = {'guard': 'lock_only'}
        record = send_layout.migrate_legacy(dict(title='Locks', tiles=tiles_in[:grid.columns * grid.rows]), grid)
        tiles = send_layout.compile_tiles(record['layout'], grid)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        entries = {}
        async def push():
            values = [state_message(index, tile, states, lock_extras(entries.get(tile['entity'])) or None)
                      for index, tile in enumerate(tiles)]
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        await push()
        await self.call('render_page', page=0)
        await self.page_done(0)
        faults = []
        def keep(card, where):
            if card['faults']:
                faults.append(f'{where}: {card["faults"]}')
        async def call_for(service, since):
            end = time.monotonic() + 8
            while time.monotonic() < end:
                found = [c for c in calls[since:] if c.service == service]
                if found:
                    return found[-1]
                await asyncio.sleep(0.05)
            raise RuntimeError(f'lock: the screen never sent {service}: {[c.service for c in calls[since:]]}')
        def answer(sent, ok=True, text=''):
            self.client.send_homeassistant_action_response(sent.call_id, ok, text, b'')
        async def card_until(test, what):
            return await self.alarm_until(test, what)
        await asyncio.sleep(1.6)
        await self.render('lock-tiles')
        spots = await self.slots()
        # A locked lock asks first: the tile turns orange and says so; the second tap unlocks.
        since = len(calls)
        await self.tap(*spots['lock.front_door'])
        await asyncio.sleep(0.2)
        await self.snapshot(self.out / 'lock-tile-ask.png')
        if [c for c in calls[since:] if c.service.startswith('lock.')]:
            faults.append('one tap on a locked lock already sent an action')
        await asyncio.sleep(0.5)
        await self.tap(*spots['lock.front_door'])
        sent = await call_for('lock.unlock', since)
        if sent.data.get('entity_id') != 'lock.front_door' or 'code' in sent.data:
            faults.append(f'unlock went out as {sent.data}')
        answer(sent)
        states['lock.front_door'] = lock('unlocking', 'Front door')
        await push()
        await asyncio.sleep(0.5)
        await self.snapshot(self.out / 'lock-tile-unlocking.png')
        states['lock.front_door'] = lock('unlocked', 'Front door', changed_by='Wall screen')
        await push()
        await asyncio.sleep(1.8)
        # An unlocked lock locks with one tap.
        since = len(calls)
        await self.tap(*spots['lock.front_door'])
        sent = await call_for('lock.lock', since)
        answer(sent)
        states['lock.front_door'] = lock('locked', 'Front door', changed_by='Wall screen')
        await push()
        await asyncio.sleep(0.3)
        await self.snapshot(self.out / 'lock-tile-locked-arriving.png')
        await asyncio.sleep(1.6)
        # A lock-only tile says so and sends nothing.
        since = len(calls)
        await self.tap(*spots['lock.gate'])
        await asyncio.sleep(0.4)
        await self.snapshot(self.out / 'lock-tile-lock-only.png')
        if [c for c in calls[since:] if c.service.startswith('lock.')]:
            faults.append('a lock-only tile sent an action')
        await asyncio.sleep(3.2)
        # The card: hold the back door (unlocked, with Open door).
        await self.hold(*spots['lock.back_door'])
        card = await card_until(lambda c: c['open'] and len(c['modes']) == 2, 'holding the back door never opened its card with two keys')
        keep(card, 'card unlocked')
        await self.render('lock-card-unlocked')
        since = len(calls)
        await self.tap(*card['modes'][1][:2])
        await asyncio.sleep(0.3)
        await self.snapshot(self.out / 'lock-card-open-ask.png')
        await self.tap(*card['modes'][1][:2])
        sent = await call_for('lock.open', since)
        answer(sent)
        states['lock.back_door'] = lock('open', 'Back door', 1, changed_by='Wall screen')
        await push()
        await asyncio.sleep(0.6)
        await self.render('lock-card-open')
        since = len(calls)
        card = await card_until(lambda c: c['open'], 'the card closed')
        await self.tap(*card['modes'][0][:2])
        sent = await call_for('lock.lock', since)
        answer(sent)
        states['lock.back_door'] = lock('locking', 'Back door', 1)
        await push()
        await asyncio.sleep(0.5)
        await self.snapshot(self.out / 'lock-card-locking.png')
        states['lock.back_door'] = lock('locked', 'Back door', 1, changed_by='Wall screen')
        await push()
        await asyncio.sleep(0.3)
        await self.snapshot(self.out / 'lock-card-locked-arriving.png')
        await asyncio.sleep(1.6)
        card = await card_until(lambda c: c['open'] and len(c['modes']) == 2, 'the locked back door never showed Unlock and Open door')
        keep(card, 'card locked')
        await self.render('lock-card-locked')
        await self.tap(*card['modes'][0][:2])
        await asyncio.sleep(0.3)
        await self.snapshot(self.out / 'lock-card-unlock-ask.png')
        await asyncio.sleep(5.5)
        await self.tap(*card['back'][:2])
        await card_until(lambda c: not c['open'], 'Back never closed the card')
        # A jammed lock shows both keys.
        await self.hold(*spots['lock.garage'])
        card = await card_until(lambda c: c['open'] and len(c['modes']) == 2, 'the jammed garage never showed two keys')
        keep(card, 'card jammed')
        await self.render('lock-card-jammed')
        await self.tap(*card['back'][:2])
        await card_until(lambda c: not c['open'], 'Back never closed the card')
        # A lock-only card: only Lock, and only when it is not locked.
        await self.hold(*spots['lock.gate'])
        card = await card_until(lambda c: c['open'], 'the gate never opened its card')
        if len(card['modes']) != 1:
            faults.append(f'a locked lock-only card offered {len(card["modes"])} keys, not only its lock')
        await self.render('lock-card-lock-only')
        since = len(calls)
        await self.tap(*card['modes'][0][:2])
        await asyncio.sleep(0.6)
        if [c for c in calls[since:] if c.service.startswith('lock.')]:
            faults.append('the lock of a locked lock-only card sent an action')
        await self.tap(*card['back'][:2])
        await card_until(lambda c: not c['open'], 'Back never closed the card')
        # A lock with a code: the tap opens the keypad, the code goes out with the action.
        states['lock.front_door'] = lock('locked', 'Front door', code_format='^\\d{4}$')
        await push()
        await asyncio.sleep(0.8)
        await self.tap(*spots['lock.front_door'])
        card = await card_until(lambda c: c['pad'] and len(c['keys']) == 12, 'a lock with a code never opened the keypad')
        keep(card, 'keypad')
        await self.render('lock-keypad')
        for digit in '1234':
            x, y, _ = card['keys'][10 if digit == '0' else int(digit) - 1]
            await self.tap(x, y)
        await self.render('lock-keypad-typed')
        since = len(calls)
        await self.tap(*card['keys'][11][:2])
        sent = await call_for('lock.unlock', since)
        if sent.data.get('code') != '1234':
            faults.append(f'the code went out as {sent.data}')
        answer(sent, False, 'Invalid code')
        card = await card_until(lambda c: c['line'] == 'Wrong code', 'a refused code never said so')
        await self.render('lock-keypad-wrong', timeout=3)
        refused = [c for c in calls if c.service == 'esphome.screen_lock_code_refused']
        if not refused or 'code' in refused[-1].data:
            faults.append(f'the refusal event: {[c.data for c in refused]}')
        await self.tap(*card['back'][:2])
        await asyncio.sleep(0.5)
        await self.tap(*card['back'][:2])
        await self.call('render_page', page=0)
        await asyncio.sleep(1.6)
        await self.render('lock-tiles-end')
        self.failures += [f'lock: {f}' for f in faults]
        self.warnings.append(f'lock: tile ask, unlock, lock, lock-only, card open/lock/jammed, keypad; {len(calls)} calls')
        return 1

    async def cards(self):
        """What every card on the glass says and how it is coloured, read back from its labels (render_cards)."""
        start = len(self.lines)
        await self.call('render_cards')
        line = await self.until(lambda l: 'cards ' in l, 10, 'render_cards', start)
        found = {}
        for item in line.split('cards ', 1)[1].strip().split(';'):
            if '|' in item:
                entity, value, icon, ink, circle, box = item.split('|')
                found[entity] = {'value': value, 'icon': icon, 'ink': ink, 'circle': circle,
                                 'box': tuple(int(n) for n in box.split(','))}
        return found

    async def humidifier_panel(self, grid):
        """Humidifiers and dehumidifiers (firmware 0.42.0+) as tiles of every size and as their card, in the states Home
        Assistant has for them: drying, humidifying, idle, off, without a humidity sensor, unavailable. Each scene is its own layout; the cards a finger
        opens are rendered, the laundry room's in Dark mode too."""
        from core import extras, state_message
        def unit(state, name, device_class='humidifier', action=None, current=None, target=None, modes=None, mode=None, **more):
            attributes = {'friendly_name': name, 'device_class': device_class, 'min_humidity': 0, 'max_humidity': 100,
                          'supported_features': 1 if modes else 0, **more}
            if modes:
                attributes.update(available_modes=modes, mode=mode)
            if action:
                attributes['action'] = action if state == 'on' else 'off'
            if current is not None:
                attributes['current_humidity'] = current
            if target is not None:
                attributes['humidity'] = target
            return {'state': state, 'attributes': attributes, 'last_changed': MOMENT.isoformat()}
        # A generic hygrostat on a smart plug in a laundry room (GitHub #128): a dehumidifier with Home Assistant's away
        # mode; a bedroom humidifier with every standard mode; and the rest of what Home Assistant reports.
        states = {'humidifier.laundry': unit('on', 'Laundry room', 'dehumidifier', 'drying', 68, 55, ['normal', 'away'], 'normal'),
                  'humidifier.bedroom': unit('on', 'Bedroom', 'humidifier', 'humidifying', 38, 45,
                                             ['normal', 'eco', 'sleep', 'boost', 'auto', 'baby'], 'sleep'),
                  'humidifier.living': unit('on', 'Living room', 'humidifier', 'idle', 46, 45, ['normal', 'eco', 'boost'], 'eco'),
                  'humidifier.office': unit('off', 'Office', 'dehumidifier', 'off', 52, 50),
                  'humidifier.cellar': unit('on', 'Cellar', 'dehumidifier', None, None, 60),
                  'humidifier.attic': unit('unavailable', 'Attic'),
                  # An integration's own modes have no icon: the card lists them by name.
                  'humidifier.closet': unit('on', 'Closet', 'dehumidifier', 'idle', 51, 50, ['continuous', 'laundry', 'auto'], 'laundry')}
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        async def show(name, tiles_in, title='Humidity'):
            tiles_in = [dict(t) for t in tiles_in]
            # First fit, page after page: a tile spans its size's columns and rows from the cell it starts in.
            spans = {'single': (1, 1), 'wide': (2, 1), 'tall': (1, 2), 'square': (2, 2), 'full': (grid.columns, grid.rows)}
            taken = set()
            for tile in tiles_in:
                tile.setdefault('name', states[tile['entity']]['attributes']['friendly_name'])
                # A grid of one column (a board standing up) has no double width: its single cell is already the width.
                if grid.columns < 2 and tile['options'].get('size') in ('wide', 'square'):
                    tile['options'] = {**tile['options'], 'size': 'tall' if tile['options']['size'] == 'square' else 'single'}
                    if tile['options']['size'] == 'single':
                        tile['options'].pop('size')
                w, h = spans[tile['options'].get('size', 'single')]
                w, h = min(w, grid.columns), min(h, grid.rows)
                slot = 0
                while True:
                    page, cell = divmod(slot, grid.slots)
                    row, col = divmod(cell, grid.columns)
                    cells = {(page, row + r, col + c) for r in range(h) for c in range(w)}
                    if col + w <= grid.columns and row + h <= grid.rows and not cells & taken:
                        break
                    slot += 1
                taken |= cells
                tile['slot'] = slot
            record = send_layout.migrate_legacy(dict(title=title, tiles=tiles_in), grid)
            tiles = send_layout.compile_tiles(record['layout'], grid)
            bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
            values = [state_message(index, tile, states, extras(tile, states)) for index, tile in enumerate(tiles)]
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
            pages = len(record['layout']['pages'])
            for page in range(pages):
                await self.call('render_page', page=page)
                await self.page_done(page)
                await asyncio.sleep(1.0)
                await self.render(name if pages == 1 else f'{name}-{page + 1}')
            await self.call('render_page', page=0)
            await self.page_done(0)
            await asyncio.sleep(0.6)
        async def card(name, entity, dark=False):
            spots = await self.slots()
            if entity not in spots:
                self.warnings.append(f'humidifier: {entity} is not on the glass for {name}')
                return
            await self.hold(*spots[entity])
            opened = await self.alarm_until(lambda c: c['open'], f'holding {entity} never opened its card')
            await asyncio.sleep(0.8)
            await self.render(name)
            if opened['faults']:
                self.warnings.append(f'humidifier card {entity}: {opened["faults"]}')
            if dark:
                self.client.switch_command(self.dark_switch.key, True)
                await asyncio.sleep(1.5)
                await self.render(name + '-dark')
                self.client.switch_command(self.dark_switch.key, False)
                await asyncio.sleep(1.5)
            await self.tap(*opened['back'][:2])
            await self.alarm_until(lambda c: not c['open'], 'Back never closed the card')
        e = lambda entity, **options: dict(entity=entity, options=options)
        everyone = [e(x) for x in states if x != 'humidifier.closet']
        await show('humidifier-tiles', everyone)
        self.client.switch_command(self.dark_switch.key, True)
        await asyncio.sleep(1.5)
        await self.render('humidifier-tiles-dark')
        self.client.switch_command(self.dark_switch.key, False)
        await asyncio.sleep(1.5)
        for entity in ('humidifier.laundry', 'humidifier.bedroom', 'humidifier.office', 'humidifier.cellar'):
            await card(f'humidifier-card-{entity.split(".")[1]}', entity, dark=entity == 'humidifier.laundry')
        await show('humidifier-own-modes', [e('humidifier.closet')])
        await card('humidifier-card-closet', 'humidifier.closet')
        await show('humidifier-wide', [e('humidifier.laundry', size='wide', controls='setpoint'),
                                       e('humidifier.bedroom', size='wide', controls='slider'),
                                       e('humidifier.bedroom', size='wide', controls='mode'),
                                       e('humidifier.office', size='wide', controls='toggle'),
                                       e('humidifier.living', size='wide', controls='setpoint'),
                                       e('humidifier.cellar', size='wide', controls='setpoint')])
        await show('humidifier-square', [e('humidifier.bedroom', size='square', controls='setpoint_mode'),
                                         e('humidifier.laundry'), e('humidifier.office')])
        await show('humidifier-square-laundry', [e('humidifier.laundry', size='square', controls='setpoint_mode'),
                                                 e('humidifier.bedroom'), e('humidifier.living')])
        await show('humidifier-tall', [e('humidifier.laundry', size='tall', controls='setpoint_mode'),
                                       e('humidifier.bedroom', size='tall', controls='setpoint_mode')])
        await show('humidifier-full', [e('humidifier.bedroom', size='full', controls='setpoint_mode')])
        return 1

    async def remote_panel(self, grid):
        """A remote (firmware 0.22.0, GitHub #117) the way it is used: a tap opens its card, as Home Assistant's tile card
        opens its dialog, with the power key in the top bar and the activities where the remote has them; the tap option
        toggle switches it, and a key is a tile of its own that performs remote.send_command."""
        from core import extras, state_message
        calls = []
        self.client.subscribe_service_calls(calls.append)
        def remote(state, name, activity=None, activities=None):
            attributes = {'friendly_name': name, 'supported_features': 4 if activities else 0}
            if activities:
                attributes.update(activity_list=activities, current_activity=activity)
            return {'state': state, 'attributes': attributes, 'last_changed': MOMENT.isoformat()}
        hub = ['Watch TV', 'Watch a film', 'Listen to music', 'Play a game']
        states = {'remote.living_room': remote('on', 'Living room', 'Watch TV', hub),
                  'remote.apple_tv': remote('on', 'Apple TV'),
                  'remote.bluray': remote('off', 'Blu-ray'),
                  'remote.shield': remote('on', 'Shield'),
                  'remote.bluray_ir': remote('on', 'Blu-ray IR'),
                  'remote.cinema': remote('unavailable', 'Cinema')}
        tiles_in = [dict(entity=e, name=states[e]['attributes']['friendly_name']) for e in states]
        tiles_in[3]['options'] = {'tap': 'toggle'}
        # A key of the Blu-ray player: Perform action with the command typed, and the device a Broadlink asks for.
        tiles_in[4].update(name='Play', options={'tap': 'action', 'icon': 'play', 'action': {
            'action': 'remote.send_command', 'data': {'command': 'play', 'device': 'bluray'}}})
        tiles_in = tiles_in[:grid.columns * grid.rows]
        for slot, tile in enumerate(tiles_in):
            tile['slot'] = slot
        record = send_layout.migrate_legacy(dict(title='Remotes', tiles=tiles_in), grid)
        tiles = send_layout.compile_tiles(record['layout'], grid)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        # The Apple TV's keypad (firmware 0.22.0) as the add-on sends it for its integration (catalogue.remote_keypad).
        import catalogue
        keypads = {'remote.apple_tv': 'apple_tv'}
        async def push():
            values = [state_message(index, tile, states, extras(tile, states)) for index, tile in enumerate(tiles)]
            for value in values:
                keys = catalogue.remote_keypad(keypads.get(value['entity']))
                if keys:
                    value.setdefault('x', {})['keys'] = keys
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        await push()
        await self.call('render_page', page=0)
        await self.page_done(0)
        faults = []
        async def call_for(service, since):
            end = time.monotonic() + 8
            while time.monotonic() < end:
                found = [c for c in calls[since:] if c.service == service]
                if found:
                    return found[-1]
                await asyncio.sleep(0.05)
            raise RuntimeError(f'remote: the screen never sent {service}: {[c.service for c in calls[since:]]}')
        def answer(sent, ok=True):
            self.client.send_homeassistant_action_response(sent.call_id, ok, '', b'')
        def sent_as(sent, data):
            if dict(sent.data) != data:
                faults.append(f'{sent.service} went out as {dict(sent.data)}, not {data}')
        await asyncio.sleep(1.6)
        await self.render('remote-tiles')
        cards = await self.cards()
        spots = await self.slots()
        grey = cards['remote.bluray']['circle']
        def expect(entity, value, lit, icon, where):
            card = cards.get(entity)
            if card is None:
                faults.append(f'{where}: {entity} is not on the glass')
                return
            if card['value'] != value:
                faults.append(f'{where}: {entity} says "{card["value"]}", not "{value}"')
            if card['icon'] != icon:
                faults.append(f'{where}: {entity} draws icon {card["icon"]}, not {icon}')
            if (card['circle'] != grey) != lit:
                faults.append(f'{where}: {entity} is {"coloured" if card["circle"] != grey else "grey"}, expected {"coloured" if lit else "grey"}')
        expect('remote.living_room', 'Watch TV', True, 'F0454', 'start')
        expect('remote.bluray', 'Off', False, 'F0EC4', 'start')
        if 'remote.shield' in cards:
            expect('remote.shield', 'On', True, 'F0454', 'start')
        # A tap opens the card: the power key and the four activities, the one it runs marked.
        await self.tap(*spots['remote.living_room'])
        card = await self.alarm_until(lambda c: c['open'] and len(c['modes']) == 5, 'the hub never opened its card with power and four activities')
        faults += [f'hub card: {f}' for f in card['faults'].split(';') if f]
        await self.render('remote-card')
        since = len(calls)
        await self.tap(*card['modes'][2][:2])
        sent = await call_for('remote.turn_on', since)
        sent_as(sent, {'entity_id': 'remote.living_room', 'activity': 'Watch a film'})
        answer(sent)
        states['remote.living_room'] = remote('on', 'Living room', 'Watch a film', hub)
        await push()
        await asyncio.sleep(0.8)
        await self.render('remote-card-activity')
        # The power key turns it off; the card shows no activity then.
        card = await self.alarm_until(lambda c: c['open'], 'the card closed')
        since = len(calls)
        await self.tap(*card['modes'][0][:2])
        sent = await call_for('remote.turn_off', since)
        sent_as(sent, {'entity_id': 'remote.living_room'})
        answer(sent)
        states['remote.living_room'] = remote('off', 'Living room', None, hub)
        await push()
        await asyncio.sleep(0.8)
        await self.render('remote-card-off')
        card = await self.alarm_until(lambda c: c['open'], 'the card closed')
        await self.tap(*card['back'][:2])
        await asyncio.sleep(0.6)
        # A remote without activities: its card is the power key alone.
        await self.tap(*spots['remote.bluray'])
        card = await self.alarm_until(lambda c: c['open'] and len(c['modes']) == 1, 'the Blu-ray card never opened with its power key alone')
        faults += [f'plain card: {f}' for f in card['faults'].split(';') if f]
        await self.render('remote-card-plain')
        await self.tap(*card['back'][:2])
        await asyncio.sleep(0.6)
        # A key: remote.send_command with the typed command and the device.
        if 'remote.bluray_ir' in spots:
            since = len(calls)
            await self.tap(*spots['remote.bluray_ir'])
            sent = await call_for('remote.send_command', since)
            sent_as(sent, {'entity_id': 'remote.bluray_ir', 'command': 'play', 'device': 'bluray'})
            answer(sent)
        # Set to On / off, a tap switches it.
        if 'remote.shield' in spots:
            since = len(calls)
            await self.tap(*spots['remote.shield'])
            sent = await call_for('remote.toggle', since)
            sent_as(sent, {'entity_id': 'remote.shield'})
            answer(sent)
        # The keypad: power in the bar, four arrows and OK, Back, Home, Play/Pause, the volume.
        if 'remote.apple_tv' in spots:
            await self.tap(*spots['remote.apple_tv'])
            card = await self.alarm_until(lambda c: c['open'] and len(c['modes']) >= 6, 'the Apple TV never opened its keypad')
            faults += [f'keypad: {f}' for f in card['faults'].split(';') if f]
            await self.render('remote-keypad')
            # modes: the power key, the four arrows, OK, then the round keys.
            for index, command in ((1, 'up'), (5, 'select'), (len(card['modes']) - 2, 'volume_up')):
                since = len(calls)
                await self.tap(*card['modes'][index][:2])
                sent = await call_for('remote.send_command', since)
                sent_as(sent, {'entity_id': 'remote.apple_tv', 'command': command})
            # Down three times in quick succession, as on a remote: three commands, none dropped.
            since = len(calls)
            for _ in range(3):
                await self.tap(*card['modes'][2][:2])
                await asyncio.sleep(0.1)
            await asyncio.sleep(1.0)
            downs = [c for c in calls[since:] if c.service == 'remote.send_command' and dict(c.data).get('command') == 'down']
            if len(downs) != 3:
                faults.append(f'three quick taps on down sent {len(downs)} commands')
            # Each integration's own keys, as Home Assistant's source has them: the row holds what that remote has.
            for platform in ('androidtv_remote', 'roku', 'sky_remote', 'lg_netcast', 'jvc_projector'):
                keypads['remote.apple_tv'] = platform
                await push()
                await asyncio.sleep(1.0)
                card = await self.alarm_until(lambda c: c['open'], 'the card closed')
                faults += [f'{platform} keypad: {f}' for f in card['faults'].split(';') if f]
                await self.render(f'remote-keypad-{platform}')
            await self.tap(*card['back'][:2])
            await asyncio.sleep(0.6)
        await asyncio.sleep(1.6)
        await self.render('remote-tiles-end')
        self.failures += [f'remote: {f}' for f in faults]
        self.warnings.append(f'remote: card, activity, power, plain card, key, toggle; {len(calls)} calls')

    async def media_probe(self):
        start = len(self.lines)
        await self.call('render_media')
        line = await self.until(lambda l: MEDIA.search(l), 10, 'render_media', start)
        m = MEDIA.search(line)
        point = lambda text: tuple(int(n) for n in text.split(',')) if text else None
        points = lambda text: [point(p) for p in text.split(';') if p]
        library = dict(part.split('=', 1) for part in m[8].split(' ') if '=' in part)
        return {'open': m[1] == '1', 'back': point(m[2]), 'pill': point(m[3]), 'library_key': point(m[4]), 'knob': point(m[5]),
                'keys': points(m[6]), 'faults': m[7], 'library': library.get('library') == '1', 'menu': library.get('menu') == '1',
                'folder': int(library.get('folder', 0)), 'items': int(library.get('items', 0)), 'page': library.get('page'),
                'grid': library.get('grid'), 'covers': int(library.get('covers', 0)), 'shown': int(library.get('shown', 0)),
                'marked': int(library.get('marked', 0)), 'lib_back': point(library.get('back')), 'speaker': point(library.get('speaker')),
                'cells': points(library.get('cells', '')), 'pager': points(library.get('pager', '')), 'rows': points(library.get('rows', '')),
                'joins': points(library.get('joins', '')), 'sliders': points(library.get('sliders', '')),
                'menu_pager': points(library.get('mpager', '')), 'input_key': point(library.get('inkey'))}

    async def media_until(self, test, what, timeout=8):
        end = time.monotonic() + timeout
        while True:
            card = await self.media_probe()
            if test(card):
                return card
            if time.monotonic() > end:
                raise RuntimeError(f'media: {what}: {card}')
            await asyncio.sleep(0.15)

    async def saver_panel(self):
        """The screensaver (firmware 0.29.0+) over the demo layout in standby: a cover that plays, a camera and the clock,
        each as ESP Screens says it (screen_saver.py) and with its picture as ESP Screens makes it (camera_feed)."""
        import camera_feed
        import media_art
        import media_library
        calls = []
        self.client.subscribe_service_calls(calls.append)
        pictured = 'camera' in json.loads((REPO / 'screen_manager/app/boards.json').read_text())[self.item.board]
        served = [0]
        async def answer(since, timeout=8):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                for call in calls[since:]:
                    data = dict(call.data)
                    if call.service != 'esphome.screen_camera' or data.get('_answered'):
                        continue
                    # The screensaver's picture as ESP Screens makes it: the screen's full box, within the picture cap.
                    kind, box = data.get('saver'), camera_feed.capped(self.canvas)
                    raw = media_art.png(0, 640) if kind == 'media' else porch(*self.camera)
                    body = camera_feed.encode_saver(raw, box, kind, int(ground.split(',')[0], 16) if ground else 0)
                    url = self.pictures.url(f'{self.item.key}-saver-{served[0]}.bmp', body)
                    served[0] += 1
                    await self.send({'v': 1, 'op': 'camera', 't': 'saver', 'e': data['entity'], 'u': url, 'view': int(data['view'])})
                    call.data['_answered'] = '1'
                    return
                await asyncio.sleep(0.05)
        ground = media_library.ground_colours(media_art.png(0)) or ''
        # The clock's row of entities (firmware 0.50.0+), as the app sends the top bar's items: the temperature first, a
        # text alone, an icon alone, both, and a moment the screen counts itself.
        row = [{'k': 'text', 't': '21°'}, {'k': 'text', 't': 'Open'}, {'k': 'text', 'i': 'F0335', 't': ''},
               {'k': 'text', 'i': 'F140B', 't': '412 W'}, {'k': 'ago', 'i': 'F0D91', 'e': int(MOMENT.timestamp()) - 300}]
        steps = [('clock', {'k': 'clock'}), ('clock-row', {'k': 'clock', 'w': '21°', 'wi': row})]
        if pictured:
            steps = [('media', {'k': 'media', 'e': 'media_player.living_room', 'n': 'Living room', 't': 'Evening Drive',
                                'x': {'artist': 'Nova Coast', 'album': 'Low Sun', 'pic': 'c0ffee1234', 'g': ground}}),
                     ('camera', {'k': 'camera', 'e': 'camera.front_door', 'n': 'Front door'}), *steps]
        async def probe():
            start = len(self.lines)
            await self.call('render_saver')
            m = SAVER.search(await self.until(lambda l: SAVER.search(l), 10, 'render_saver', start))
            return m[1] == '1', [tuple(int(n) for n in p.split(',')) if p != '-' else None for p in m[2].split(';') if p], int(m[3])
        async def sent(since, service, entity, timeout=4):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if any(c.service == service and dict(c.data).get('entity_id') == entity for c in calls[since:]):
                    return
                await asyncio.sleep(0.05)
            raise RuntimeError(f'saver: no {service} for {entity}: {[c.service for c in calls[since:]]}')
        await self.call('render_standby', enter=1)
        for name, message in steps:
            start = len(calls)
            await self.send({'v': 1, 'op': 'saver', **message})
            if not name.startswith('clock'):
                await answer(start)
            await asyncio.sleep(1.5)
            await self.render(f'saver-{name}')
            if name != 'media':
                continue
            # The player's keys (firmware 0.33.0+): each sends its action for the player on the glass and the screen
            # stays in standby; the play key turns at once; a long title ends before the keys; a tap beside them wakes.
            entity = message['e']
            keyed = {**message, 's': 'playing', 'f': 1 | 4 | 8 | 1024 | 16384}
            await self.send({'v': 1, 'op': 'saver', **keyed})
            await asyncio.sleep(0.8)
            dimmed, keys, _ = await probe()
            if not dimmed or len(keys) != 3 or None in keys:
                raise RuntimeError(f'saver: the keys of a player that plays: dimmed={dimmed} keys={keys}')
            await self.render('saver-media-keys')
            for key, service in zip(keys, ('media_player.volume_up', 'media_player.volume_down', 'media_player.media_play_pause')):
                since = len(calls)
                await self.tap(*key)
                await sent(since, service, entity)
                if not (await probe())[0]:
                    raise RuntimeError(f'saver: the tap on the {service} key woke the screen')
            await self.render('saver-media-paused')
            # Volume down held for a second and a half mutes, once, and the screen stays in standby; the next tap on a volume
            # key only takes the mute off.
            async def field(since, value, timeout=4):
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    found = [dict(c.data).get('is_volume_muted') for c in calls[since:] if c.service == 'media_player.volume_mute']
                    if found:
                        return found
                    await asyncio.sleep(0.05)
                raise RuntimeError(f'saver: no volume_mute {value}: {[c.service for c in calls[since:]]}')
            since = len(calls)
            await self.call('render_finger', x=keys[1][0], y=keys[1][1], down=True)
            await asyncio.sleep(2.0)
            await self.call('render_finger', x=keys[1][0], y=keys[1][1], down=False)
            await asyncio.sleep(0.4)
            after = [(c.service, dict(c.data).get('is_volume_muted')) for c in calls[since:] if c.service.startswith('media_player.')]
            if await field(since, 'true') != ['true'] or after != [('media_player.volume_mute', 'true')] or not (await probe())[0]:
                raise RuntimeError(f'saver: holding volume down mutes once and nothing else: {after}')
            await self.send({'v': 1, 'op': 'saver', **keyed, 's': 'paused', 'm': 1})
            await asyncio.sleep(0.8)
            await self.render('saver-media-muted')
            since = len(calls)
            await self.tap(*keys[0])
            after = [(c.service, dict(c.data).get('is_volume_muted')) for c in calls[since:] if c.service.startswith('media_player.')]
            if await field(since, 'false') != ['false'] or after != [('media_player.volume_mute', 'false')] or not (await probe())[0]:
                raise RuntimeError(f'saver: a tap on a volume key of a muted player takes the mute off: {after}')
            # Home Assistant's word after the pause, a player without a volume, and a long title.
            await self.send({'v': 1, 'op': 'saver', **keyed, 's': 'paused', 'f': 1 | 16384})
            await asyncio.sleep(0.8)
            dimmed, alone, _ = await probe()
            if not dimmed or alone[:2] != [None, None] or alone[2] != keys[2]:
                raise RuntimeError(f'saver: a player without a volume keeps the play key alone: {alone}')
            await self.send({'v': 1, 'op': 'saver', **keyed, 't': 'Symphony No. 9 in D minor, Op. 125 "Choral": IV. Presto, Allegro assai',
                             'x': {**message['x'], 'artist': 'Berliner Philharmoniker and the Rundfunkchor Berlin, Herbert von Karajan'}})
            await asyncio.sleep(0.8)
            dimmed, keys, right = await probe()
            if not dimmed or right >= min(k[0] for k in keys) - 20:
                raise RuntimeError(f'saver: a long title runs under the keys: it ends at {right}, keys {keys}')
            await self.render('saver-media-long')
            await self.tap(max(4, right // 2), 12)
            if (await probe())[0]:
                raise RuntimeError('saver: a tap beside the keys did not wake the screen')
            await self.call('render_standby', enter=1)
        await self.call('render_standby', enter=0)
        return 0

    async def media_panel(self, grid):
        """A player the way Spotify is used (firmware 0.24.0, app 0.4.42): its card on its cover's ground with the speaker
        in the top bar, the speaker menu, shuffle and repeat, the library from its folders to a page of covers, a tap
        that plays, and the card of a player at rest. The app's side is played by the add-on's own code (media_library,
        tile_art, camera_feed); Home Assistant's answers have the shape of the Spotify integration's."""
        from core import extras, state_message
        import camera_feed
        import media_library
        import speakers
        import tile_art
        import media_art
        from PIL import Image as PILImage, ImageDraw as PILDraw
        calls = []
        self.client.subscribe_service_calls(calls.append)
        ENTITY = 'media_player.spotify'
        PLAYING = 444983
        def spotify(state='playing', features=PLAYING, **more):
            attributes = {'friendly_name': 'Spotify', 'supported_features': features, 'source_list': ['Bedroom', 'Kitchen', 'Living room']}
            if state in ('playing', 'paused'):
                attributes.update(source='Kitchen', shuffle=True, repeat='all', volume_level=0.42, media_title='Evening Drive',
                                  media_artist='Nova Coast', media_album_name='Low Sun', media_duration=274,
                                  media_position=81, media_position_updated_at=MOMENT.isoformat(),
                                  entity_picture='/api/media_player_proxy/media_player.spotify?token=x&cache=ram')
            attributes.update(more)
            return {'state': state, 'attributes': attributes, 'last_changed': MOMENT.isoformat()}
        states = {ENTITY: spotify()}
        tiles_in = [{'entity': ENTITY, 'name': 'Spotify', 'slot': 0}]
        record = send_layout.migrate_legacy(dict(title='Music', tiles=tiles_in), grid)
        tiles = send_layout.compile_tiles(record['layout'], grid)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        # The card's ground as the add-on reads it from the cover that plays (media_library.ground_colours).
        ground = {'g': media_library.ground_colours(media_art.png(0)) or '-'}
        async def push():
            values = [state_message(index, tile, states, extras(tile, states)) for index, tile in enumerate(tiles)]
            for value in values:
                attributes = states[value['entity']]['attributes']
                more = media_library.player_extras(attributes, PLAYING, ground.get('g'), True)
                # This firmware says speaker_groups: the add-on's speaker menu replaces source_list (speakers.py).
                more.pop('so', None); more.pop('sl', None)
                more.update(speakers.extras(speakers.menu(value['entity'], states, lambda e: 'spotify')))
                value.setdefault('x', {}).update(more)
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        await push()
        await self.call('render_page', page=0)
        await self.page_done(0)
        faults = []
        def picture(seed, size=320):
            """A cover drawn for the renders (media_art): no real record's artwork."""
            return media_art.png(seed, size)
        served = {'cover': 0, 'art': 0}
        async def answer_pictures(since):
            """The pictures the screen asked for since `since`: the card's cover and a page's covers."""
            for call in calls[since:]:
                data = dict(call.data)
                if call.service != 'esphome.screen_camera' or data.get('_answered'):
                    continue
                if 'lib' in data:
                    tokens = [int(t) for t in data['lib'].split(',')]
                    atlas = tile_art.parse(data['atlas'], self.canvas, len(tokens))
                    if atlas is None:
                        faults.append(f'the covers were asked for with frames the app refuses: {data["atlas"][:120]}')
                        continue
                    # Each album keeps its own cover: the one the card plays from (Low Sun) is the same picture here.
                    seeds = [int(((shelf.get(ENTITY, t) or {}).get('id') or f':{t}').rsplit(':', 1)[1]) for t in tokens]
                    body = tile_art.encode([picture(n) for n in seeds], [int(data['bg'], 16)] * len(tokens), atlas, compact=True)
                    url = self.pictures.url(f'{self.item.key}-lib-{served["art"]}.bmp', body)
                    served['art'] += 1
                    await self.send({'v': 1, 'op': 'camera', 't': 'lib', 'e': ENTITY, 'u': url, 'view': int(data['view'])})
                elif data.get('size'):
                    body = camera_feed.encode_cover(picture(0), int(data['size']), int(data['bg'], 16))
                    url = self.pictures.url(f'{self.item.key}-cover-{served["cover"]}.bmp', body)
                    served['cover'] += 1
                    await self.send({'v': 1, 'op': 'camera', 't': 'cover', 'e': ENTITY, 'u': url, 'view': int(data['view'])})
                call.data['_answered'] = '1'
        async def call_for(service, since, timeout=8):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                found = [c for c in calls[since:] if c.service == service]
                if found:
                    return found[-1]
                await asyncio.sleep(0.05)
            raise RuntimeError(f'media: the screen never sent {service}: {[c.service for c in calls[since:]]}')
        def answer(sent, ok=True):
            if getattr(sent, 'call_id', 0):
                self.client.send_homeassistant_action_response(sent.call_id, ok, '', b'')
        # The library as Home Assistant's Spotify integration answers it: eight folders at the top, 48 albums in one.
        shelf = media_library.Shelf()
        folders = ['Playlists', 'Artists', 'Albums', 'Liked songs', 'Podcasts', 'Recently played', 'Top Artists', 'Top Tracks']
        classes = ['playlist', 'artist', 'album', 'track', 'podcast', 'track', 'artist', 'track']
        top = {'title': 'Media Library', 'children': [{'title': name, 'media_class': 'directory', 'children_media_class': kind,
               'media_content_type': f'spotify://{name}', 'media_content_id': name, 'can_play': False, 'can_expand': True}
               for name, kind in zip(folders, classes)]}
        albums = {'title': 'Albums', 'children': [{'title': title, 'media_class': 'album', 'media_content_type': 'spotify://album',
                  'media_content_id': f'spotify:album:{n}', 'can_play': True, 'can_expand': True, 'thumbnail': f'https://i.scdn.co/image/{n}'}
                  for n, title in enumerate(([title for title, _ in media_art.ALBUMS[:7]] + [media_art.LONG_ALBUM] + [title for title, _ in media_art.ALBUMS[7:]]) * 2)
                  if n < 48]}
        async def answer_browse(since):
            sent = await call_for('esphome.screen_browse', since)
            data = dict(sent.data)
            token = int(data['folder'])
            folder = media_library.folder_of(top if token == 0 else albums)
            items = media_library.entries(folder, shelf, ENTITY)
            pages = media_library.pages(items)
            await self.send({**media_library.message(ENTITY, token, folder['title'], int(data['page']), pages, len(items)), 'view': int(data['view'])})
            return token
        await asyncio.sleep(1.0)
        spots = await self.slots()
        # The card: a tap on the tile opens it, on the cover's ground, the speaker in the pill.
        since = len(calls)
        await self.tap(*spots[ENTITY])
        card = await self.media_until(lambda c: c['open'] and c['pill'], 'the card never opened with its speaker pill')
        faults += [f'card: {f}' for f in card['faults'].split(';') if f]
        await asyncio.sleep(0.6)
        await answer_pictures(since)
        await asyncio.sleep(2.5)
        await answer_pictures(since)
        await self.render('media-card')
        # The speaker menu: a tap on the pill, a row per speaker, the one it plays on ticked; a row chooses it.
        await self.tap(*card['pill'][:2])
        card = await self.media_until(lambda c: c['menu'] and len(c['rows']) == 3, 'the speaker menu never opened with three rows')
        await self.render('media-speakers')
        since = len(calls)
        await self.tap(*card['rows'][0][:2])
        # A speaker goes to the app, which moves Spotify there with select_source (speakers.plan).
        sent = await call_for('esphome.screen_speaker', since)
        if {k: v for k, v in dict(sent.data).items() if k in ('entity', 'speaker', 'op')} != {'entity': ENTITY, 'speaker': 'Bedroom', 'op': 'pick'}:
            faults.append(f'a speaker was picked as {dict(sent.data)}')
        answer(sent)
        states[ENTITY] = spotify(source='Bedroom')
        await push()
        card = await self.media_until(lambda c: c['open'] and not c['menu'], 'the menu never closed')
        # Shuffle and repeat, where the row has room: the first key after next is shuffle.
        # The library: its key at the end of the volume row (the top right before 0.39.0), then the eight folders as cards.
        since = len(calls)
        await self.tap(*card['library_key'][:2])
        await answer_browse(since)
        card = await self.media_until(lambda c: c['library'] and c['items'] == 8, 'the library never showed its eight folders')
        await self.render('media-library')
        # Albums: a page of covers, then their picture.
        since = len(calls)
        await self.tap(*card['cells'][2][:2])
        await answer_browse(since)
        card = await self.media_until(lambda c: c['library'] and c['items'] == 48, 'the albums never came')
        if card['covers']:
            await asyncio.sleep(0.5)
            await answer_pictures(since)
            card = await self.media_until(lambda c: c['shown'] == c['covers'], 'the covers never showed', timeout=20)
        await self.render('media-albums')
        if card['pager']:
            since2 = len(calls)
            await self.tap(*card['pager'][1][:2])
            card = await self.media_until(lambda c: c['page'].startswith('1/'), 'the next page never came')
            if card['covers']:
                await asyncio.sleep(0.5)
                await answer_pictures(since2)
                card = await self.media_until(lambda c: c['shown'] == c['covers'], 'the covers of page 2 never showed', timeout=20)
            await self.render('media-albums-2')
        # A tap on a cover plays it where the player plays now.
        since = len(calls)
        await self.tap(*card['cells'][0][:2])
        sent = await call_for('esphome.screen_play', since)
        data = dict(sent.data)
        if data.get('source') or not data.get('item'):
            faults.append(f'a tap on a cover asked to play {data}')
        card = await self.media_until(lambda c: c['marked'] == int(data['item']), 'the tapped cover was never marked')
        await self.render('media-albums-starting')
        # Back twice: the folders, then the card again.
        since = len(calls)
        await self.tap(*card['lib_back'][:2])
        await answer_browse(since)
        card = await self.media_until(lambda c: c['library'] and c['items'] == 8, 'back never went to the folders')
        await self.tap(*card['lib_back'][:2])
        card = await self.media_until(lambda c: c['open'] and not c['library'], 'back never went to the card')
        # A player that is on and can be turned off (a TV): its power key at the top right (firmware 0.39.0, GitHub #146).
        # Nothing plays and there is no cover, so the card is plain black.
        states[ENTITY] = spotify('on', features=PLAYING | 256, volume_level=0.28, friendly_name='TV', device_class='tv', source_list=[])
        cover_ground = ground.pop('g', None)
        await push()
        await asyncio.sleep(1.0)
        await self.render('media-power')
        if cover_ground is not None:
            ground['g'] = cover_ground
        # At rest, as Spotify playing nowhere: only SELECT_SOURCE, no track; the card offers the library.
        states[ENTITY] = spotify('idle', features=2048)
        ground.pop('g')
        await push()
        await asyncio.sleep(1.0)
        await self.render('media-rest')
        card = await self.media_until(lambda c: c['open'] and len(c['keys']) >= 1, 'the card at rest has no Library key')
        faults += [f'card at rest: {f}' for f in card['faults'].split(';') if f]
        # Its Library key opens the library; a cover then asks for a speaker first, and plays on the one chosen.
        since = len(calls)
        await self.tap(*card['keys'][-1][:2])
        await answer_browse(since)
        card = await self.media_until(lambda c: c['library'] and c['items'] == 8, 'the library never opened at rest')
        since = len(calls)
        await self.tap(*card['cells'][2][:2])
        await answer_browse(since)
        card = await self.media_until(lambda c: c['library'] and c['items'] == 48, 'the albums never came at rest')
        await self.tap(*card['cells'][1][:2])
        card = await self.media_until(lambda c: c['menu'] and len(c['rows']) == 3, 'a cover at rest never asked for a speaker')
        await self.render('media-rest-speakers')
        since = len(calls)
        await self.tap(*card['rows'][2][:2])
        sent = await call_for('esphome.screen_play', since)
        if dict(sent.data).get('source') != 'Living room':
            faults.append(f'a start at rest went out as {dict(sent.data)}')
        await asyncio.sleep(0.6)
        # Favourites (firmware 0.24.0): an album on one cell, a playlist on two with its own speaker, one without a picture.
        await self.tap(*card['lib_back'][:2]) if card.get('lib_back') else None
        await asyncio.sleep(0.4)
        library = await self.media_probe()
        if library['library']:
            await self.tap(*library['lib_back'][:2])
            await asyncio.sleep(0.4)
        library = await self.media_probe()
        if library['open'] and library['back']:
            await self.tap(*library['back'][:2])
            await asyncio.sleep(0.6)
        states[ENTITY] = spotify(source='Kitchen')
        favorites = [
            {'entity': ENTITY, 'name': '', 'slot': 0, 'options': {'display': 'favorite', 'play': {'id': 'spotify:album:1', 'type': 'spotify://album',
             'title': 'Low Sun', 'thumb': 'https://i.scdn.co/image/1', 'class': 'album'}}},
            {'entity': ENTITY, 'name': 'Deep Focus', 'slot': 1, 'options': {'display': 'favorite', 'play': {'id': 'spotify:playlist:2', 'type': 'spotify://playlist',
             'title': 'Deep Focus', 'thumb': 'https://i.scdn.co/image/2', 'class': 'playlist'}, 'speaker': 'Bedroom'}},
            {'entity': ENTITY, 'name': '', 'slot': grid.columns, 'options': {'display': 'favorite', 'size': 'wide', 'play': {'id': 'spotify:playlist:3', 'type': 'spotify://playlist',
             'title': 'Sunday Morning', 'thumb': 'https://i.scdn.co/image/3', 'class': 'playlist'}, 'speaker': 'Kitchen'}},
            {'entity': ENTITY, 'name': '', 'slot': 2 * grid.columns, 'options': {'display': 'favorite', 'play': {'id': 'spotify:artist:4', 'type': 'spotify://artist',
             'title': 'Nova Coast', 'class': 'artist'}}},
            {'entity': ENTITY, 'name': 'Spotify', 'slot': 2 * grid.columns + 1, 'options': {'display': 'cover'}}]
        favorites = [tile for tile in favorites if tile['slot'] < grid.columns * grid.rows]
        record = send_layout.migrate_legacy(dict(title='Favourites', tiles=favorites), grid)
        tiles = send_layout.compile_tiles(record['layout'], grid)
        started = {'id': None}
        WORDS = {'album': 'Album', 'playlist': 'Playlist', 'artist': 'Artist'}
        async def push_favorites():
            values = [state_message(index, {**tile, 'name': tile['name'] or (tile['options'].get('play') or {}).get('title', '')}, states, extras(tile, states))
                      for index, tile in enumerate(tiles)]
            for value, tile in zip(values, tiles):
                attributes = states[value['entity']]['attributes']
                value.setdefault('x', {}).update(media_library.player_extras(attributes, PLAYING, '2B484F,121E20', True))
                play = tile['options'].get('play')
                # Home Assistant's word for the player's state rides along, as the add-on sends it (core.state_word):
                # a favourite says what it plays all the same.
                value['x']['w'] = 'Playing' if states[value['entity']]['state'] == 'playing' else 'Idle'
                if play:
                    mine = started['id'] == play['id']
                    value['x'].update(media_library.favorite_extras(play, tile['options'].get('speaker'), attributes if mine else {},
                                                                    (play['type'], play['id']) if mine else None, WORDS[play['class']]))
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        await push_favorites()
        await asyncio.sleep(0.8)
        # Before their pictures come, the favourites wait with the spinner every picture card has (a moment, one snapshot).
        (await self.snapshot(self.out / 'media-favorites-waiting.ppm')).save(self.out / 'media-favorites-waiting.png')
        (self.out / 'media-favorites-waiting.ppm').unlink(missing_ok=True)
        # A favourite without a picture never waits for one.
        start = len(self.lines)
        await self.call('render_cards')
        await self.until(lambda l: 'cards ' in l, 10, 'render_cards', start)
        async def answer_strip(since):
            for call in calls[since:]:
                data = dict(call.data)
                if call.service != 'esphome.screen_camera' or 'tiles' not in data or data.get('_answered'):
                    continue
                entities = data['tiles'].split(',')
                atlas = tile_art.parse(data.get('atlas'), self.canvas, len(entities)) if data.get('atlas') else None
                if atlas is None:
                    faults.append(f'the favourites asked for their pictures without frames the app takes: {data}')
                    continue
                indexes = [int(n) for n in data['idx'].split(',')]
                # Low Sun and the player that plays from it share the card's cover; the playlists have their own.
                seeds = {0: 0, 1: 2, 2: 6, 4: 0}
                body = tile_art.encode([picture(seeds.get(i, i + 3)) for i in indexes], [int(g, 16) for g in data['bg'].split(',')], atlas, compact=True)
                url = self.pictures.url(f'{self.item.key}-strip-{served["art"]}.bmp', body)
                served['art'] += 1
                await self.send({'v': 1, 'op': 'camera', 't': 'live', 'e': data['tiles'], 'u': url, 'view': int(data['view'])})
                call.data['_answered'] = '1'
        since = 0
        await asyncio.sleep(1.0)
        await answer_strip(since)
        await asyncio.sleep(2.0)
        await answer_strip(since)
        await asyncio.sleep(1.5)
        await self.render('media-favorites')
        # Every card of the page in slot order (they are all the same player): its box.
        start = len(self.lines)
        await self.call('render_cards')
        line = await self.until(lambda l: 'cards ' in l, 10, 'render_cards', start)
        boxes = [tuple(int(n) for n in item.split('|')[5].split(',')) for item in line.split('cards ', 1)[1].strip().split(';') if '|' in item]
        # A tap on the playlist on two cells: it asks the app to play that tile.
        playlist = next((i for i, tile in enumerate(tiles) if tile['options'].get('size') == 'wide'), None)
        if playlist is not None and boxes:
            since = len(calls)
            # The widest card, a little left of its key.
            wide = max(boxes, key=lambda b: b[2] - b[0])
            await self.tap((wide[0] + wide[2]) // 2 - 40, (wide[1] + wide[3]) // 2)
            sent = await call_for('esphome.screen_play', since)
            if dict(sent.data).get('tile') != str(playlist):
                faults.append(f'a favourite asked to play {dict(sent.data)}, not tile {playlist}')
            # While it starts its key turns (an animation: one snapshot, never two equal ones) and its line says so.
            await asyncio.sleep(0.6)
            start = len(self.lines)
            await self.call('render_cards')
            line = await self.until(lambda l: 'cards ' in l, 10, 'render_cards', start)
            if 'Starting on Kitchen' not in line or 'Playlist · Bed' not in line:
                faults.append(f'a favourite that starts does not say so: {line.split("cards ", 1)[1][:200]}')
            (await self.snapshot(self.out / 'media-favorites-starting.ppm')).save(self.out / 'media-favorites-starting.png')
            (self.out / 'media-favorites-starting.ppm').unlink(missing_ok=True)
            started['id'] = tiles[playlist]['options']['play']['id']
            states[ENTITY] = spotify(source='Kitchen', media_title='Coffee in the Garden', media_artist='Willow & Fern', media_playlist='Sunday Morning')
            await push_favorites()
            await asyncio.sleep(1.0)
            await answer_strip(since)
            await asyncio.sleep(1.5)
            await self.render('media-favorites-playing')
        await self.media_group(grid, calls, call_for, answer, faults, region, bars)
        self.failures += [f'media: {f}' for f in faults]
        self.warnings.append(f'media: card, speakers, library, albums, play, rest, favourites, group, inputs; {served["cover"]} covers, {served["art"]} pictures')
        return 1

    async def _menu_next(self, card):
        """The menu's next page, when there is one (its pager says '3 / 3' on the last)."""
        before = card['rows']
        await self.tap(*card['menu_pager'][1][:2])
        await asyncio.sleep(0.5)
        after = await self.media_probe()
        return after['rows'] != before

    async def media_group(self, grid, calls, call_for, answer, faults, region, bars):
        """A Sonos the way it groups (firmware 0.26.0, speakers.py): its card with the input key, the pill naming the
        group, the speaker menu with a tick and a volume for each speaker in the group and a plus for the others, a plus
        that joins, and the inputs. Home Assistant's states have the shape of the Sonos integration's."""
        from core import extras, state_message
        import media_library
        import speakers
        names = {'living_room': 'Living room', 'kitchen': 'Kitchen', 'bedroom': 'Bedroom', 'bathroom': 'Bathroom'}
        group = ['media_player.living_room', 'media_player.kitchen']
        def sonos(key, members, volume):
            on = f'media_player.{key}' in members
            return {'state': 'playing' if on else 'idle', 'last_changed': MOMENT.isoformat(), 'attributes': {
                'friendly_name': names[key], 'supported_features': 8321599, 'volume_level': volume, 'group_members': members if on else [],
                'source_list': ['TV', 'Radio One', 'Radio Two'], **({'media_title': 'Evening Drive', 'media_artist': 'Nova Coast',
                'media_album_name': 'Low Sun', 'media_duration': 274, 'media_position': 81, 'media_position_updated_at': MOMENT.isoformat()} if on else {})}}
        volumes = {'living_room': 0.32, 'kitchen': 0.24, 'bedroom': 0.2, 'bathroom': 0.15}
        def house(members):
            return {f'media_player.{k}': sonos(k, members, v) for k, v in volumes.items()}
        states = house(group)
        ENTITY = 'media_player.living_room'
        record = send_layout.migrate_legacy(dict(title='Sonos', tiles=[{'entity': ENTITY, 'name': 'Living room', 'slot': 0}]), grid)
        tiles = send_layout.compile_tiles(record['layout'], grid)
        async def push():
            values = [state_message(index, tile, states, extras(tile, states)) for index, tile in enumerate(tiles)]
            for value in values:
                more = media_library.player_extras(states[value['entity']]['attributes'], 8321599, None, True)
                more.pop('so', None); more.pop('sl', None)
                more.update(speakers.extras(speakers.menu(value['entity'], states, lambda e: 'sonos')))
                value.setdefault('x', {}).update(more)
            await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        await push()
        await asyncio.sleep(1.5)
        spots = await self.slots()
        await self.tap(*spots[ENTITY])
        card = await self.media_until(lambda c: c['open'] and c['pill'] and c['input_key'], 'the Sonos card never opened with its pill and input key')
        faults += [f'group card: {f}' for f in card['faults'].split(';') if f]
        await asyncio.sleep(0.8)
        await self.render('media-group-card')
        await self.tap(*card['pill'][:2])
        card = await self.media_until(lambda c: c['menu'] and c['rows'], 'the speaker menu never opened')
        await self.render('media-group-speakers')
        if len(card['sliders']) < 1 or not card['joins']:
            faults.append(f'the group menu shows {len(card["sliders"])} volumes and {len(card["joins"])} keys')
        # The plus of the last speaker, outside the group, on the last page joins it.
        while card['menu_pager'] and await self._menu_next(card):
            card = await self.media_until(lambda c: c['menu'] and c['joins'], 'the next page never came')
        await self.render('media-group-speakers-last')
        since = len(calls)
        await self.tap(*card['joins'][-1][:2])
        target = 'Bedroom'
        if target:
            sent = await call_for('esphome.screen_speaker', since)
            if {k: v for k, v in dict(sent.data).items() if k in ('speaker', 'op')} != {'speaker': target, 'op': 'join'}:
                faults.append(f'a plus asked {dict(sent.data)}')
            answer(sent)
            found = speakers.menu(ENTITY, states, lambda e: 'sonos')
            steps, _ = speakers.plan(ENTITY, found, speakers.find(found, target), 'join', states)
            if steps != [('media_player', 'join', {'entity_id': ENTITY, 'group_members': ['media_player.bedroom']})]:
                faults.append(f'the app would join with {steps}')
            states = house(group + ['media_player.bedroom'])
            await push()
            await asyncio.sleep(1.0)
            await self.render('media-group-joined')
        # Beside the menu closes it; the input key opens the inputs, and one goes out as Home Assistant's select_source.
        await self.tap(3, self.canvas[1] - 3)
        card = await self.media_until(lambda c: c['open'] and not c['menu'], 'the speaker menu never closed')
        await self.tap(*card['input_key'][:2])
        card = await self.media_until(lambda c: c['menu'] and len(c['rows']) >= 1, 'the inputs never opened')
        await self.render('media-inputs')
        since = len(calls)
        await self.tap(*card['rows'][0][:2])
        sent = await call_for('media_player.select_source', since)
        if dict(sent.data) != {'entity_id': ENTITY, 'source': 'TV'}:
            faults.append(f'an input went out as {dict(sent.data)}')
        answer(sent)
        # The same player as a tile over the whole page (firmware 0.39.0, GitHub #146): the volume row is volume down,
        # the slider and volume up, as on the card.
        await asyncio.sleep(0.6)
        card = await self.media_probe()
        if card['menu']:
            await self.tap(3, self.canvas[1] - 3)
            card = await self.media_until(lambda c: not c['menu'], 'the inputs never closed')
        if card['open'] and card['back']:
            await self.tap(*card['back'][:2])
            await self.media_until(lambda c: not c['open'], 'the card never closed')
        record = send_layout.migrate_legacy(dict(title='Sonos', tiles=[{'entity': ENTITY, 'name': 'Living room', 'slot': 0, 'options': {'size': 'full'}}]), grid)
        tiles = send_layout.compile_tiles(record['layout'], grid)
        await push()
        await asyncio.sleep(1.5)
        await self.render('media-full')

    async def automation_panel(self, grid):
        """An automation (firmware 0.7.0, GitHub #62) the way it is used: a tap switches it on or off and holding runs its
        actions; a tile set to run does it the other way round and looks like a script's button, coloured only while
        the actions run. Home Assistant's answers and states come back through the add-on's own messages (core.extras
        sends when it last ran and whether it runs now)."""
        from core import extras, state_message
        calls = []
        self.client.subscribe_service_calls(calls.append)
        def automation(state, name, current=0, last='2026-09-15T07:30:00+00:00'):
            return {'state': state, 'attributes': {'friendly_name': name, 'current': current, 'last_triggered': last,
                                                   'mode': 'single', 'id': name.lower()},
                    'last_changed': MOMENT.isoformat()}
        states = {'automation.curtains': automation('on', 'Curtains'),
                  'automation.holiday': automation('off', 'Holiday lights'),
                  'automation.doorbell': automation('on', 'Doorbell chime'),
                  'automation.night': automation('off', 'Night mode'),
                  'automation.garden': automation('unavailable', 'Garden'),
                  'automation.away': automation('on', 'Away')}
        order = list(states)
        tiles_in = [dict(entity=e, name=states[e]['attributes']['friendly_name'], slot=i) for i, e in enumerate(order)]
        tiles_in[2]['options'] = {'tap': 'run'}
        tiles_in[3]['options'] = {'tap': 'run'}
        record = send_layout.migrate_legacy(dict(title='Automations', tiles=tiles_in[:grid.columns * grid.rows]), grid)
        tiles = send_layout.compile_tiles(record['layout'], grid)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        shown = {'record': record, 'tiles': tiles, 'bars': bars}
        async def push():
            values = [state_message(index, tile, states, extras(tile, states)) for index, tile in enumerate(shown['tiles'])]
            await self.sender.synchronize(self.inbox.object_id, shown['record'], region, values, shown['bars'])
        await push()
        await self.call('render_page', page=0)
        await self.page_done(0)
        faults = []
        async def call_for(service, since):
            end = time.monotonic() + 8
            while time.monotonic() < end:
                found = [c for c in calls[since:] if c.service == service]
                if found:
                    return found[-1]
                await asyncio.sleep(0.05)
            raise RuntimeError(f'automation: the screen never sent {service}: {[c.service for c in calls[since:]]}')
        def answer(sent, ok=True):
            self.client.send_homeassistant_action_response(sent.call_id, ok, '', b'')
        def sent_only(sent, entity):
            if dict(sent.data) != {'entity_id': entity}:
                faults.append(f'{sent.service} went out as {dict(sent.data)}')
        async def expect(entity, value=None, lit=None, icon=None, where=''):
            card = (await self.cards()).get(entity)
            if card is None:
                faults.append(f'{where}: {entity} is not on the glass')
                return
            if value is not None and card['value'] != value:
                faults.append(f'{where}: {entity} says "{card["value"]}", not "{value}"')
            if icon is not None and card['icon'] != icon:
                faults.append(f'{where}: {entity} draws icon {card["icon"]}, not {icon}')
            if lit is not None and (card['circle'] != grey) == (not lit):
                faults.append(f'{where}: {entity} is {"grey" if card["circle"] == grey else "coloured"} ({card["circle"]}), expected {"coloured" if lit else "grey"}')
            return card
        await asyncio.sleep(1.6)
        await self.render('automation-tiles')
        spots = await self.slots()
        start = await self.cards()
        grey = start['automation.holiday']['circle']
        await expect('automation.curtains', 'On', True, 'F06A9', 'start')
        await expect('automation.holiday', 'Off', False, 'F16A7', 'start')
        # A run button: grey at rest although the automation is on, and when it last ran under its name.
        await expect('automation.doorbell', lit=False, icon='F06A9', where='start')
        if start['automation.doorbell']['value'] in ('On', 'Off', ''):
            faults.append(f'start: the run button says "{start["automation.doorbell"]["value"]}" instead of when it last ran')
        # A run button of an automation that is off says so: a tap still runs it, nothing starts it on its own.
        await expect('automation.night', 'Off', False, 'F16A7', 'start')
        # Unavailable: in the unavailable grey, not the colour of an automation that is on, and taps send nothing.
        if 'automation.garden' in start and start['automation.garden']['circle'] == start['automation.curtains']['circle']:
            faults.append('start: an unavailable automation is coloured like one that is on')
        # Tap on an automation that switches: it turns off at once (optimistic) and automation.toggle goes out.
        since = len(calls)
        await self.tap(*spots['automation.curtains'])
        sent = await call_for('automation.toggle', since)
        sent_only(sent, 'automation.curtains')
        await asyncio.sleep(0.1)
        await expect('automation.curtains', 'Off', False, where='right after the tap')
        await self.snapshot(self.out / 'automation-toggle-tapped.png')
        answer(sent)
        states['automation.curtains'] = automation('off', 'Curtains')
        await push()
        await asyncio.sleep(0.6)
        await expect('automation.curtains', 'Off', False, 'F16A7', 'after Home Assistant')
        # Tap again: back on.
        since = len(calls)
        await self.tap(*spots['automation.curtains'])
        sent = await call_for('automation.toggle', since)
        answer(sent)
        states['automation.curtains'] = automation('on', 'Curtains')
        await push()
        await asyncio.sleep(0.6)
        await expect('automation.curtains', 'On', True, 'F06A9', 'switched back on')
        # Hold it: its actions run (automation.trigger with the entity alone) and it stays on.
        since = len(calls)
        await self.hold(*spots['automation.curtains'])
        sent = await call_for('automation.trigger', since)
        sent_only(sent, 'automation.curtains')
        if [c for c in calls[since:] if c.service == 'automation.toggle']:
            faults.append('holding a switching tile also switched it')
        answer(sent)
        await asyncio.sleep(0.4)
        await expect('automation.curtains', 'On', True, where='after holding')
        # The run button: a tap runs its actions; while they run it is coloured and says so.
        since = len(calls)
        await self.tap(*spots['automation.doorbell'])
        sent = await call_for('automation.trigger', since)
        sent_only(sent, 'automation.doorbell')
        if [c for c in calls[since:] if c.service.endswith(('.toggle', '.turn_on', '.turn_off'))]:
            faults.append('a tap on a run button also switched it')
        answer(sent)
        states['automation.doorbell'] = automation('on', 'Doorbell chime', current=1, last='2026-09-15T08:08:00+00:00')
        await push()
        await asyncio.sleep(0.6)
        await expect('automation.doorbell', 'Running...', True, where='while its actions run')
        await self.render('automation-running')
        states['automation.doorbell'] = automation('on', 'Doorbell chime', current=0, last='2026-09-15T08:08:00+00:00')
        await push()
        await asyncio.sleep(0.6)
        done = await expect('automation.doorbell', lit=False, where='after its actions ran')
        if done and done['value'] in ('Running...', 'On', 'Off'):
            faults.append(f'after its actions ran the run button says "{done["value"]}"')
        # Hold the run button: it switches off, at once, and says Off.
        since = len(calls)
        await self.hold(*spots['automation.doorbell'])
        sent = await call_for('automation.toggle', since)
        sent_only(sent, 'automation.doorbell')
        if [c for c in calls[since:] if c.service == 'automation.trigger']:
            faults.append('holding a run button also ran it')
        await expect('automation.doorbell', 'Off', False, where='right after holding the run button')
        answer(sent)
        states['automation.doorbell'] = automation('off', 'Doorbell chime', last='2026-09-15T08:08:00+00:00')
        await push()
        await asyncio.sleep(0.6)
        await expect('automation.doorbell', 'Off', False, 'F16A7', 'run button switched off')
        await self.render('automation-run-off')
        # A run button of an automation that is off still runs on a tap.
        since = len(calls)
        await self.tap(*spots['automation.night'])
        sent = await call_for('automation.trigger', since)
        answer(sent)
        # Unavailable: nothing goes out.
        if 'automation.garden' in spots:
            since = len(calls)
            await self.tap(*spots['automation.garden'])
            await self.hold(*spots['automation.garden'])
            await asyncio.sleep(0.4)
            if [c for c in calls[since:] if c.service.startswith('automation.')]:
                faults.append('an unavailable automation sent an action')
        await asyncio.sleep(1.6)
        await self.render('automation-tiles-end')
        # Double-width cards carry the switch (the default control) beside the name; the run button's switch switches
        # it while a tap on the card runs it.
        wide_in = [dict(entity='automation.curtains', name='Curtains', options={'size': 'wide'}),
                   dict(entity='automation.doorbell', name='Doorbell chime', options={'size': 'wide', 'tap': 'run'}),
                   dict(entity='automation.away', name='Away', options={'size': 'wide', 'controls': 'run'})][:grid.rows]
        for row, tile in enumerate(wide_in):
            tile['slot'] = row * grid.columns
        shown['record'] = send_layout.migrate_legacy(dict(title='Automations', tiles=wide_in), grid)
        shown['tiles'] = send_layout.compile_tiles(shown['record']['layout'], grid)
        shown['bars'] = [[{'k': 'clock'}] for _ in shown['record']['layout']['pages']]
        await push()
        await self.call('render_page', page=0)
        await self.page_done(0)
        await asyncio.sleep(1.6)
        await self.render('automation-wide')
        # The control at the right end of a double-width card: its switch switches, its Run key runs, and a tap on
        # the card itself does what the tile's tap says.
        wide = await self.cards()
        def control(entity):
            x1, y1, x2, y2 = wide[entity]['box']
            return x2 - (y2 - y1) * 2 // 5, (y1 + y2) // 2
        since = len(calls)
        await self.tap(*control('automation.curtains'))
        sent = await call_for('automation.turn_off', since)
        sent_only(sent, 'automation.curtains')
        answer(sent)
        if len(wide_in) > 2:
            since = len(calls)
            await self.tap(*control('automation.away'))
            sent = await call_for('automation.trigger', since)
            sent_only(sent, 'automation.away')
            answer(sent)
            if [c for c in calls[since:] if c.service != 'automation.trigger']:
                faults.append(f'the Run key also sent {[c.service for c in calls[since:]]}')
        since = len(calls)
        x1, y1, x2, y2 = wide['automation.doorbell']['box']
        await self.tap(x1 + (x2 - x1) // 3, (y1 + y2) // 2)
        sent = await call_for('automation.trigger', since)
        answer(sent)
        await asyncio.sleep(2)
        since = len(calls)
        await self.tap(*control('automation.doorbell'))
        sent = await call_for('automation.turn_on', since)
        answer(sent)
        self.failures += [f'automation: {f}' for f in faults]
        self.warnings.append(f'automation: tap/hold on a switching tile and a run button, running, off, unavailable; {len(calls)} calls')
        return 1

    async def drive(self):
        self.client = APIClient('127.0.0.1', self.item.port, None)
        for _ in range(240):
            if self.process.poll() is not None:
                raise RuntimeError(f'the program exited with {self.process.returncode}')
            try:
                await self.client.connect(login=True)
                break
            except Exception:
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError('the API never came up')
        entities, services = await self.client.list_entities_services()
        self.services = {s.name: s for s in services}
        self.inbox = next(e for e in entities if type(e).__name__ == 'TextInfo' and e.name == 'Tile settings')
        dark = next(e for e in entities if getattr(e, 'name', '') == 'Dark mode')
        self.dark_switch = dark
        self.swipe_switch = next(e for e in entities if getattr(e, 'name', '') == 'Swipe between pages')
        self.subscribe_logs()
        if 'render_skip_calibration' in self.services:
            await self.call('render_skip_calibration')
        await self.call('render_time', epoch=int(MOMENT.timestamp()))
        # The starting screen with its Tessera lockup, before any layout (firmware 0.3.8+).
        await self.render('starting')
        # Each step of it as the screen says it (firmware 0.38.0), from Wi-Fi to an update, then back as it was.
        if 'render_boot' in self.services:
            for name, given in BOOT_STATES:
                await self.call('render_boot', **{**BOOT_DEFAULTS, **given})
                await self.render(name)
            await self.call('render_boot', **{**BOOT_DEFAULTS, 'ha': -1})
        side = json.loads((REPO / 'screen_manager/app/boards.json').read_text())[self.item.board]['orientations']
        side = side['portrait' if self.item.rotation else 'landscape']
        grid = send_layout.Grid(side['columns'], side['rows'])
        record, values, bars, region = send_layout.configuration(grid, now=MOMENT, titles=PAGE_TITLES)
        self.sender = send_layout.api_sender(self.client, services)
        await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        tiles = len(values)
        end = time.monotonic() + 30
        while True:
            p = await self.probe()
            if p[3] == tiles and p[1] == 0:
                break
            if time.monotonic() > end:
                raise RuntimeError(f'the layout never arrived: {p}, {tiles} tiles expected')
            await asyncio.sleep(0.2)
        pages = p[5]
        self.canvas = (side['width'], side['height'])
        if self.only == 'alarm':
            return 1, await self.alarm_panel(grid)
        if self.only == 'lock':
            return 1, await self.lock_panel(grid)
        if self.only == 'automation':
            return 1, await self.automation_panel(grid)
        if self.only == 'remote':
            return 1, await self.remote_panel(grid)
        if self.only == 'bedside':
            return 1, await self.bedside_clock(grid)
        if self.only == 'media':
            return 1, await self.media_panel(grid)
        if self.only == 'saver':
            return 1, await self.saver_panel()
        if self.only == 'humidifier':
            return 1, await self.humidifier_panel(grid)
        checks = await self.self_test()
        await self.moments(pages)
        for page in range(pages):
            await self.call('render_page', page=page)
            await self.page_done(page)
            await self.render(f'page-{page + 1}')
        await self.call('render_page', page=0)
        await self.page_done(0)
        page1 = await self.render('_page-1', keep=False)
        for name, given in ALERTS:
            await self.alert(name, page1, **given)
        if 'camera' in json.loads((REPO / 'screen_manager/app/boards.json').read_text())[self.item.board]:
            await self.send({'v': 1, 'op': 'camera', 't': 'alert', 'e': 'camera.front_door', 'u': ''})
            await self.alert('alert-camera', page1, title='Someone is at the door', subtitle='Front door', icon='doorbell',
                             color='orange', button_text='Coming')
            await self.send({'v': 1, 'op': 'camera', 't': 'alert', 'e': 'camera.front_door', 'u': ''})
            await self.alert('alert-camera-choice', page1, title='Someone is at the door', subtitle='Front door', icon='doorbell',
                             button_text='Open', button_color='green', button2_text='Not now')
        self.client.switch_command(dark.key, True)
        end = time.monotonic() + 10
        while (await self.snapshot(self.out / '_dark.ppm')).tobytes() == page1.tobytes():
            if time.monotonic() > end:
                raise RuntimeError('Dark mode never changed the screen')
            await asyncio.sleep(0.2)
        (self.out / '_dark.ppm').unlink(missing_ok=True)
        await self.render('page-1-dark')
        self.client.switch_command(dark.key, False)
        await self.appearance_edits(grid)
        checks += await self.detail_navigation(grid, entities)
        checks += await self.rectangular_tiles(grid)
        checks += await self.bedside_clock(grid)
        checks += await self.alarm_panel(grid)
        return pages, checks

    async def run(self):
        self.out.mkdir(parents=True, exist_ok=True)
        for old in self.out.glob('*.png'):
            old.unlink()
        # The host keeps a screen's settings between runs; every run starts from the firmware's own defaults.
        (Path.home() / '.esphome' / 'prefs' / f'{self.item.name}.prefs').unlink(missing_ok=True)
        log = open(self.out / 'program.log', 'w')
        self.process = subprocess.Popen([str(self.build.program)], stdout=log, stderr=subprocess.STDOUT, cwd=self.build.work)
        try:
            pages, checks = await self.drive()
            return f'{pages} pages, {checks} page checks'
        finally:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            (self.out / 'log.txt').write_text('\n'.join(self.lines) + '\n')


def sheet(out, keys):
    """One picture of every variant's page 1, alerts and Dark mode side by side, for a look at a glance."""
    names = ['page-1', 'alert-plain', 'alert-long', 'alert-button', 'alert-camera', 'page-1-dark']
    rows = [(key, [out / key / f'{name}.png' for name in names]) for key in keys]
    cell, gap = 320, 12
    width = len(names) * (cell + gap) + gap
    heights = []
    for _, paths in rows:
        sizes = [Image.open(p).size for p in paths if p.exists()]
        heights.append(max((round(h * cell / w) for w, h in sizes), default=0))
    image = Image.new('RGB', (width, sum(h + 30 + gap for h in heights) + gap), (236, 236, 236))
    draw, y = ImageDraw.Draw(image), gap
    for (key, paths), height in zip(rows, heights):
        draw.text((gap, y), key, fill=(20, 20, 20))
        for i, path in enumerate(paths):
            if path.exists():
                with Image.open(path) as shot:
                    image.paste(shot.resize((cell, round(shot.height * cell / shot.width)), Image.LANCZOS), (gap + i * (cell + gap), y + 20))
        y += height + 30 + gap
    image.save(out / 'sheet.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('variants', nargs='*', help='variants to run (default: all of them)')
    parser.add_argument('--tree', type=Path, default=REPO, help='the source tree to build (default: this checkout)')
    parser.add_argument('--out', type=Path, default=REPO / '.esphome' / 'render' / 'out')
    parser.add_argument('--work', type=Path, help='where the host builds go (default: .esphome/render/build)')
    parser.add_argument('--camera', default='960x540', help='the camera picture of the camera alert, WxH')
    parser.add_argument('--only', choices=['alarm', 'lock', 'automation', 'remote', 'bedside', 'media', 'saver', 'humidifier'], help='after the demo layout arrives, run only this stage')
    parser.add_argument('--port-base', type=int, help='the first API port (default host.PORT_BASE); another worktree may use it')
    args = parser.parse_args()
    # The programs write their pictures from their own folder, so every path they get is absolute.
    args.out = args.out.resolve()
    if args.port_base:
        host.PORT_BASE = args.port_base
    items = [host.variant(key) for key in args.variants] or host.variants()
    busy = [str(item.port) for item in items if not free(item.port)]
    if busy:
        raise SystemExit(f'ports {", ".join(busy)} are in use; stop what listens there first')
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
    camera = tuple(int(n) for n in args.camera.split('x'))
    pictures = Pictures()
    results, failed = {}, []
    tree = args.tree.resolve()
    for item in items:
        build = host.Build(item, tree=tree, work=args.work, esphome=esphome)
        started = time.monotonic()
        ok, output = build.compile()
        if not ok:
            failed.append(item.key)
            results[item.key] = {'status': 'build failed', 'log': output[-3000:]}
            print(f'{item.key}: BUILD FAILED\n{output[-2000:]}', flush=True)
            continue
        built = time.monotonic()
        run = Run(build, args.out / item.key, pictures, camera, args.only)
        try:
            summary = asyncio.run(run.run())
        except Exception as error:  # a program that crashed or stopped answering
            run.failures.append(f'{type(error).__name__}: {error}')
            summary = 'stopped'
        status = 'FAIL' if run.failures else 'PASS'
        if run.failures:
            failed.append(item.key)
        results[item.key] = {'status': status, 'summary': summary, 'failures': run.failures, 'notes': run.warnings,
                             'build_s': round(built - started, 1), 'render_s': round(time.monotonic() - built, 1)}
        print(f'{item.key}: {status} ({summary}; build {built - started:.0f} s, render {time.monotonic() - built:.0f} s)', flush=True)
        for line in run.failures:
            print(f'  {line}', flush=True)
    rendered = [item.key for item in items if (args.out / item.key / 'page-1.png').exists()]
    if rendered:
        sheet(args.out, rendered)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'summary.json').write_text(json.dumps({'tree': str(tree), 'results': results}, indent=1) + '\n')
    last = f'{len(items) - len(failed)} of {len(items)} variants passed'
    (args.out / 'summary.txt').write_text(''.join(f"{key}: {result['status']} {result.get('summary', '')}\n"
                                                  + ''.join(f'  {line}\n' for line in result.get('failures', []))
                                                  for key, result in results.items()) + last + '\n')
    print(f'{last}; renders in {args.out}', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
