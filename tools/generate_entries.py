"""Write the two entry files of every board in boards.yaml: packages/<key>.yaml and checkout/<key>.yaml.

A screen is built from an entry that includes the shared core and one board file (docs/PROFILES.md):

- packages/<key>.yaml is what a screen installed from ESP Screens builds from over GitHub. ESP Screen Manager writes
  every screen's own YAML with `files: [packages/<key>.yaml]`, so these names never change and their content is a
  promise to every screen out there: the fonts and the components from GitHub, nothing of the screen's own.
- checkout/<key>.yaml builds the same two files from a clone of this repository (checkout/README.md): the fonts and
  components of the checkout, the secrets from checkout/secrets.yaml.

The two differ between boards only in the board file they include and the components that board needs besides
smart_display: a component of this repository its hardware names as a platform (the CYD's xpt2046 touch panel). So
they are written from the catalog instead of by hand, and `--check` (tools/check.sh) fails when one is out of date.

    python3 tools/generate_entries.py            # write every board's two entries
    python3 tools/generate_entries.py --check    # fail when one differs from what this would write
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402

ROOT = profiles.ROOT
REPO = 'https://github.com/MaxGramser/homeassistant_espscreen'


def components(board):
    """The components of this repository a board's firmware needs: smart_display, and before it every other component
    under components/ that the board's files name as a platform (in the order they are found)."""
    text = '\n'.join(path.read_text() for path in profiles.chain(profiles.BOARDS[board]))
    own = {path.name for path in (ROOT / 'components').iterdir() if path.is_dir() and path.name != 'smart_display'}
    found = [name for name in dict.fromkeys(re.findall(r'(?m)^\s*-?\s*platform: ([a-z0-9_]+)\s*$', text)) if name in own]
    return found + ['smart_display']


def describe(board):
    entry = profiles.CATALOG[board]
    return f'{entry["name"]} {entry["model"]}'


def package_entry(board):
    file = profiles.CATALOG[board]['file']
    return f'''# ESP Screens - the package a {describe(board)} builds from over GitHub. Written by tools/generate_entries.py
# from boards.yaml; do not edit.
#
# ESP Screen Manager writes every screen's own YAML with `packages: display: {{url: <this repository>, files:
# [packages/{board}.yaml]}}` and adds the name, the Wi-Fi reference and the unique keys (docs/EASY_SETUP.md); nothing
# of that lives here. The screen is two packages: core.yaml, which every board shares, and boards/{file} with this
# board's hardware and sizes (docs/PROFILES.md). checkout/{board}.yaml builds the same two from a checkout.
substitutions:
  FONT_DIR: "https://raw.githubusercontent.com/MaxGramser/homeassistant_espscreen/main/fonts"

packages:
  core: !include core.yaml
  board: !include boards/{file}

external_components:
  - source:
      type: git
      url: {REPO}.git
      ref: main
      path: components
    refresh: 0s
    components: [{", ".join(components(board))}]
'''


def checkout_entry(board):
    file = profiles.CATALOG[board]['file']
    return f'''# ESP Screens - a {describe(board)} built from a clone of this repository. Written by tools/generate_entries.py
# from boards.yaml; do not edit. checkout/README.md says how to build it.
#
# The screen is two packages: packages/core.yaml, which every board shares, and packages/boards/{file} with
# this board's hardware and sizes (docs/PROFILES.md). A screen installed from ESP Screens builds the same two over
# GitHub through packages/{board}.yaml; this file only adds what a build from a checkout needs: the fonts and the
# components of this checkout, and the secrets (api_encryption_key, ota_password, Wi-Fi) from checkout/secrets.yaml.
substitutions:
  FONT_DIR: "../fonts"

packages:
  core: !include ../packages/core.yaml
  board: !include ../packages/boards/{file}

external_components:
  - source:
      type: local
      path: ../components
    components: [{", ".join(components(board))}]

api:
  encryption:
    key: !secret api_encryption_key

ota:
  - platform: esphome
    password: !secret ota_password

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  # Mains-powered panel: no modem sleep, so HA updates and OTA arrive without beacon latency.
  power_save_mode: none
{hotspot_of(board)}'''


def hotspot_of(board):
    """The Wi-Fi fallback hotspot and captive portal, as a screen's own YAML has them (core.installation_yaml): not on
    a board with 4 MB of flash (profiles.hotspot, app 0.4.5+), so tools/check.sh measures the image users get."""
    if not profiles.hotspot(board):
        return ''
    return '''  ap:
    ssid: "Smartdisplay Fallback Hotspot"
    password: !secret ap_password

captive_portal:
'''


def entries():
    """{path: text} for every board of the catalog."""
    found = {}
    for board in profiles.CATALOG:
        found[ROOT / 'packages' / f'{board}.yaml'] = package_entry(board)
        found[ROOT / 'checkout' / f'{board}.yaml'] = checkout_entry(board)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale = []
    for path, text in entries().items():
        if (path.read_text() if path.exists() else None) == text:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT))
        else:
            path.write_text(text)
            print(f'wrote {path.relative_to(ROOT)}')
    if stale:
        print('out of date, run tools/generate_entries.py: ' + ', '.join(map(str, stale)))
        return 1
    if args.check:
        print(f'{len(profiles.CATALOG)} boards, their entries match boards.yaml')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
