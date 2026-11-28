#!/bin/sh
# Builds the chip's firmware: build.sh [BUILD_DIR]. Needs the Pico SDK (PICO_SDK_PATH, or PICO_SDK_FETCH_FROM_GIT=1),
# an arm-none-eabi-gcc with its C library on the PATH (or PICO_TOOLCHAIN_PATH) and picotool. The file is
# BUILD_DIR/tessera-indicator-rp2040.uf2.
set -e
here=$(cd "$(dirname "$0")" && pwd)
build=${1:-$here/build}
cmake -S "$here" -B "$build" -DCMAKE_BUILD_TYPE=Release ${PICO_TOOLCHAIN_PATH:+-DPICO_TOOLCHAIN_PATH="$PICO_TOOLCHAIN_PATH"}
cmake --build "$build" -j 8
ls -l "$build/tessera-indicator-rp2040.uf2"
