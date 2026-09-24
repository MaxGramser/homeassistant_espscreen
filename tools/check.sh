#!/usr/bin/env bash
# The release checks of docs/RELEASING.md step 2 in one command, the same on a laptop and in CI
# (.github/workflows/ci.yml, app 0.2.78). Runs from any folder: every path is taken from this repository.
#
#   tools/check.sh                   the Python tests, every tests/*.cpp, the package check, the icon generator's --check, the editor's
#                                    tests, types and build, and whether the editor bundle in Git equals that build
#   tools/check.sh --firmware        compiles every board profile (tools/profiles.py) and applies the CYD's flash budget
#   tools/check.sh --all             both
#   tools/check.sh --render          builds every board as a host program (tools/render/run.py): its self test must pass,
#                                    and what it draws is saved as PNGs under .esphome/render/out (needs SDL2)
#   --baseline BYTES                 with --firmware: the CYD image of the last release, to print the growth
#
# Environment:
#   PYTHON            python3 by default; needs aiohttp, PyYAML, Pillow, fontTools and jinja2 (.venv-portal/bin/python has them)
#   CXX               clang++ by default
#   ESPHOME           the ESPHome command, esphome by default ("python -m esphome", or a newer Device Builder's)
#   RENDER_PYTHON     for --render: a Python with aioesphomeapi and Pillow, by default the one next to ESPHOME
#   ESPHOME_DATA_DIR  where the firmware builds go, .esphome/check by default: apart from the bench profiles' own
#                     build folders, so a check build never replaces the firmware.bin of a screen's profile
#
# Every check prints PASS, WARN or FAIL; a failing check shows the end of its output. Exit status 1 when one failed.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON=${PYTHON:-python3}
CXX=${CXX:-clang++}
read -r -a ESPHOME_CMD <<< "${ESPHOME:-esphome}"

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'; }

want_fast=1 want_firmware=0 want_render=0 saw_firmware=0 saw_all=0 saw_render=0 baseline=""
while (($#)); do
  case $1 in
    --firmware) saw_firmware=1 ;;
    --all) saw_all=1 ;;
    --render) saw_render=1 ;;
    --baseline)
      baseline=${2:-}
      [[ $baseline =~ ^[0-9]+$ ]] || { echo "--baseline needs a size in bytes, such as 1655584" >&2; exit 2; }
      shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1 (see tools/check.sh --help)" >&2; exit 2 ;;
  esac
  shift
done
if ((saw_firmware || saw_all)); then want_firmware=1; fi
if ((saw_firmware && !saw_all)); then want_fast=0; fi
if ((saw_render)); then want_render=1; if ((!saw_all && !saw_firmware)); then want_fast=0; fi; fi

WORK=$(mktemp -d "${TMPDIR:-/tmp}/esp-screens-check.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

passed=0 count=0 last_ok=0
failed=() warned=()
note() { printf '%s' "$*" > "$WORK/note"; }   # a short result for the PASS line, such as "17/17"
warn() { printf '%s\n' "$*" >> "$WORK/warn"; } # passes, but someone has to look

# run NAME COMMAND...: one check. Its output goes to a log that is shown when it fails; last_ok says how it went.
# The command runs in a subshell, so its cd stays there. set -e doesn't reach into it (it runs as `cmd || ...`), so
# every check function stops on its own errors with `|| return 1`.
run() {
  local name=$1 log="$WORK/log-$((count += 1)).txt" start=$SECONDS status=0 detail=""
  shift
  rm -f "$WORK/note" "$WORK/warn"
  printf '%-40s ' "$name"
  ("$@") > "$log" 2>&1 || status=$?
  [[ -s $WORK/note ]] && detail=" $(cat "$WORK/note")"
  if ((status != 0)); then
    printf 'FAIL%s (%ss)\n' "$detail" $((SECONDS - start))
    # The last 200 lines, each cut at 1000 characters: an assertion can quote a whole header.
    tail -n 200 "$log" | awk '{ if (length($0) > 1000) $0 = substr($0, 1, 1000) " ..."; print "    | " $0 }'
    failed+=("$name")
    last_ok=0
  elif [[ -s $WORK/warn ]]; then
    printf 'WARN%s (%ss)\n' "$detail" $((SECONDS - start))
    sed 's/^/    ! /' "$WORK/warn"
    warned+=("$name")
    last_ok=1
  else
    printf 'PASS%s (%ss)\n' "$detail" $((SECONDS - start))
    passed=$((passed + 1))
    last_ok=1
  fi
}

skip() { printf '%-40s SKIP (%s)\n' "$1" "$2"; }

# ---- The fast checks ----

python_packages() {
  "$PYTHON" - <<'EOF' || return 1
import importlib.util, sys
wanted = {'aiohttp': 'aiohttp', 'yaml': 'PyYAML', 'PIL': 'Pillow', 'fontTools': 'fonttools', 'jinja2': 'jinja2'}
missing = [package for module, package in wanted.items() if importlib.util.find_spec(module) is None]
print(sys.executable, sys.version.split()[0])
# Without them the server and camera tests skip themselves, and a skipped test proves nothing.
if missing:
    sys.exit('Missing: ' + ' '.join(missing) + '. pip install them, or run with PYTHON=.venv-portal/bin/python')
EOF
  note "$("$PYTHON" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null || true)"
}

python_tests() {
  local out="$WORK/python.txt" status=0
  (cd "$ROOT" && "$PYTHON" -m unittest discover -s tests) > "$out" 2>&1 || status=$?
  cat "$out"
  note "$(grep -Eo '^Ran [0-9]+ tests?' "$out" | tail -n 1 | sed 's/^Ran //')$(grep -Eo 'skipped=[0-9]+' "$out" | tail -n 1 | sed 's/^/, /')"
  return "$status"
}

cpp_tests() {
  local test name total=0 good=0
  cd "$ROOT" || return 1
  for test in tests/*.cpp; do
    name=$(basename "$test" .cpp)
    total=$((total + 1))
    if "$CXX" -std=c++17 -Wall -Wextra -Werror -I. "$test" -o "$WORK/$name" && "$WORK/$name"; then
      good=$((good + 1))
      echo "PASS $name"
    else
      echo "FAIL $name"
    fi
  done
  note "$good/$total"
  ((total > 0 && good == total))
}

packages_current() { cd "$ROOT" && "$PYTHON" tools/check_packages.py; }
# One card per cell of a board's grid: the files are written, not hand-kept (docs/RESPONSIVE.md).
cells_current() { cd "$ROOT" && "$PYTHON" tools/generate_cells.py --check; }
icons_current() { cd "$ROOT" && "$PYTHON" tools/generate_icons.py --check; }
# What every board looks like, as the manager reads it (screen_manager/app/boards.json from the board files).
shapes_current() { cd "$ROOT" && "$PYTHON" tools/generate_board_shapes.py --check; }
entries_current() { cd "$ROOT" && "$PYTHON" tools/generate_entries.py --check; }
# The translations (app 0.2.90, docs/TRANSLATING.md): every language against English, the key header the firmware
# builds against, and no English left in the firmware's code.
translations_check() { cd "$ROOT" && "$PYTHON" tools/i18n.py check > "$WORK/i18n.txt" && "$PYTHON" tools/i18n.py header --check && "$PYTHON" tools/i18n.py lint; }
editor_install() { cd "$ROOT/web" && npm ci --no-audit --no-fund; }
editor_tests() { cd "$ROOT/web" && npm test; }
editor_types() { cd "$ROOT/web" && npm run check; }
firmware_preview() {
  cd "$ROOT" || return 1
  "$PYTHON" web/wasm/generate_renderer_manifest.py --check || return 1
  node web/wasm/test_profiles.mjs || return 1
  node web/wasm/test_runtime.mjs || return 1
  PREVIEW_WIDTH=720 PREVIEW_HEIGHT=720 PREVIEW_DPI=254 node web/wasm/test_runtime.mjs || return 1
  PREVIEW_WIDTH=800 PREVIEW_HEIGHT=480 PREVIEW_COLUMNS=3 node web/wasm/test_runtime.mjs || return 1
}
editor_build() { cd "$ROOT/web" && npm run build; }

# The add-on serves the committed bundle, so it must be what the committed web/src builds to (Vite names every file
# after a hash of its content). Compared with Git's index, so a freshly built bundle that is staged passes.
editor_bundle() {
  local static=screen_manager/app/static untracked
  cd "$ROOT" || return 1
  git rev-parse --is-inside-work-tree > /dev/null || { echo "Not a Git work tree: can't compare the bundle"; return 1; }
  untracked=$(git ls-files --others --exclude-standard -- "$static")
  if git diff --quiet -- "$static" && [[ -z $untracked ]]; then
    return 0
  fi
  echo "A fresh build of web/ differs from $static in Git. Commit the new build (it is in place now):"
  git diff --stat -- "$static"
  [[ -z $untracked ]] || printf 'new: %s\n' $untracked
  return 1
}

# ---- Firmware ----

esphome_version() {
  local pinned running
  pinned=$(sed -n 's|^FROM ghcr.io/esphome/esphome:||p' "$ROOT/screen_manager/Dockerfile")
  running=$("${ESPHOME_CMD[@]}" version | sed -n 's/^Version: //p')
  echo "ESPHome $running (${ESPHOME_CMD[*]}); the add-on ships $pinned"
  note "$running"
  [[ -n $running ]] || return 1
  [[ $running == "$pinned" ]] || warn "The add-on ships ESPHome $pinned: measure the release budget on that one too."
}

# The builds users get come from the YAML core.installation_yaml() writes: the board's package plus the device's own
# keys, the Wi-Fi fallback access point and captive_portal. The board profiles carry all of that (with !secret), so a
# copy of each profile compiles in a temporary checkout/ folder with placeholder secrets of the same length as real ones,
# beside links to this tree's components, fonts and packages (the shared core and the board files the profile includes,
# which a checkout entry names as ../packages): this commit's code, never GitHub's main, never the real secrets.yaml.
prepare_profiles() {
  local root="$WORK/config" config="$WORK/config/checkout" board file
  mkdir -p "$config" && ln -s "$ROOT/components" "$root/components" && ln -s "$ROOT/fonts" "$root/fonts" \
    && ln -s "$ROOT/packages" "$root/packages" || return 1
  cat > "$config/secrets.yaml" <<'EOF' || return 1
# Placeholders for the check builds (tools/check.sh); nothing here is a real key.
wifi_ssid: "check-wifi"
wifi_password: "check-wifi-password"
api_encryption_key: "Y2hlY2stYnVpbGQtcGxhY2Vob2xkZXIta2V5LTMyYnk="
ota_password: "check-build-ota-password-0000000"
ap_password: "check-ap-passwd0"
EOF
  # Every board that ships, by its checkout entry: the YAML users get, with the fallback hotspot.
  while read -r board file; do
    cp "$ROOT/$file" "$config/check-$board.yaml" || return 1
    if ! grep -q '^captive_portal:' "$config/check-$board.yaml" || ! grep -q '^  ap:' "$config/check-$board.yaml"; then
      echo "$file has no captive_portal: or wifi ap: any more, unlike the YAML users get; the flash figures would read low."
      return 1
    fi
  done < <(board_entries)
  echo "Check profiles in $config"
}

# The boards that ship and their checkout entries, one "board entry" per line (tools/profiles.py is the one list).
board_entries() {
  cd "$ROOT" && "$PYTHON" -c 'import sys; sys.path.insert(0, "tools"); import profiles
for name in profiles.PROFILES: print(profiles.board_of(name), name)'
}

# A board's own ESPHome floor: its board file's `min_version` when it has one, else the core's. A board that asks
# for more than the ESPHome running here is skipped instead of failed, which is what CI's min_version build needs
# (docs/ADDING_A_BOARD.md; the 10.1-inch Guition asks for 2026.8.0 while the packages promise 2026.6.2).
board_needs() {  # board_needs <board> -> its min_version
  cd "$ROOT" && "$PYTHON" -c 'import re, sys; sys.path.insert(0, "tools"); import profiles
board = sys.argv[1]
text = profiles.BOARDS[board].read_text()
found = re.search(r"(?m)^  min_version: (\S+)", text) or re.search(r"(?m)^  min_version: (\S+)", profiles.CORE.read_text())
print(found.group(1))' "$1"
}

older_version() {  # older_version A B -> true when A is older than B
  [[ $1 != "$2" ]] && [[ $(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1) == "$1" ]]
}

compile_board() {  # compile_board <board>
  local board=$1
  cd "$WORK/config/checkout" || return 1
  "${ESPHOME_CMD[@]}" -s DEVICE_NAME "check-$board" -s DEVICE_FRIENDLY_NAME "Check $board" compile "check-$board.yaml" || return 1
  flash_report "$board"
}

# flash_report BOARD [budget]: the image against its update slot, both read from the build, and on the CYD the growth
# against --baseline and the budget of docs/RELEASING.md step 2. Exit 3 means over 90 %: it passes, but the release has
# to say why.
flash_report() {
  local board=$1 mode=${2:-} status=0 out="$WORK/flash-$1.txt" against=""
  [[ $board == cyd ]] && against=$baseline
  "$PYTHON" - "$ESPHOME_DATA_DIR/build/check-$board" "$mode" "$against" > "$out" 2>&1 <<'EOF' || status=$?
import csv, sys
from pathlib import Path

build, mode, baseline = Path(sys.argv[1]), sys.argv[2], sys.argv[3]

def size(text):
    text = text.strip().upper()
    scale = {'K': 1024, 'M': 1024 * 1024}.get(text[-1:], 1)
    return int(text[:-1] if scale > 1 else text, 0) * scale

rows = csv.reader(line for line in (build / 'partitions.csv').read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith('#'))
slot = next((size(row[4]) for row in ([cell.strip() for cell in row] for row in rows)
             if len(row) >= 5 and row[1] == 'app' and (row[2] == 'ota_0' or row[0] == 'app0')), None)
if not slot:
    sys.exit(f'No app0/ota_0 partition in {build / "partitions.csv"}')
images = sorted(build.glob('.pioenvs/*/firmware.ota.bin')) or sorted(build.glob('.pioenvs/*/firmware.bin')) \
    or sorted(build.rglob('firmware.ota.bin'))
if not images:
    sys.exit(f'No firmware.ota.bin under {build}')
image = images[0].stat().st_size
share = image / slot * 100
line = f'{image:,} B of {slot:,} B = {share:.1f} % ({slot - image:,} B free)'
delta = None
if baseline:
    delta = image - int(baseline)
    line += f', {delta:+,} B against {int(baseline):,} B'
print(line)
if mode != 'budget':
    sys.exit(0)
if share > 95:
    print('Over 95 %: never ship this; it leaves no room for ESPHome upgrades and users\' own overrides.')
    sys.exit(1)
if share > 93:
    print('93-95 %: only fixes ship.')
    sys.exit(3)
if share > 90:
    print('90-93 %: tight. The release states its flash delta; more than 8 KB needs a matching saving or Max\'s OK.'
          + (f' This one grows {delta:,} B.' if delta is not None and delta > 8192 else ''))
    sys.exit(3)
EOF
  cat "$out"
  note "$(head -n 1 "$out")"
  if ((status == 3)); then
    warn "$(tail -n +2 "$out")"
    return 0
  fi
  return "$status"
}

cyd_budget() { flash_report cyd budget; }

# The overrides owners shared in GitHub issues (tests/fixtures/overrides/<board>-<case>.yaml), each read by ESPHome on
# its board the way a screen's own YAML loads it: a package after the board's (core.installation_yaml, local_overrides).
# An override lives on the owner's Home Assistant, where nothing else would notice that a change of ours broke it.
override_configs() {
  local config="$WORK/config/checkout" fixture board profile count=0 running needs
  running=$("${ESPHOME_CMD[@]}" version | sed -n 's/^Version: //p')
  mkdir -p "$config/overrides" || return 1
  for fixture in "$ROOT"/tests/fixtures/overrides/*.yaml; do
    board=$(cd "$ROOT" && "$PYTHON" -c 'import sys; sys.path.insert(0, "tools"); import profiles
name = sys.argv[1]; print(max((b for b in profiles.BOARDS if name.startswith(b + "-")), key=len))' "$(basename "$fixture" .yaml)") || return 1
    needs=$(board_needs "$board")
    if older_version "$running" "$needs"; then
      echo "$(basename "$fixture"): skipped, $board asks for ESPHome $needs"
      continue
    fi
    profile="$config/override-$(basename "$fixture")"
    cp "$fixture" "$config/overrides/" || return 1
    # The board's check profile with the override as the last package, as a screen's own YAML has it.
    "$PYTHON" - "$config/check-$board.yaml" "$profile" "overrides/$(basename "$fixture")" <<'PY' || return 1
import re, sys
text = open(sys.argv[1]).read()
text, n = re.subn(r'(?m)^(  board: !include [^\n]+\n)', r'\1  local_overrides: !include ' + sys.argv[3] + '\n', text, count=1)
if n != 1:
    sys.exit('no board package in ' + sys.argv[1])
open(sys.argv[2], 'w').write(text)
PY
    (cd "$config" && "${ESPHOME_CMD[@]}" -s DEVICE_NAME "check-$board" config "$(basename "$profile")" > "$profile.log" 2>&1) \
      || { tail -n 40 "$profile.log"; echo "$(basename "$fixture") does not build on $board"; return 1; }
    count=$((count + 1))
  done
  note "$count overrides"
}

# ---- Run ----

echo "ESP Screens checks in $ROOT"
if ((want_fast)); then
  run "Python packages" python_packages
  run "Python tests" python_tests
  run "C++ tests" cpp_tests
  run "Packages fit together" packages_current
  run "Cards of every grid" cells_current
  run "Board shapes for the manager" shapes_current
  run "Entry files of every board" entries_current
  run "Icons match tile_icons.py" icons_current
  run "Translations" translations_check
  run "Editor: npm ci" editor_install
  if ((last_ok)); then
    run "Editor: tests (Vitest)" editor_tests
    run "Firmware preview: WASM" firmware_preview
    run "Editor: types (vue-tsc)" editor_types
    run "Editor: build" editor_build
    if ((last_ok)); then run "Editor: bundle in Git is fresh" editor_bundle; else skip "Editor: bundle in Git is fresh" "no build"; fi
  else
    skip "Editor: tests, types, build" "npm ci failed"
  fi
fi

if ((want_firmware)); then
  export ESPHOME_DATA_DIR=${ESPHOME_DATA_DIR:-$ROOT/.esphome/check}
  run "ESPHome" esphome_version
  if ((last_ok)); then run "Check profiles" prepare_profiles; fi
  profiles_ok=$last_ok
  if ((profiles_ok)); then run "Overrides from GitHub issues" override_configs; fi
  if ((profiles_ok)); then
    # One after the other: parallel builds race on ESPHome's shared ESP-IDF install (and on PlatformIO's, before 2026.7).
    running=$("${ESPHOME_CMD[@]}" version | sed -n 's/^Version: //p')
    while read -r board _; do
      needs=$(board_needs "$board")
      if older_version "$running" "$needs"; then
        skip "Firmware: $board" "asks for ESPHome $needs, this is $running"
        continue
      fi
      run "Firmware: $board" compile_board "$board"
      if [[ $board == cyd ]]; then
        if ((last_ok)); then run "CYD flash budget" cyd_budget; else skip "CYD flash budget" "no CYD build"; fi
      fi
    done < <(board_entries)
  else
    skip "Firmware builds" "ESPHome or the check profiles are missing"
  fi
fi

# ---- Every board on the host: its self test, and what it draws (tools/render/run.py) ----

render_boards() {
  local python=${RENDER_PYTHON:-} out="$ROOT/.esphome/render/out"
  if [[ -z $python ]]; then
    python=$(dirname "$(command -v "${ESPHOME_CMD[0]}" 2>/dev/null || echo "${ESPHOME_CMD[0]}")")/python
    [[ -x $python ]] || python=$PYTHON
  fi
  command -v sdl2-config > /dev/null || { echo "SDL2 is missing: brew install sdl2, or apt install libsdl2-dev"; return 1; }
  cd "$ROOT" || return 1
  ESPHOME="${ESPHOME_CMD[*]}" "$python" tools/render/run.py --out "$out" || { note "see $out/summary.json"; return 1; }
  note "$(tail -n 1 "$out/summary.txt" 2>/dev/null)"
}

if ((want_render)); then
  run "Every board on the host" render_boards
fi

echo
echo "$passed passed, ${#warned[@]} warned, ${#failed[@]} failed"
((${#warned[@]} == 0)) || printf 'WARN: %s\n' "${warned[@]}"
if ((${#failed[@]})); then
  printf 'FAIL: %s\n' "${failed[@]}"
  exit 1
fi
