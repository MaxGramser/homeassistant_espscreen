"""Expand local implementation includes for existing firmware source contracts."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'components/smart_display'

def runtime_source():
    text = (ROOT / 'runtime_tiles.h').read_text()
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
