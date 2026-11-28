"""Feature renders for the website and the release notes: the to-do card, calls between screens and the doorbell's Talk,
drawn by the real firmware as a host program (tools/render/host.py) and driven by the messages ESP Screens sends it.

    python3 tools/render/features.py [variants ...] [--pictures DIR] [--out DIR]

The variants default to jc8012p4a1 (lying, 1280 x 800) and reterminald1001-portrait (standing, 800 x 1280). No board
and no Home Assistant take part: the screen's questions are answered here as the add-on answers them.

- To-do: run.Run.todo_panel, the to-do round of the render harness, with the app's own todo_feed. Its tiles, the full
  list with open and done items, and the keyboard with half a word typed and a name offered.
- Calls: the op `call` (out, ring, live, end) and the op `contacts`, made by the app's own calls.py (Calls.contacts,
  contacts_messages, message), after a finger on the Call tile.
- Doorbell: the op `doorbell` with a door and a Talk link. The host has no microphone: talk_uplink.h stands one in under
  USE_HOST, set by the action render_talk, and the program is built with the audio caps of a board that plays and hears
  (HW_SPEAKER, HW_MICROPHONE), so the keys are the ones a P4 board shows.

Pictures: the screen asks for the picture of a video call and of a ring (esphome.screen_camera, a question); the answer is
painted by the add-on's picture_paint from `--pictures DIR`: caller.jpg (the other screen's camera) and door.jpg (the
doorbell's camera), drawn stand-ins when a file is missing. Before that, each picture is answered once in pure magenta to
find where it lands: <moment>.json beside the PNG holds every picture's rectangle on the glass (x, y, w, h, radius).
self.jpg is never asked for: a call shows no picture of the screen's own camera (module_call.cpp). This screen is the
Living room, the other one the Kitchen.

Each moment is rendered in the light look and the dark look; the dark one is kept only where it differs. The PNGs land in
.esphome/render/out/features/<variant>/.
"""
import argparse
import asyncio
import io
import json
import os
import shlex
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import host  # noqa: E402
import send_layout  # noqa: E402
import calls  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

VARIANTS = ('jc8012p4a1', 'reterminald1001-portrait')
MAGENTA = (255, 0, 255)
# The screen this one is (the Living room), and the others in the house as ESP Screens knows them (calls.Calls.contacts):
# two with video, one without a camera (sound only), one in a call, one offline; the Kitchen called and was missed.
HERE_NODE = 'living_room'
HOUSE = {
    'living_room': {'name': 'Living room', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': True},
    'kitchen': {'name': 'Kitchen', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': True},
    'hall': {'name': 'Hall', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': True},
    'bedroom': {'name': 'Bedroom', 'hears': True, 'speaks': True, 'films': False, 'shows': True, 'online': True},
    'office': {'name': 'Office', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': True},
    'garage': {'name': 'Garage', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': False},
    'study': {'name': 'Study', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': True, 'hidden': True},
}
# The ordinary tiles around the Call tile.
NEIGHBOURS = [
    ('light.ceiling', 'Ceiling', {'state': 'on', 'attributes': {'brightness': 190, 'color_mode': 'brightness', 'supported_color_modes': ['brightness']}}, {}),
    ('sensor.room_temperature', 'Temperature', {'state': '21.5', 'attributes': {'unit_of_measurement': '°C', 'device_class': 'temperature'}}, {}),
    ('light.kitchen', 'Kitchen', {'state': 'off', 'attributes': {'color_mode': 'brightness', 'supported_color_modes': ['brightness']}}, {}),
    ('switch.coffee_machine', 'Coffee machine', {'state': 'on', 'attributes': {}}, {}),
    ('binary_sensor.front_door', 'Front door', {'state': 'off', 'attributes': {'device_class': 'door'}}, {}),
    ('sensor.energy_today', 'Energy today', {'state': '7.4', 'attributes': {'unit_of_measurement': 'kWh', 'device_class': 'energy'}}, {}),
    ('light.hallway', 'Hallway', {'state': 'on', 'attributes': {'brightness': 120, 'color_mode': 'brightness', 'supported_color_modes': ['brightness']}}, {}),
    ('sensor.outside_humidity', 'Humidity', {'state': '64', 'attributes': {'unit_of_measurement': '%', 'device_class': 'humidity'}}, {}),
    ('switch.garden_lights', 'Garden lights', {'state': 'off', 'attributes': {}}, {}),
    ('binary_sensor.back_door', 'Back door', {'state': 'on', 'attributes': {'device_class': 'door'}}, {}),
    ('light.dining_table', 'Dining table', {'state': 'off', 'attributes': {'color_mode': 'brightness', 'supported_color_modes': ['brightness']}}, {}),
    ('sensor.power_now', 'Power now', {'state': '412', 'attributes': {'unit_of_measurement': 'W', 'device_class': 'power'}}, {}),
    ('light.bedroom', 'Bedroom', {'state': 'off', 'attributes': {'color_mode': 'brightness', 'supported_color_modes': ['brightness']}}, {}),
    ('switch.dishwasher', 'Dishwasher', {'state': 'on', 'attributes': {}}, {}),
]
TALK_LINK = 'http://127.0.0.1:9/camera/render/talk'


def stand_in(name, width=1280, height=720):
    """A drawn picture for a missing file: a calm gradient with a frame, so its place, crop and corners show."""
    image = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(image)
    top, bottom = ((70, 96, 120), (150, 170, 180)) if name == 'caller' else ((30, 42, 70), (120, 100, 90))
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    if name == 'caller':
        # A head and shoulders, roughly where a face sits in a video call.
        draw.ellipse([width * 0.42, height * 0.22, width * 0.58, height * 0.56], fill=(214, 182, 160))
        draw.ellipse([width * 0.30, height * 0.58, width * 0.70, height * 1.25], fill=(60, 80, 110))
    else:
        return run.porch(width, height)
    draw.rectangle([0, 0, width - 1, height - 1], outline=(255, 255, 255), width=4)
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=92)
    return out.getvalue()


def solid(colour, width=1280, height=720):
    out = io.BytesIO()
    Image.new('RGB', (width, height), colour).save(out, 'JPEG', quality=95)
    return out.getvalue()


def magenta_box(image):
    """(x, y, w, h) of the magenta in a render, or None."""
    rgb = image.convert('RGB')
    r, g, b = rgb.split()
    mask = Image.eval(r, lambda v: 255 if v > 200 else 0)
    mask = Image.composite(mask, Image.new('L', rgb.size, 0), Image.eval(g, lambda v: 255 if v < 70 else 0))
    mask = Image.composite(mask, Image.new('L', rgb.size, 0), Image.eval(b, lambda v: 255 if v > 200 else 0))
    box = mask.getbbox()
    return None if box is None else (box[0], box[1], box[2] - box[0], box[3] - box[1])


def home_states(now):
    """A house in the evening, every tile with the state Home Assistant would give it."""
    from datetime import timedelta
    dim = {'color_mode': 'brightness', 'supported_color_modes': ['brightness']}
    return {
        'weather.home': {'state': 'partlycloudy', 'attributes': {'temperature': 18.4, 'temperature_unit': '°C'}},
        'person.sam': {'state': 'home', 'attributes': {}},
        'person.alex': {'state': 'not_home', 'attributes': {}},
        'media_player.living_room': {'state': 'playing', 'attributes': {'volume_level': 0.42, 'is_volume_muted': False, 'media_title': 'Evening Drive',
                                                                       'media_artist': 'Nova Coast', 'media_album_name': 'Low Sun', 'supported_features': 8321599}},
        'media_player.kitchen': {'state': 'playing', 'attributes': {'volume_level': 0.32, 'is_volume_muted': False, 'media_title': 'Evening Drive',
                                                                   'media_artist': 'Nova Coast', 'supported_features': 8321599}},
        'climate.heating': {'state': 'heat', 'attributes': {'supported_features': 385, 'current_temperature': 20.5, 'temperature': 21.5, 'hvac_action': 'heating',
                                                            'hvac_modes': ['off', 'heat', 'cool', 'auto'], 'min_temp': 7, 'max_temp': 30, 'target_temp_step': 0.5}},
        'climate.hallway': {'state': 'heat', 'attributes': {'supported_features': 385, 'current_temperature': 20.5, 'temperature': 21.0, 'hvac_action': 'heating',
                                                            'hvac_modes': ['off', 'heat'], 'min_temp': 7, 'max_temp': 30, 'target_temp_step': 0.5}},
        'sensor.indoor_temperature': {'state': '21.4', 'attributes': {'unit_of_measurement': '°C', 'device_class': 'temperature'}},
        'sensor.energy_today': {'state': '6.84', 'attributes': {'unit_of_measurement': 'kWh', 'device_class': 'energy'}},
        'light.table_lamp': {'state': 'on', 'attributes': {'brightness': 191, **dim}},
        'light.ceiling': {'state': 'on', 'attributes': {'brightness': 150, **dim}},
        'light.porch': {'state': 'on', 'attributes': {'brightness': 199, **dim}},
        'light.kitchen': {'state': 'on', 'attributes': {'brightness': 230, **dim}},
        'lock.front_door': {'state': 'locked', 'attributes': {}},
        'vacuum.robot': {'state': 'docked', 'attributes': {'battery_level': 100, 'supported_features': 30524}},
        'alarm_control_panel.home': {'state': 'disarmed', 'attributes': {'code_arm_required': False, 'supported_features': 63}},
        'scene.movie_night': {'state': (now - timedelta(days=1, hours=-11, minutes=-7)).isoformat(), 'attributes': {}},
        'scene.good_night': {'state': (now - timedelta(days=1, hours=-13, minutes=-3)).isoformat(), 'attributes': {}},
        'cover.curtains': {'state': 'open', 'attributes': {'current_position': 70, 'device_class': 'curtain', 'supported_features': 15}},
        'switch.coffee': {'state': 'on', 'attributes': {}},
    }


# The home page around the to-do tile: (entity, name, column, row, options) per board shape (columns, rows). The to-do
# tile is the Shopping list in the middle of the page, two columns wide and as tall as shows most of its list.
HOME = {
    (5, 8): [
        ('screen.clock', '', 0, 0, {'display': 'analog', 'size': 'wide'}),
        ('weather.home', 'Outside', 2, 0, {'display': 'forecast', 'size': 'wide'}),
        ('person.sam', 'Sam', 4, 0, {}),
        ('media_player.living_room', 'Living room', 0, 1, {'size': 'square', 'controls': 'playback', 'icon': 'speaker'}),
        ('todo.shopping', 'Shopping list', 2, 1, {'size': '2x4'}),
        ('climate.heating', 'Heating', 4, 1, {'size': 'tall', 'controls': 'setpoint_mode', 'icon': 'radiator'}),
        ('sensor.indoor_temperature', 'Indoor', 0, 3, {'display': 'graph', 'size': 'wide', 'icon': 'thermometer'}),
        ('lock.front_door', 'Front door', 4, 3, {}),
        ('vacuum.robot', 'Robot', 0, 4, {'size': 'wide'}),
        ('light.porch', 'Porch light', 4, 4, {'icon': 'outdoor-lamp'}),
        ('sensor.energy_today', 'Energy', 0, 5, {'display': 'graph', 'size': 'wide', 'icon': 'flash'}),
        ('alarm_control_panel.home', 'Alarm', 2, 5, {}),
        ('scene.movie_night', 'Movie night', 3, 5, {'background': 'purple', 'icon': 'movie-open'}),
        ('scene.good_night', 'Good night', 4, 5, {'background': 'blue', 'icon': 'weather-night'}),
        ('climate.hallway', 'Hallway', 0, 6, {'size': 'wide', 'icon': 'radiator'}),
        ('cover.curtains', 'Curtains', 2, 6, {'size': 'wide', 'controls': 'position', 'icon': 'curtains'}),
        ('switch.coffee', 'Coffee', 4, 6, {'background': 'orange', 'icon': 'coffee-maker'}),
        ('media_player.kitchen', 'Kitchen', 0, 7, {'size': 'wide', 'controls': 'volume', 'icon': 'speaker'}),
        ('light.table_lamp', 'Table lamp', 2, 7, {'icon': 'lamp'}),
        ('person.alex', 'Alex', 3, 7, {}),
        ('screen.call', 'Call', 4, 7, {}),
    ],
    (2, 3): [
        ('todo.shopping', 'Shopping list', 0, 0, {'size': 'square'}),
        ('light.table_lamp', 'Table lamp', 0, 2, {'icon': 'lamp'}),
        ('sensor.indoor_temperature', 'Indoor', 1, 2, {'icon': 'thermometer'}),
    ],
    (3, 8): [
        ('screen.clock', '', 0, 0, {'display': 'analog', 'size': 'wide'}),
        ('person.sam', 'Sam', 2, 0, {}),
        ('weather.home', 'Outside', 0, 1, {'display': 'forecast', 'size': 'wide'}),
        ('light.porch', 'Porch light', 2, 1, {'icon': 'outdoor-lamp'}),
        ('todo.shopping', 'Shopping list', 0, 2, {'size': '2x3'}),
        ('climate.heating', 'Heating', 2, 2, {'size': 'tall', 'controls': 'setpoint_mode', 'icon': 'radiator'}),
        ('lock.front_door', 'Front door', 2, 4, {}),
        ('media_player.kitchen', 'Kitchen', 0, 5, {'size': 'wide', 'controls': 'volume', 'icon': 'speaker'}),
        ('switch.coffee', 'Coffee', 2, 5, {'background': 'orange', 'icon': 'coffee-maker'}),
        ('sensor.energy_today', 'Energy', 0, 6, {'display': 'graph', 'size': 'wide', 'icon': 'flash'}),
        ('scene.movie_night', 'Movie night', 2, 6, {'background': 'purple', 'icon': 'movie-open'}),
        ('cover.curtains', 'Curtains', 0, 7, {'size': 'wide', 'controls': 'position', 'icon': 'curtains'}),
        ('alarm_control_panel.home', 'Alarm', 2, 7, {}),
    ],
}


def highlighted(image, box, dark, radius=18):
    """The page with everything but `box` (x1, y1, x2, y2) faded towards the page, and a soft shadow under the card: the
    to-do tile stands out, the rest stays readable. A picture made from the render, not something the screen draws."""
    from PIL import ImageFilter
    page = (18, 18, 18) if dark else (232, 232, 232)
    faded = Image.blend(image, Image.new('RGB', image.size, page), 0.55)
    shadow = Image.new('L', image.size, 0)
    x1, y1, x2, y2 = box
    ImageDraw.Draw(shadow).rounded_rectangle([x1 - 4, y1 + 6, x2 + 4, y2 + 14], radius=28, fill=150 if not dark else 220)
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    faded = Image.composite(Image.new('RGB', image.size, (0, 0, 0)), faded, shadow.point(lambda v: v * 0.45))
    # The card itself as the screen drew it, its own rounded corners kept (the page's radius for a card, ui::px(16) at
    # this density, measured off the render).
    mask = Image.new('L', image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([x1, y1, x2 - 1, y2 - 1], radius=radius, fill=255)
    return Image.composite(image, faded, mask)


class Features(run.Run):
    """One variant's program, driven through the three features."""

    def __init__(self, build, out, pictures, given, only=None):
        super().__init__(build, out, pictures, (1280, 720), only)
        self.given = given          # {'caller': bytes, 'door': bytes}
        self.kept, self.unreached = [], []

    # ---- the program ----

    async def connect(self):
        self.client = run.APIClient('127.0.0.1', self.item.port, None)
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
        self.dark_switch = next(e for e in entities if getattr(e, 'name', '') == 'Dark mode')
        self.subscribe_logs()
        self.events = []
        self.client.subscribe_service_calls(self.events.append)
        if 'render_skip_calibration' in self.services:
            await self.call('render_skip_calibration')
        await self.call('render_time', epoch=int(run.MOMENT.timestamp()))
        side = json.loads((run.REPO / 'screen_manager/app/boards.json').read_text())[self.item.board]['orientations']
        side = side['portrait' if self.item.rotation else 'landscape']
        self.grid = send_layout.Grid(side['columns'], side['rows'])
        self.canvas = (side['width'], side['height'])
        self.sender = send_layout.api_sender(self.client, services)

    async def look(self, dark):
        self.client.switch_command(self.dark_switch.key, dark)
        await asyncio.sleep(1.5)

    async def keep(self, name, pictures=None):
        """The moment as <name>.png (and its pictures' rectangles as <name>.json); a dark one only where it differs."""
        image = await self.render(name)
        if name.endswith('-dark'):
            light = self.out / f'{name[:-5]}.png'
            if light.exists():
                with Image.open(light) as other:
                    if other.convert('RGB').tobytes() == image.tobytes():
                        (self.out / f'{name}.png').unlink()
                        return
        if pictures:
            (self.out / f'{name}.json').write_text(json.dumps({'size': list(self.canvas), 'pictures': pictures}, indent=1) + '\n')
        self.kept.append(name)

    # ---- the pictures ----

    async def question(self, since, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            found = self.unanswered(self.events, since)
            if found:
                call, read = found[-1]
                for each, _ in found:
                    each.data['_answered'] = '1'
                return read
            await asyncio.sleep(0.05)
        return None

    async def picture(self, source, name, open_view, close_view):
        """The view opened twice, its question answered as the add-on paints it: in magenta the first time, to find the
        picture on the glass (a view draws the first answer to a question), then with the picture itself. Returns the
        rectangle for the JSON, or None when no question came."""
        since = len(self.events)
        await open_view(0)
        read = await self.question(since)
        if read is None:
            self.unreached.append(f'{name}: the screen asked for no picture')
            return None
        body, question = run.painted(read.question, [solid(MAGENTA)], [{}])
        await self.reply(read, self.pictures.url(f'{self.item.key}-{name}-magenta.bmp', body))
        await asyncio.sleep(1.2)
        box = magenta_box(await self.render(f'_{name}-magenta', keep=False))
        await close_view()
        since = len(self.events)
        await open_view(1)
        read = await self.question(since)
        if read is None:
            self.unreached.append(f'{name}: the screen asked for no picture the second time')
            return None
        body, _ = run.painted(read.question, [self.given[source]], [{}])
        await self.reply(read, self.pictures.url(f'{self.item.key}-{name}.bmp', body))
        await asyncio.sleep(1.2)
        if box is None:
            self.unreached.append(f'{name}: the magenta answer never showed, no rectangle')
            return None
        return {'source': f'{source}.jpg', 'x': box[0], 'y': box[1], 'w': box[2], 'h': box[3], 'radius': question.places[0].radius}

    # ---- the layout ----

    async def page(self, tiles, states):
        spans = {'wide': (2, 1), 'tall': (1, 2), 'square': (2, 2)}
        grid, taken = self.grid, set()
        placed = []
        for tile in tiles:
            w, h = spans.get(tile.get('options', {}).get('size'), (1, 1))
            w, h = min(w, grid.columns), min(h, grid.rows)
            for slot in range(grid.slots):
                row, col = divmod(slot, grid.columns)
                cells = {(row + r, col + c) for r in range(h) for c in range(w)}
                if col + w <= grid.columns and row + h <= grid.rows and not cells & taken:
                    taken |= cells
                    placed.append({**tile, 'slot': slot})
                    break
        record = send_layout.migrate_legacy(dict(title='Living room', tiles=placed), grid)
        compiled = send_layout.compile_tiles(record['layout'], grid)
        values = [send_layout.state_message(i, tile, states) for i, tile in enumerate(compiled)]
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        await self.call('render_page', page=0)
        await self.page_done(0)
        await asyncio.sleep(1.0)

    def call_page(self):
        """The Call tile among ordinary tiles: a page as full as the glass holds, the Call tile in its middle."""
        cells = self.grid.slots
        tiles, states = [], {}
        others = iter(NEIGHBOURS)
        middle = (self.grid.rows // 2) * self.grid.columns + self.grid.columns // 2
        count = 0
        while count < cells:
            if count == middle:
                tiles.append(dict(entity=calls.TILE, name='Call', options={}))
                count += 1
                continue
            try:
                entity, name, state, options = next(others)
            except StopIteration:
                break
            tiles.append(dict(entity=entity, name=name, options=options))
            states[entity] = {**state, 'attributes': {'friendly_name': name, **state['attributes']}}
            count += 1
        return tiles, states

    # ---- the moments ----

    async def todo(self):
        """run.Run.todo_panel into a folder of its own; its moments that show the card are kept under their names here."""
        work = self.out / '_todo'
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        out, self.out = self.out, work
        try:
            await self.todo_panel(self.grid)
        finally:
            self.out = out
        chosen = {'todo-sizes': 'todo-tiles', 'todo-sizes-dark': 'todo-tiles-dark', 'todo-card': 'todo-list',
                  'todo-card-dark': 'todo-list-dark', 'todo-typed': 'todo-keyboard', 'todo-added': 'todo-added'}
        for source, name in chosen.items():
            if (work / f'{source}.png').exists():
                shutil.copy(work / f'{source}.png', self.out / f'{name}.png')
                self.kept.append(name)
            else:
                self.unreached.append(f'todo: {source} was not rendered')
        if (self.out / 'todo-keyboard.png').exists():
            self.unreached.append('todo: the keyboard is rendered in the light look only (the to-do round types once)')
        await self.call('render_close_cards')
        await asyncio.sleep(0.8)

    async def todo_home(self):
        """The Shopping list as a 2 x 2 tile among a full page of a house, as on a wall, and once more with the rest faded."""
        import todo_feed
        from core import extras, state_message
        # A wall's page as people make it: five columns and eight rows lying, three by eight standing (the layout says
        # its grid, the screen places it); a square glass keeps its own grid.
        width, height = self.canvas
        grid = send_layout.Grid(5, 8) if width > height else send_layout.Grid(3, 8) if height > width else self.grid
        shape = (grid.columns, grid.rows)
        if shape not in HOME:
            self.unreached.append(f'todo-home: no home page for a {shape[0]} x {shape[1]} grid')
            return
        tz = run.MOMENT.tzinfo
        items = [{'uid': f's{n}', 'summary': name, 'status': 'needs_action', 'due': None}
                 for n, name in enumerate(('Oat milk', 'Bananas', 'Coffee beans', 'Tomatoes', 'Dishwasher tablets', 'Olive oil', 'Sourdough bread'))]
        items += [{'uid': f'd{n}', 'summary': name, 'status': 'completed', 'due': None} for n, name in enumerate(('Butter', 'Apples'))]
        numbers = todo_feed.Numbers()
        numbers.update('todo.shopping', items)
        states = home_states(run.MOMENT)
        states['todo.shopping'] = {'state': str(sum(not todo_feed.done(i) for i in items)), 'attributes': {'supported_features': 127}}
        for entity, name, *_ in HOME[shape]:
            if entity in states:
                states[entity]['attributes'].setdefault('friendly_name', name)
        tiles = [dict(entity=entity, name=name, slot=row * shape[0] + column, options=options)
                 for entity, name, column, row, options in HOME[shape]]
        record = send_layout.migrate_legacy(dict(title='Living room', tiles=tiles), grid)
        compiled = send_layout.compile_tiles(record['layout'], grid)
        forecast = send_layout.demo_forecast(run.MOMENT)
        values = []
        for i, tile in enumerate(compiled):
            weather = tile['entity'].startswith('weather.')
            extra = extras(tile, states, forecast if weather else None, None, send_layout.demo_hourly(run.MOMENT) if weather else None,
                           run.MOMENT, week=True) or {}
            if tile['entity'] == 'todo.shopping':
                extra = {**extra, 'todo': todo_feed.card(tile, items, numbers.of('todo.shopping'), 127, tz, run.MOMENT)}
            message = state_message(i, tile, states, extra, week=True)
            if tile['entity'] == 'sensor.indoor_temperature':
                message['history'] = {'hours': 24, 'values': [round(21 + 1.6 * __import__('math').sin(k / 3.2) - 0.05 * k, 2) for k in range(24)]}
            if tile['entity'] == 'sensor.energy_today':
                message['history'] = {'hours': 24, 'values': [round(0.12 * k + 0.04 * (k % 5), 2) for k in range(24)]}
            values.append(message)
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
        await self.sender.synchronize(self.inbox.object_id, record, region, values, bars)
        await self.call('render_page', page=0)
        await self.page_done(0)
        for dark in (False, True):
            suffix = '-dark' if dark else ''
            await self.look(dark)
            await asyncio.sleep(1.0)
            await self.keep('todo-home' + suffix)
            start = len(self.lines)
            await self.call('render_cards')
            line = await self.until(lambda l: 'cards ' in l, 10, 'render_cards', start)
            box = None
            for card in line.split('cards ', 1)[1].split(';'):
                if card.startswith('todo.shopping|'):
                    box = tuple(int(n) for n in card.rsplit('|', 1)[1].split(','))
            if box is None:
                self.unreached.append('todo-home: the to-do tile was not on the page')
                continue
            with Image.open(self.out / f'todo-home{suffix}.png') as shot:
                highlighted(shot.convert('RGB'), (box[0], box[1], box[2] + 1, box[3] + 1), dark).save(self.out / f'todo-home-highlight{suffix}.png')
            self.kept.append('todo-home-highlight' + suffix)
        await self.look(False)

    async def send_call(self, say, **said):
        await self.send(calls.message(say, **said))
        await asyncio.sleep(0.8)

    async def wait_line(self, words, start, timeout=10, what=''):
        try:
            await self.until(lambda line: words in line, timeout, what or words, start)
            return True
        except RuntimeError:
            return False

    async def calls_round(self, suffix):
        tiles, states = self.call_page()
        await self.page(tiles, states)
        await self.keep('call-page' + suffix)
        # A finger on the Call tile opens the list, and the screen asks ESP Screens for it.
        spots = await self.slots()
        if calls.TILE not in spots:
            raise RuntimeError(f'the Call tile is not on the page: {spots}')
        start = len(self.lines)
        await self.tap(*spots[calls.TILE])
        # The tap says "list" to ESP Screens (module_call.cpp, say); the host leaves out the report's binding (audio), so
        # the log line is what shows it.
        if not await self.wait_line('the tile: the list', start, 5):
            self.unreached.append(f'calls{suffix}: a tap on the Call tile did not open the list')
        # The list as the app makes it: the house, the Office in a call, the Kitchen's call missed here.
        book = calls.Calls()
        book.dial('office', 'study', True, 0)
        book.missed[HERE_NODE] = {'from': 'kitchen', 'at': int(run.MOMENT.timestamp()) - 600, 'video': True}
        house = {node: facts for node, facts in HOUSE.items() if not facts.get('hidden') or node == HERE_NODE}
        rows = book.contacts(HERE_NODE, house)
        for part in calls.contacts_messages(rows):
            await self.send(part)
        await self.wait_line('the list:', start, what='the list drawn')
        await asyncio.sleep(0.6)
        await self.keep('call-list' + suffix)
        # A call coming in (it closes the list), answered: the video call; hung up; a call going out; a call with sound
        # alone; a call nobody answered.
        await self.send_call(calls.Say(HERE_NODE, 'k1', calls.RING, 'kitchen', True), name='Kitchen')
        await self.keep('call-ring' + suffix)
        async def answered(n):
            await self.send_call(calls.Say(HERE_NODE, f'k1{n}', calls.LIVE, 'kitchen', True), name='Kitchen')

        async def hung_up():
            await self.send_call(calls.Say(HERE_NODE, 'k10', calls.END, 'kitchen', True, calls.HUNG_UP), name='Kitchen')
        box = await self.picture('caller', 'call-video' + suffix, answered, hung_up)
        # The timer counts from the answer: a few seconds in, as a call looks while it goes.
        await asyncio.sleep(6)
        await self.keep('call-video' + suffix, [box] if box else None)
        await self.send_call(calls.Say(HERE_NODE, 'k11', calls.END, 'kitchen', True, calls.HUNG_UP), name='Kitchen')
        await self.send_call(calls.Say(HERE_NODE, 'k2', calls.OUT, 'kitchen', True), name='Kitchen')
        await self.keep('call-out' + suffix)
        await self.send_call(calls.Say(HERE_NODE, 'k2', calls.END, 'kitchen', True, calls.HUNG_UP), name='Kitchen')
        await self.send_call(calls.Say(HERE_NODE, 'k3', calls.RING, 'bedroom', False), name='Bedroom')
        since = len(self.events)
        await self.send_call(calls.Say(HERE_NODE, 'k3', calls.LIVE, 'bedroom', False), name='Bedroom', peer_camera=False)
        await asyncio.sleep(4)
        for call, _ in self.unanswered(self.events, since):
            call.data['_answered'] = '1'  # a call with sound alone shows no picture: its little room is not answered
        await self.keep('call-sound' + suffix)
        await self.send_call(calls.Say(HERE_NODE, 'k3', calls.END, 'bedroom', False, calls.HUNG_UP), name='Bedroom')
        await self.send_call(calls.Say(HERE_NODE, 'k4', calls.RING, 'kitchen', True), name='Kitchen')
        await self.send_call(calls.Say(HERE_NODE, 'k4', calls.END, 'kitchen', True, calls.MISSED), name='Kitchen')
        await self.keep('call-missed' + suffix)
        await asyncio.sleep(3)  # the end card goes by itself (END_SHOWN_MS)

    async def doorbell_round(self, suffix):
        await self.call('render_talk', present=True, state=0, bar=0.0)
        tiles, states = self.call_page()
        await self.page(tiles, states)
        await asyncio.sleep(1.0)
        rang = int(run.MOMENT.timestamp()) - 20
        ring = {}

        async def ring_opens(n):
            ring.clear()
            ring.update({'v': 1, 'op': 'doorbell', 'e': 'camera.front_door', 'n': 'Front door', 'k': f'ring{n}{suffix or "-light"}',
                         'r': rang, 'd': 1, 'ds': 'locked', 'tk': TALK_LINK})
            start = len(self.lines)
            await self.send(dict(ring))
            if not await self.wait_line('for a ring', start, what='doorbell: the view'):
                self.unreached.append(f'doorbell{suffix}: the view never opened')

        async def ring_closes():
            await self.send({'v': 1, 'op': 'doorbell', 'k': ring['k'], 'c': 1})
            await asyncio.sleep(1.5)
        box = await self.picture('door', 'doorbell-ring' + suffix, ring_opens, ring_closes)
        pictures = [box] if box else None
        await self.keep('doorbell-ring' + suffix, pictures)
        # Talk, as a finger turns it on: on its way, then talking with the voice's bars.
        await self.call('render_talk_key')
        await asyncio.sleep(0.5)
        await self.keep('doorbell-connecting' + suffix, pictures)
        await self.call('render_talk', present=True, state=2, bar=0.72)
        await asyncio.sleep(1.0)
        await self.keep('doorbell-talking' + suffix, pictures)
        await self.call('render_talk_key')
        await self.send({'v': 1, 'op': 'doorbell', 'k': ring['k'], 'c': 1})
        await asyncio.sleep(1.5)
        await self.call('render_talk', present=False, state=0, bar=0.0)

    async def drive(self):
        await self.connect()
        tiles, states = self.call_page()
        await self.page(tiles, states)
        await self.todo()
        await self.todo_home()
        if self.only == 'todo':
            return len(self.kept)
        for dark in (False, True):
            suffix = '-dark' if dark else ''
            await self.look(dark)
            await self.calls_round(suffix)
            await self.doorbell_round(suffix)
        await self.look(False)
        return len(self.kept)

    async def run(self):
        self.out.mkdir(parents=True, exist_ok=True)
        for old in list(self.out.glob('*.png')) + list(self.out.glob('*.json')):
            old.unlink()
        (Path.home() / '.esphome' / 'prefs' / f'{self.item.name}.prefs').unlink(missing_ok=True)
        log = open(self.out / 'program.log', 'w')
        self.process = run.subprocess.Popen([str(self.build.program)], stdout=log, stderr=run.subprocess.STDOUT, cwd=self.build.work)
        try:
            return await self.drive()
        finally:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.process.terminate()
            try:
                self.process.wait(5)
            except run.subprocess.TimeoutExpired:
                self.process.kill()
            (self.out / 'log.txt').write_text('\n'.join(self.lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('variants', nargs='*', default=list(VARIANTS))
    parser.add_argument('--pictures', type=Path, help='caller.jpg and door.jpg (1280 x 720); drawn stand-ins for a missing one')
    parser.add_argument('--out', type=Path, default=run.REPO / '.esphome' / 'render' / 'out' / 'features')
    parser.add_argument('--work', type=Path, default=run.REPO / '.esphome' / 'render' / 'features-build',
                        help='its own host builds: they carry the audio caps, a plain render does not')
    parser.add_argument('--skip-build', action='store_true', help='run the programs already built')
    parser.add_argument('--only', choices=['todo'], help='the to-do moments alone (a board without calls, the 4-inch Guition)')
    args = parser.parse_args()
    args.out = args.out.resolve()
    given = {}
    for name in ('caller', 'door'):
        path = args.pictures / f'{name}.jpg' if args.pictures else None
        given[name] = path.read_bytes() if path and path.is_file() else stand_in(name)
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
    pictures = run.Pictures()
    report = {}
    for key in args.variants:
        item = host.variant(key)
        build = host.Build(item, tree=run.REPO, work=args.work, esphome=esphome, defines=('HW_SPEAKER', 'HW_MICROPHONE'))
        started = time.monotonic()
        if not args.skip_build:
            ok, output = build.compile()
            if not ok:
                print(f'{key}: BUILD FAILED\n{output[-3000:]}', flush=True)
                report[key] = {'status': 'build failed'}
                continue
        features = Features(build, args.out / key, pictures, given, args.only)
        try:
            kept = asyncio.run(features.run())
            status = 'done'
        except Exception as error:
            kept, status = len(features.kept), f'stopped: {type(error).__name__}: {error}'
        shutil.rmtree(args.out / key / '_todo', ignore_errors=True)
        report[key] = {'status': status, 'kept': features.kept, 'not reached': features.unreached,
                       'notes': features.warnings + features.failures, 'seconds': round(time.monotonic() - started)}
        print(f'{key}: {status}, {kept} pictures ({time.monotonic() - started:.0f} s)', flush=True)
        for line in features.unreached + features.failures:
            print(f'  {line}', flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print(args.out, flush=True)


if __name__ == '__main__':
    main()
