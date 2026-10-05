"""The cases the screen (tile_memory::cost), the add-on (core.tile_cost) and the editor (memory.ts tileCost) must price
alike (firmware 0.34.0+, docs/TILE_MEMORY.md).

    python tests/memory_conformance.py      writes tests/fixtures/memory-conformance.json from core.tile_cost

tests/test_tile_memory.py checks the file still is what core.tile_cost answers; tests/test_tile_memory.cpp and
web/tests/memory.spec.ts check the firmware and the editor answer the same. The cases: every type of the catalogue and one
it does not know, on a board with PSRAM and on one without, with no choice of its own, with its own action, with its own
second line and with both; and a page with none to twelve entity items in its top bar. One case per line, so the C++ test reads it without a JSON library.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import catalogue  # noqa: E402
from core import page_cost, tile_cost  # noqa: E402

FIXTURE = ROOT / 'tests/fixtures/memory-conformance.json'
BOARDS = [{'psram': True, 'tile': 524, 'extra': 1056, 'page': 336}, {'psram': False, 'tile': 524, 'extra': 1056, 'page': 336},
          {'psram': False, 'tile': 600, 'extra': 1200, 'page': 624}]
CHOICES = [(False, False), (True, False), (False, True), (True, True)]


def cases():
    # A screen card with a price of its own (catalogue/screen.yaml `cards`) is named by its entity in `domain`.
    for domain in sorted(catalogue.TYPES) + ['nonsense'] + sorted(catalogue.CARD_MEMORY):
        for board in BOARDS:
            for action, line in CHOICES:
                options = {**({'tap': 'action'} if action else {}), **({'sub': 'attr:battery'} if line else {})}
                memory = {'room': 0, 'used': 0, **board}
                entity = domain if '.' in domain else f'{domain}.thing'
                yield {'domain': domain, 'action': action, 'line': line, **board,
                       'cost': tile_cost({'entity': entity, 'options': options}, memory)}
    # A page with a top bar of builtins and entity items: only the entity items keep a text.
    for board in BOARDS:
        for entities in (0, 1, 6, 12):
            trailing = [{'id': f'{n:016x}', 'type': 'clock'} for n in range(2)] + [
                {'id': f'{n + 2:016x}', 'type': 'entity', 'entity': f'sensor.s{n}'} for n in range(entities)]
            yield {'page_entities': entities, **board, 'cost': page_cost({'topbar': {'trailing': trailing}}, {'room': 0, 'used': 0, **board})}


def output():
    return '[\n' + ',\n'.join(json.dumps(case) for case in cases()) + '\n]\n'


if __name__ == '__main__':
    FIXTURE.write_text(output())
    print(f'wrote {FIXTURE.relative_to(ROOT)}')
