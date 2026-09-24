#!/usr/bin/env python3
"""Write the firmware-source fingerprint embedded in the host renderer."""
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

root = Path(next((arg for arg in sys.argv[1:] if not arg.startswith('--')), Path(__file__).resolve().parents[2])).resolve()
files = [root / "components/smart_display/runtime_tiles.h", root / "components/smart_display/renderer_host_api.h"]
seen = set()
pending = list(files)
while pending:
    path = pending.pop()
    if path in seen:
        continue
    seen.add(path)
    if not path.is_file():
        raise SystemExit(f"missing firmware renderer source: {path}")
    for name in re.findall(r'^\s*#include\s+"([^"]+)"', path.read_text(errors="replace"), re.M):
        candidate = (path.parent / name).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            pending.append(candidate)
files = sorted(seen)
files += [Path(__file__).resolve(), root / 'components/smart_display/screen_text_gen.py']
files += sorted((root / 'web/wasm/generated').rglob('*.h'))
files += [root / 'web/wasm/generated/font.cpp', root / 'web/wasm/generate_host_ui.py', root / 'web/wasm/preview_profiles.py', root / 'web/wasm/build.py', root / 'web/wasm/firmware_preview.cpp', root / 'web/wasm/lv_conf.h']
files += sorted((root / 'fonts').glob('*.ttf'))
files = sorted({p for p in files if p.name != 'firmware_renderer_manifest.h'})
digest = sha256()
for path in files:
    if not path.is_file():
        raise SystemExit(f"missing firmware renderer source: {path}")
    digest.update(str(path.relative_to(root)).encode())
    digest.update(path.read_bytes())
# Hash the resolved UI portions, so changing a board's pins does not invalidate
# the renderer but changing its look, glyph set, cell prototype or boot bindings does.
sys.path.insert(0, str(root / 'tools'))
import profiles
from preview_profiles import variants
for dpi, look, profile in variants():
    raw = profiles.raw_substitutions(root / profile)
    raw['DISPLAY_DPI'] = str(dpi)
    resolved = profiles.resolve(profiles.CORE.read_text(), profiles.evaluate(raw))
    for section in ('esphome', 'font', 'lvgl'):
        digest.update(re.search(r'^' + section + r':\n.*?(?=^[a-z_]+:|\Z)', resolved, re.M | re.S)[0].encode())
digest.update((root / 'packages/cells/6.yaml').read_bytes())
english = json.loads((root / 'screen_manager/translations/en.json').read_text())
digest.update(json.dumps({key: english[key] for key in ('screen', '_meta')}).encode())
digest.update(re.search(r'FROM ghcr.io/esphome/esphome:([^\s]+)', (root / 'screen_manager/Dockerfile').read_text())[1].encode())
out = root / "web/wasm/generated/firmware_renderer_manifest.h"
content = "// Generated. Do not edit; regenerate with web/wasm/build.sh.\n" + f'#define ESP_SCREEN_FIRMWARE_RENDERER_SOURCE_SHA256 "{digest.hexdigest()}"\n'
metadata = root / 'web/src/wasm/renderer.json'
metadata_content = json.dumps({
    'firmware': profiles.board_values('guition')['SCREEN_FIRMWARE_VERSION'].strip('"'),
    'profiles': [{'dpi': dpi, 'look': look} for dpi, look, _ in variants()],
}, indent=2) + '\n'
if '--check' in sys.argv:
    if not out.exists() or out.read_text() != content or not metadata.exists() or metadata.read_text() != metadata_content:
        raise SystemExit('Stale firmware preview: run web/wasm/build.sh, its runtime tests, and npm run build.')
else:
    out.write_text(content)
    metadata.write_text(metadata_content)
print(digest.hexdigest())
