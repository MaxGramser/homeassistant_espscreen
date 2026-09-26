"""Expand local implementation includes for existing firmware source contracts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'components/smart_display'

def runtime_source():
    text = (ROOT / 'runtime_tiles.h').read_text()
    # The parser lives in its own compilation unit (page_receiver.cpp, firmware 0.3.3+); the source contracts read it
    # where runtime_tiles.h names its header.
    return text.replace('#include "page_receiver.h"', (ROOT / 'page_receiver.h').read_text() + (ROOT / 'page_receiver.cpp').read_text())
