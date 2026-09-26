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
PROBE = re.compile(r'probe page=(-?\d+) applied=(-?\d+) shown=(\d+) tiles=(\d+) alert=(\d) pages=(\d+)')
HEADER = re.compile(r'state page=(-?\d+) name=\[(.*?)\] shown=\[(.*?)\] name_box=(-?\d+),(-?\d+),(-?\d+),(-?\d+)')
NAVIGATION = re.compile(r'navigation page=(-?\d+) footer=(\d) back=(\d) grid_height=(\d+) tile=(-?\d+),(-?\d+) prev=(-?\d+),(-?\d+) header=(-?\d+),(-?\d+)')
ALERT = re.compile(r'alert on=(\d) ' + ' '.join(f'{part}=(-?\\d+),(-?\\d+),(-?\\d+),(-?\\d+)'
                                              for part in ('card', 'frame', 'icon', 'title', 'subtitle', 'button', 'button2')))
# A page's own title (app 0.2.123): a long one among them, the kind that stood in dots after a page change (GitHub #27).
PAGE_TITLES = ['Demo cards', 'Living room downstairs', 'Kitchen']
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
        self.swipe_switch = next(e for e in entities if getattr(e, 'name', '') == 'Swipe between pages')
        self.subscribe_logs()
        if 'render_skip_calibration' in self.services:
            await self.call('render_skip_calibration')
        await self.call('render_time', epoch=int(MOMENT.timestamp()))
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
    parser.add_argument('--only', choices=['alarm'], help='after the demo layout arrives, run only this stage')
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
