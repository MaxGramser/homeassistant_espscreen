"""What a tile of an entity keeps in the memory inside a screen's chip, estimated without a screen (docs/TILE_MEMORY.md).

    python tools/estimate_tile_memory.py                     every type, from tools/tile_memory_examples.json
    python tools/estimate_tile_memory.py light               one type
    python tools/estimate_tile_memory.py --state state.json  an entity of your own: {"entity", "state", "attributes"}
                                                             (and "forecast"/"hourly" for a weather entity, "events"
                                                             for a calendar: Home Assistant's calendar.get_events,
                                                             "items" for a to-do list: its todo/item/subscribe)

The add-on's own code builds the state message of the tile (Manager.tile_message with a stand-in Home Assistant), and a
model of the firmware's storage prices what the screen keeps of it on a board with PSRAM, which is what a type's `memory:
bytes` in the catalogue means: a text of more than 15 bytes is a block of its length (the shorter ones live inside the
string), a list is a block of its elements, and every block carries the heap's overhead. The model's constants come from
the bench measurements (`MODEL`), and tests/test_tile_memory.py holds every catalogue price to its estimate, so a firmware
that starts keeping more cannot leave the price behind. A new type needs only an example state here and its estimate in
its catalogue file; the bench measures it once more when one is at hand.
"""
import argparse
import asyncio
import json
import math
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
EXAMPLES = ROOT / 'tools/tile_memory_examples.json'

# The firmware's storage, as the bench measured it (2026-10-03, docs/TILE_MEMORY.md "Measuring a price"): std::string keeps
# up to 15 bytes inside itself (libstdc++ on the ESP32, S3 and P4); a block costs its size rounded to four bytes and the
# heap's own `block` bytes; an element of a list costs its slot (`slot` for a text, `number` for a number, `record` for a
# record such as a day of a forecast, `choice` for a row of a vacuum's choices: four texts and two lists); `tile` is what
# every tile keeps besides its message's texts.
MODEL = {'inline': 15, 'block': 10, 'slot': 24, 'number': 4, 'record': 64, 'choice': 124, 'tile': 0}
# What the firmware reads of a state message, read from its own source, so the estimate follows the firmware: the
# attributes (`a`) and extras (`x`) it takes, the longest text it keeps of each (string(..., N)), and the lists it keeps as
# one text (list(...): a thermostat's modes). Anything else in a message reaches the screen and is gone with the message.
RECEIVER = (ROOT / 'components/smart_display/page_receiver.cpp').read_text()
READS = {'a': set(re.findall(r'\ba\["(\w+)"\]', RECEIVER)),
         # A vacuum's rows are read by name through choice("mode", ...), the rest of the extras by extra["name"].
         'x': set(re.findall(r'\bextra\["(\w+)"\]', RECEIVER)) | set(re.findall(r'\bchoice\("(\w+)"', RECEIVER))}
# A vacuum's rows, each a Choice in a list of its own (runtime_model.h).
CHOICES = set(re.findall(r'\bchoice\("(\w+)"', RECEIVER))
CAPS = {key: int(n) for key, n in re.findall(r'string\((?:a|extra)\["(\w+)"\],\s*(\d+)\)', RECEIVER)}
JOINED = set(re.findall(r'list\(a\["(\w+)"\]\)', RECEIVER))
# The longest text and the most items the firmware keeps where its source names no number of its own.
TEXT_MOST, LIST_MOST = 160, 16
# A text's state (text, input_text) is kept whole on a board with its field (tile_controls.h TEXT_BYTES, module text_edit).
TEXT_STATE_MOST = int(re.search(r'TEXT_BYTES = (\d+);', (ROOT / 'components/smart_display/tile_controls.h').read_text())[1])
TEXT_DOMAINS = ('text.', 'input_text.')


def text(value, model=MODEL, most=TEXT_MOST):
    size = min(len(value.encode()), most)
    return 0 if size <= model['inline'] else 4 * math.ceil((size + 1) / 4) + model['block']


def kept(value, model=MODEL, most=TEXT_MOST):
    """The bytes the screen keeps of one value it reads."""
    if isinstance(value, str):
        return text(value, model, most)
    if isinstance(value, dict):
        return sum(kept(v, model) for v in value.values())
    if isinstance(value, list):
        value = value[:LIST_MOST]
        if not value:
            return 0
        if isinstance(value[0], (int, float)):
            return 0  # a colour or a position: the firmware keeps its numbers in fields of their own
        slot = model['slot'] if isinstance(value[0], str) else model['record']
        # The firmware fills its lists one item at a time (push_back), and a std::vector doubles its room as it grows: six
        # items hold the room of eight.
        room = 1 << (len(value) - 1).bit_length()
        return 4 * math.ceil(room * slot / 4) + model['block'] + sum(kept(v, model, 48) for v in value if not isinstance(v, (int, float)))
    return 0


def price(message, model=MODEL):
    """What one tile keeps of its state message, by the model: its entity, name and state, the attributes and extras the
    firmware reads, and a sensor's history."""
    total = model['tile'] + sum(text(message.get(key) or '', model) for key in ('entity', 'name'))
    total += text(message.get('state') or '', model, TEXT_STATE_MOST if str(message.get('entity', '')).startswith(TEXT_DOMAINS) else TEXT_MOST)
    for part in ('a', 'x'):
        for key, value in (message.get(part) or {}).items():
            if key not in READS[part]:
                continue
            if key in JOINED and isinstance(value, list):
                total += text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), model, 512)
            elif part == 'x' and key in CHOICES and isinstance(value, dict):
                # A row's values, and its labels: the values again where the row brings none.
                total += kept(value, model) + (kept(value['o'], model, 24) if 'o' in value and 'l' not in value else 0)
            else:
                total += kept(value, model, CAPS.get(key, TEXT_MOST))
    rows = sum(1 for key in CHOICES if isinstance((message.get('x') or {}).get(key), dict))
    if rows:
        total += 4 * math.ceil((1 << (rows - 1).bit_length()) * model['choice'] / 4) + model['block']
    # A sensor's history is made at once (assign: 24 numbers), so it holds no more room than its numbers.
    if (message.get('history') or {}).get('values'):
        total += 4 * math.ceil(24 * model['number'] / 4) + model['block']
    return total


def from_now(entries):
    """A forecast as an example holds it, moved to start just after now: the add-on leaves out the days and hours that are
    past, so a forecast with fixed dates would price lower every hour (CI, 2026-10-03). The spacing stays as it was."""
    from datetime import datetime, timedelta, timezone
    stamps = [datetime.fromisoformat(e['datetime']) for e in entries if isinstance(e, dict) and e.get('datetime')]
    if not stamps:
        return entries
    shift = datetime.now(timezone.utc) + timedelta(minutes=5) - min(stamps)
    return [{**e, 'datetime': (datetime.fromisoformat(e['datetime']) + shift).isoformat()} if isinstance(e, dict) and e.get('datetime') else e
            for e in entries]


def this_week(entries):
    """Calendar events as an example holds them, moved by whole days so the first starts today: the add-on keeps only the
    days around now, so fixed dates would price lower every week."""
    from datetime import date, datetime, timedelta
    days = [date.fromisoformat(str(e.get('start', ''))[:10]) for e in entries if isinstance(e, dict) and e.get('start')]
    if not days:
        return entries
    shift = date.today() - min(days)

    def moved(value):
        if not isinstance(value, str) or not value:
            return value
        if len(value) == 10:
            return (date.fromisoformat(value) + shift).isoformat()
        return (datetime.fromisoformat(value) + shift).isoformat()
    return [{**e, 'start': moved(e.get('start')), 'end': moved(e.get('end'))} for e in entries]


async def messages(examples):
    """The state message the add-on builds for each example, as a screen running the newest firmware gets it."""
    import test_scaling
    from manager_fixtures import with_screen_grid
    from server import Manager
    ha = test_scaling.fake_ha(firmware='0.34.0')
    forecasts = {}
    for example in examples:
        ha.registry.append({'entity_id': example['entity'], 'platform': 'demo'})
        ha.states[example['entity']] = {'state': example['state'], 'attributes': example.get('attributes', {})}
        forecasts[(example['entity'], 'daily')] = from_now(example.get('forecast', []))
        forecasts[(example['entity'], 'hourly')] = from_now(example.get('hourly', []))

    async def forecast(entity, kind='daily'):
        return forecasts.get((entity, kind), [])
    ha.forecast = forecast
    # A calendar's events (firmware 0.56.0), moved to this week as the add-on would fetch them.
    calendars = {example['entity']: example['events'] for example in examples if example.get('events')}

    async def events(entities, start, end):
        return {entity: this_week(calendars.get(entity, [])) for entity in entities}
    ha.events = events
    with tempfile.TemporaryDirectory() as folder:
        manager = Manager(with_screen_grid(ha), Path(folder) / 'screens.json')
        out = []
        # A to-do list's items, as Home Assistant's todo/item/subscribe sends them.
        for example in examples:
            if example.get('items'):
                manager.todos.received(example['entity'], {'items': example['items']})
        for example in examples:
            if example['entity'].startswith('sensor.'):
                manager.histories[(example['entity'], 24)] = (0, [round(20 + n / 10, 1) for n in range(24)])
            out.append(await manager.tile_message(0, {'entity': example['entity'], 'name': '', 'options': {}}, lamps=True))
        return out


def estimates(examples):
    """{domain: bytes} for examples given as {domain: example or [examples]}: the mean over a type's examples, as a layout
    of many tiles cycling through them keeps."""
    flat = [(domain, example) for domain, value in examples.items() for example in (value if isinstance(value, list) else [value])]
    built = asyncio.run(messages([example for _, example in flat]))
    sums = {}
    for (domain, _), message in zip(flat, built):
        sums.setdefault(domain, []).append(price(message))
    return {domain: round(sum(values) / len(values)) for domain, values in sums.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('domains', nargs='*')
    parser.add_argument('--state', type=Path)
    parser.add_argument('--examples', type=Path, default=EXAMPLES)
    args = parser.parse_args()
    if args.state:
        example = json.loads(args.state.read_text())
        examples = {example['entity'].split('.')[0]: example}
    else:
        examples = json.loads(args.examples.read_text())
        if args.domains:
            examples = {d: examples[d] for d in args.domains}
    import catalogue
    for domain, estimate in sorted(estimates(examples).items()):
        stated = catalogue.MEMORY.get(domain, {}).get('bytes')
        print(f'{domain:22} {estimate:6} B estimated' + (f', the catalogue says {stated} B' if stated is not None else ''))


if __name__ == '__main__':
    main()
