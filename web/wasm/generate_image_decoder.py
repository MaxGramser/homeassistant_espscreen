"""Compile ESPHome's BMP decoder unchanged apart from platform includes."""
from pathlib import Path
import re
import esphome

ROOT = Path(__file__).resolve().parents[2]
source = Path(esphome.__file__).parent / 'components/runtime_image'
out = ROOT / 'web/wasm/generated/image'
out.mkdir(parents=True, exist_ok=True)
for name in ('bmp_decoder.h', 'bmp_decoder.cpp', 'image_decoder.h', 'image_decoder.cpp', 'image_format.h'):
    text = (source / name).read_text()
    text = re.sub(r'^#include "esphome/[^\n]+\n', '', text, flags=re.M)
    (out / name).write_text('// Generated from the pinned ESPHome runtime_image component.\n'
                            '#include "../../image_buffer.h"\n' + text)
(out / 'runtime_image.h').write_text('#pragma once\n#include "../../image_buffer.h"\n')
