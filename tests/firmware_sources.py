"""Expand local implementation includes for existing firmware source contracts."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'components/smart_display'

PART = re.compile(r'^\}  // namespace runtime_tiles\n#include "(\w+_lvgl\.h)"\nnamespace runtime_tiles \{$', re.M)
MORE = re.compile(r'^#include "(\w+_lvgl\.h)"$', re.M)


def parts():
    """The files runtime_tiles.h was split into (2026-11-16): each a section of it moved whole, included in its place."""
    return [name for name in MORE.findall((ROOT / 'runtime_tiles.h').read_text())
            if (ROOT / name).read_text().count('belongs to runtime_tiles.h') == 1]


def part_body(name):
    """A part as it stood in runtime_tiles.h: without its head and the namespace it is wrapped in."""
    text = (ROOT / name).read_text()
    start = text.index('namespace runtime_tiles {\n') + len('namespace runtime_tiles {\n')
    return text[start:text.rindex('}  // namespace runtime_tiles')]


def runtime_source():
    """runtime_tiles.h with its parts read in their place, so the text is the one translation unit the compiler sees and
    a contract that names two things in order finds them in the order they are compiled in."""
    text = (ROOT / 'runtime_tiles.h').read_text()
    names = set(parts())
    text = MORE.sub(lambda m: part_body(m.group(1)) if m.group(1) in names else m.group(0), text)
    # The parser lives in its own compilation unit (page_receiver.cpp, firmware 0.3.3+); the source contracts read it
    # where runtime_tiles.h names its header.
    # A player's library (media_library.cpp, firmware 0.24.0+) likewise, after the parser.
    return text.replace('#include "page_receiver.h"', (ROOT / 'page_receiver.h').read_text() + (ROOT / 'page_receiver.cpp').read_text()
                        + (ROOT / 'media_library.cpp').read_text() + (ROOT / 'tile_panel.cpp').read_text())


def firmware_domains():
    """The entity types the firmware takes as tiles: the list tile_catalogue.h holds (written from catalogue/*.yaml,
    app 0.4.32), which valid_entity in runtime_model.h walks."""
    assert 'for (const auto *allowed : tile_catalogue::DOMAINS)' in (ROOT / 'runtime_model.h').read_text()
    line = next(line for line in (ROOT / 'tile_catalogue.h').read_text().splitlines() if 'DOMAINS[] = {' in line)
    return set(re.findall(r'"([a-z_]+)"', line))
