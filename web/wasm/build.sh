#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
exec "${PYTHON:-python3}" "$ROOT/web/wasm/build.py"
