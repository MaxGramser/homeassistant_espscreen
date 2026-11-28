#!/usr/bin/env python3
"""The firmware of the boards' second chips, built and put into the app (docs/SECOND_CHIP.md, "Building it").

    tools/build_chips.py            builds every chip under chips/ and writes screen_manager/app/chips/<name>.uf2 and .json
    tools/build_chips.py --check    says whether what the app has was built from the sources as they are now

A chip's folder holds its sources, `version.txt` and `chip.json`: its name, the build's target, the USB ids its port
has and the name of the drive it shows as when it takes a new firmware, and the files outside its folder it is built
from. The app ships the built file, as it ships the browser's firmware preview: New screen hands it to the browser,
which writes it to the chip (docs/BOARD_STEPS.md), and no Home Assistant has to compile for an RP2040.

The .json beside the file says what it is: the version, its size and SHA-256, and a hash of the sources it was built
from. --check compares that hash, so a source that changed without a new build fails tools/check.sh. The build itself
is each chip's build.sh, which needs the Pico SDK (PICO_SDK_PATH), an arm-none-eabi-gcc with its C library
(PICO_TOOLCHAIN_PATH) and picotool.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHIPS = ROOT / 'chips'
APP = ROOT / 'screen_manager/app/chips'
UF2_MAGIC = (0x0A324655, 0x9E5D5157, 0x0AB16F30)
RP2040 = 0xE48BFF56


def chips():
    return sorted(path.parent for path in CHIPS.glob('*/chip.json'))


def sources_of(folder, about):
    """Every file a chip's firmware is made from: its folder (but for what a build leaves there) and what chip.json names."""
    files = [path for path in folder.rglob('*') if path.is_file() and 'build' not in path.relative_to(folder).parts]
    files += [(folder / extra).resolve() for extra in about.get('sources', [])]
    return sorted(files)


def source_hash(folder, about):
    digest = hashlib.sha256()
    for path in sources_of(folder, about):
        digest.update(os.path.relpath(path, ROOT).encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def uf2_blocks(data):
    """The blocks of a UF2 file, or ValueError: 512 bytes each, with the three magic numbers and one family."""
    if not data or len(data) % 512:
        raise ValueError('not a whole number of 512-byte blocks')
    for at in range(0, len(data), 512):
        block = data[at:at + 512]
        if (int.from_bytes(block[0:4], 'little'), int.from_bytes(block[4:8], 'little'), int.from_bytes(block[508:512], 'little')) != UF2_MAGIC:
            raise ValueError(f'block {at // 512} is no UF2 block')
        if int.from_bytes(block[28:32], 'little') != RP2040:
            raise ValueError(f'block {at // 512} is not for an RP2040')
    return len(data) // 512


def manifest(folder, data):
    about = json.loads((folder / 'chip.json').read_text())
    return {'name': about['name'], 'version': (folder / 'version.txt').read_text().strip(), 'file': about['name'] + '.uf2',
            'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'usb': about['usb'], 'drive': about['drive'],
            'source': source_hash(folder, about)}


def build(folder):
    about = json.loads((folder / 'chip.json').read_text())
    with tempfile.TemporaryDirectory() as work:
        subprocess.run([str(folder / 'build.sh'), work], check=True)
        data = (Path(work) / (about['target'] + '.uf2')).read_bytes()
    uf2_blocks(data)
    APP.mkdir(parents=True, exist_ok=True)
    (APP / (about['name'] + '.uf2')).write_bytes(data)
    (APP / (about['name'] + '.json')).write_text(json.dumps(manifest(folder, data), indent=2) + '\n')
    print(f"{about['name']} {manifest(folder, data)['version']}: {len(data)} bytes")


def check(folder):
    """What is wrong with the app's file for this chip, or None."""
    about = json.loads((folder / 'chip.json').read_text())
    file, record = APP / (about['name'] + '.uf2'), APP / (about['name'] + '.json')
    if not file.exists() or not record.exists():
        return f"{about['name']}: the app has no firmware for it, run tools/build_chips.py"
    data, have = file.read_bytes(), json.loads(record.read_text())
    try:
        uf2_blocks(data)
    except ValueError as error:
        return f"{about['name']}: {file.name} {error}"
    want = manifest(folder, data)
    for key in ('version', 'source', 'sha256', 'size', 'usb', 'drive', 'file', 'name'):
        if have.get(key) != want[key]:
            return (f"{about['name']}: the app's firmware was built from other sources than chips/{folder.name} holds now"
                    if key == 'source' else f"{about['name']}: {record.name} says another {key} than the file and its folder") + ', run tools/build_chips.py'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        wrong = [found for found in map(check, chips()) if found]
        print('\n'.join(wrong) if wrong else f'{len(chips())} chip firmware current')
        return 1 if wrong else 0
    if not shutil.which('cmake'):
        raise SystemExit('cmake is needed to build a chip\'s firmware')
    for folder in chips():
        build(folder)
    return 0


if __name__ == '__main__':
    sys.exit(main())
