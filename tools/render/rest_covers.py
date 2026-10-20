"""The Spotify tile while nothing plays, drawn by the real firmware on the host (tools/render/host.py), with the app's
own mosaic (screen_manager/app/rest_mosaic.py): a player's `cover` tile on 1x2 or 2x2 asks for its picture by the mark the
app sends at rest, and this script answers as the app does, from a folder of real or drawn covers.

    now        Spotify at rest without the mosaic: the tile as it was
    playing    for comparison: a player that plays, its cover over the card
    rest       Spotify at rest: the covers of "Liked songs", darkened as the screen asks (170 of 255)
    rest-t1/2  one and two turns later (ROTATE_SECONDS each): one cover, then another, moved on

    ESPHOME="uvx --python 3.13 --from esphome==2026.9.0 esphome" \\
      uv run --python 3.13 --with esphome==2026.9.0 python tools/render/rest_covers.py guition waveshare7 jc8012p4a1

Covers come from REST_COVERS (a folder with covers.json and its pictures, git-ignored); without it the drawn covers of
media_art stand in, as in every other render. The output goes to .esphome/rest-covers/out.
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
import core  # noqa: E402
import media_art  # noqa: E402
import media_library  # noqa: E402
import rest_mosaic  # noqa: E402
from camera_tiles import NEIGHBOURS as HOUSE  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

SPOTIFY = 'media_player.spotify'
KITCHEN = 'media_player.kitchen'
PLAYING_FEATURES = 444983
SPEAKERS = ['Bedroom', 'Kitchen', 'Living room']
# A song of each album, as Home Assistant's Spotify library names its items: a title and a thumbnail, no artist.
TRACKS = ['Get Lucky', 'Dreams', 'BIRDS OF A FEATHER', 'Weird Fishes/Arpeggi', 'Do I Wanna Know?', 'Espresso', 'luther',
          'Time (You and I)', 'cardigan', 'Blinding Lights', 'Green Light', 'CUFF IT', 'Teardrop', 'Rehab', 'Yellow']
LIKED = [5, 1, 9, 2, 8, 6, 10, 13, 3, 11, 4, 14, 12, 0]   # "Liked songs", newest first
NOW_PLAYING = 7
CONCEPTS = {
    'now': 'Spotify at rest, as it was',
    'playing': 'For comparison: a player that plays',
    'rest': 'Spotify at rest: its Liked songs',
    'rest-t1': 'A minute later: one cover moved on',
    'rest-t2': 'Two minutes later: another one',
}
TURNS = {'rest': 0, 'rest-t1': 1, 'rest-t2': 2}
SIZES = {'tall': '1x2', 'square': '2x2'}
# The house around the tile, enough to fill the ten-inch grid.
NEIGHBOURS = HOUSE + [
    ('light.demo_kitchen', 'Kitchen', {'state': 'on', 'attributes': {'brightness': 200}}),
    ('switch.demo_coffee', 'Coffee machine', {'state': 'off', 'attributes': {}}),
    ('sensor.demo_bedroom', 'Bedroom', {'state': '19.0', 'attributes': {'unit_of_measurement': '°C'}}),
    ('binary_sensor.demo_window', 'Window', {'state': 'on', 'attributes': {'device_class': 'window'}}),
    ('light.demo_reading', 'Reading lamp', {'state': 'off', 'attributes': {}}),
    ('sensor.demo_solar', 'Solar', {'state': '1.84', 'attributes': {'unit_of_measurement': 'kW'}}),
    ('switch.demo_fan', 'Fan', {'state': 'off', 'attributes': {}}),
    ('light.demo_porch', 'Porch', {'state': 'on', 'attributes': {'brightness': 90}}),
    ('sensor.demo_co2', 'CO2', {'state': '612', 'attributes': {'unit_of_measurement': 'ppm'}}),
    ('binary_sensor.demo_garage', 'Garage', {'state': 'off', 'attributes': {'device_class': 'garage_door'}}),
    ('light.demo_stairs', 'Stairs', {'state': 'off', 'attributes': {}}),
    ('sensor.demo_water', 'Water today', {'state': '142', 'attributes': {'unit_of_measurement': 'L'}}),
    ('switch.demo_tv', 'TV', {'state': 'on', 'attributes': {}}),
    ('sensor.demo_office', 'Office', {'state': '22.4', 'attributes': {'unit_of_measurement': '°C'}}),
]


def covers():
    """(picture bytes, album) per cover: the real covers of REST_COVERS, or media_art's drawn ones."""
    folder = os.environ.get('REST_COVERS')
    if folder:
        meta = json.loads((Path(folder) / 'covers.json').read_text())
        return [((Path(folder) / item['file']).read_bytes(), item['album']) for item in meta]
    return [(media_art.png(n), title) for n, (title, _) in enumerate(media_art.ALBUMS[:len(TRACKS)])]


class Study(run.Run):

    def answer(self, call):
        if call.service != 'esphome.screen_camera':
            return
        asked = run.asked(dict(call.data), self.screen)
        if asked is None:
            self.warnings.append(f'a question the add-on cannot read: {dict(call.data)}')
            return
        if asked.owner.kind != 'tile':
            return
        task = asyncio.get_running_loop().create_task(self.strip(asked))
        task.add_done_callback(lambda t: t.exception() and 'superseded' not in str(t.exception()) and self.warnings.append(f'answer failed: {t.exception()!r}'))

    async def strip(self, asked):
        """The page's pictures as the app answers them (picture_sources.Sources._tile_picture, picture_paint): each place
        filled, in the format the screen names first (8-bit colour), its own shade baked in. The covers at rest are drawn
        at their place's size, as Manager.rest_render draws them."""
        raws = [self.art.get(int(source.ref)) for source in asked.question.sources]
        if all(raw is None for raw in raws):
            # A player without a picture now: the add-on answers that it has none.
            async with self.turn:
                await self.reply(asked, '')
            return
        body, _ = run.painted(asked.question, raws)
        # What the firmware asked for (each place's size and shade) and what goes over the wire, beside the renders.
        self.asked = {'frames': [[place.w, place.h, place.shade] for place in asked.question.places], 'bytes': len(body)}
        self.served += 1
        url = self.pictures.url(f'{self.item.key}-rest-{self.served}.bmp', body)
        async with self.turn:
            await self.reply(asked, url)

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

    def page(self, concept, size, grid, shelf):
        """One page: the concept on the first cell, the house around it. Returns (tiles, art, mark)."""
        art = mark = None
        if concept == 'playing':
            tile = dict(entity=KITCHEN, name='Kitchen', slot=0, options={'display': 'cover', 'size': size})
            art = shelf[NOW_PLAYING][0]
        else:
            tile = dict(entity=SPOTIFY, name='Spotify', slot=0, options={'display': 'cover', 'size': size})
            if concept in TURNS:
                # As the app draws it (Manager.rest_render): the covers of this turn in the card's frame.
                step, pictures = TURNS[concept], [shelf[n][0] for n in LIKED]
                pool = [(f'https://i.scdn.co/image/{n}', TRACKS[n]) for n in LIKED]

                def art(width, height, step=step, pictures=pictures):
                    columns, lines, *_ = rest_mosaic.grid_of(width, height)
                    order = rest_mosaic.shown(len(pictures), columns * lines, step)
                    return rest_mosaic.draw([pictures[n] for n in order], width, height)
                mark = rest_mosaic.mark(pool, step)
        tiles = [tile]
        taken = set(grid.footprint(0, size))
        free = [cell for cell in range(grid.slots) if cell not in taken]
        for cell, (neighbour, label, _) in zip(free, NEIGHBOURS):
            tiles.append(dict(entity=neighbour, name=label, slot=cell))
        return tiles, art, mark

    async def drive(self):
        self.served, self.turn, self.art, self.asked = 0, asyncio.Lock(), {}, []
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
        region = dict(keepalive=120, clock_24h=True, numbers='point', group_min=1, percent_space=False)
        shelf = covers()
        rest = {'state': 'idle', 'attributes': {'friendly_name': 'Spotify', 'supported_features': media_library.SELECT_SOURCE,
                                                'source_list': SPEAKERS}}
        playing = {'state': 'playing', 'attributes': {
            'friendly_name': 'Kitchen', 'supported_features': PLAYING_FEATURES, 'source': 'Kitchen', 'volume_level': 0.35,
            'media_title': TRACKS[NOW_PLAYING], 'media_artist': 'Khruangbin', 'media_album_name': shelf[NOW_PLAYING][1],
            'media_duration': 254, 'media_position': 61, 'media_position_updated_at': run.MOMENT.isoformat(),
            'entity_picture': '/api/media_player_proxy/media_player.kitchen?token=x&cache=mordechai'}}
        states = {SPOTIFY: rest, KITCHEN: playing}
        for neighbour, _, state in NEIGHBOURS:
            states[neighbour] = state
        frames = {}
        rounds = [(size, concept) for size in SIZES for concept in CONCEPTS]
        for size, concept in rounds:
            tiles, art, mark = self.page(concept, size, grid, shelf)
            record = send_layout.migrate_legacy(dict(title='Music', tiles=tiles), grid)
            compiled = send_layout.compile_tiles(record['layout'], grid)
            self.art = {}
            values = []
            for index, tile in enumerate(compiled):
                value = send_layout.state_message(index, tile, states, core.extras(tile, states))
                if tile['entity'].startswith('media_player.'):
                    attributes = states[tile['entity']]['attributes']
                    value.setdefault('x', {}).update(media_library.player_extras(attributes, PLAYING_FEATURES, None, True))
                    value['x']['w'] = 'Playing' if states[tile['entity']]['state'] == 'playing' else 'Idle'
                    self.art[index] = art
                    if mark:
                        value['x']['pic'] = mark
                values.append(value)
            async with self.turn:
                await self.sender.synchronize(self.inbox.object_id, record, region, values, [[{'k': 'clock'}]])
            await self.call('render_page', page=0)
            await self.page_done(0)
            if art is not None:
                await self.picture(f'{size} {concept}')
                frames[f'{size}-{concept}'] = self.asked
            else:
                await asyncio.sleep(0.8)
            await self.render(f'{size}-{concept}')
        (self.out / 'frames.json').write_text(json.dumps(frames))
        return len(rounds), len(rounds)


def sheets(out, keys):
    """Per board: a row per size, the concepts in columns."""
    font = ImageFont.truetype(str(run.REPO / 'fonts/Roboto-500.ttf'), 24)
    small = ImageFont.truetype(str(run.REPO / 'fonts/Roboto-400.ttf'), 18)
    for key in keys:
        first = out / key / 'tall-now.png'
        if not first.exists():
            continue
        w, h = Image.open(first).size
        scale = 480 / max(w, h)
        cw, ch = round(w * scale), round(h * scale)
        sheet = Image.new('RGB', (len(CONCEPTS) * (cw + 20) + 20, len(SIZES) * (ch + 50) + 70), '#f5f6f8')
        draw = ImageDraw.Draw(sheet)
        draw.text((20, 16), f'{key} · {w} × {h}', font=font, fill='#17202c')
        for row, size in enumerate(SIZES):
            for col, concept in enumerate(CONCEPTS):
                path = out / key / f'{size}-{concept}.png'
                if not path.exists():
                    continue
                x, y = 20 + col * (cw + 20), 60 + row * (ch + 50)
                draw.text((x, y), f'{SIZES[size]} · {concept}', font=small, fill='#56616d')
                with Image.open(path) as shot:
                    sheet.paste(shot.resize((cw, ch), Image.Resampling.LANCZOS), (x, y + 26))
        sheet.save(out / f'sheet-{key}.png')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('variants', nargs='+')
    parser.add_argument('--out', type=Path, default=run.REPO / '.esphome' / 'rest-covers' / 'out')
    args = parser.parse_args()
    args.out = args.out.resolve()
    esphome = shlex.split(os.environ.get('ESPHOME', 'esphome'))
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
        study = Study(build, args.out / key, pictures, None)
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
