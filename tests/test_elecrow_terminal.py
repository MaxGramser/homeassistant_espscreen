"""Elecrow's parallel Terminal: catalog and actual RGB565 conversion contract."""
import json
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_pixel_words(tmp_path):
    compiler = shutil.which('c++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    binary = tmp_path / 'pixels'
    subprocess.run([compiler, '-std=c++17', '-I', str(ROOT),
                    str(ROOT / 'tests/test_ili9488_pixels.cpp'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_board_is_experimental_and_has_both_orientations():
    import yaml
    catalog = yaml.safe_load((ROOT / 'boards.yaml').read_text())
    assert catalog['elecrow-terminal-rgb']['status'] == 'experimental'
    shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
    shape = shapes['elecrow-terminal-rgb']
    assert (shape['width'], shape['height']) == (480, 320)
    assert (shape['columns'], shape['rows']) == (2, 2)
    assert shape['dimmable'] and shape['can_standby']
    assert shape['catalog']['touch'] == 'FT6236'
    # Entries must load the local component, including remotely installed firmware.
    for folder in ('checkout', 'packages'):
        entry = (ROOT / folder / 'elecrow-terminal-rgb.yaml').read_text()
        assert 'components: [ili9488_i80, smart_display]' in entry


def test_transport_chunks_stride_and_timeout(tmp_path):
    compiler = shutil.which('c++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    binary = tmp_path / 'transport'
    subprocess.run([compiler, '-std=c++17', '-I', str(ROOT / 'tests/fixtures/ili9488_i80'),
                    '-I', str(ROOT), str(ROOT / 'tests/test_ili9488_transport.cpp'),
                    str(ROOT / 'components/ili9488_i80/ili9488_i80.cpp'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
