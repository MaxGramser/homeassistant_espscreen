# The host render of main does not build on ESPHome 2026.9.0

## The symptom

`tools/render/run.py guition` on main (0.4.97, 9c7c6a67) with ESPHome 2026.9.0, the version the app's Dockerfile pins,
stops in the build: `float_output.h: static assertion failed: set_min_power() requires
USE_OUTPUT_FLOAT_POWER_SCALING` (2026-11-16, with and without the loop stack hotfix on top). Main's nightly CI is green:
the host render is not part of `tools/check.sh`, so nothing there sees it.

## What we know

- The Guition 4848S040's backlight code (`packages/hardware/parts/guition-backlight-extras.yaml`, its Dimmest level)
  calls `id(gpio_backlight_pwm).set_min_power(...)`. On a board that output has `min_power: 0.01`, which makes ESPHome
  2026.9 build its power scaling in.
- The host render puts a template output of its own in place of every board output (`tools/render/host.py`), without
  `min_power`, so the host build lacks the power scaling and the static assertion fires.
- Dev fixed it in df32c78b (2026-11-11): the host's template outputs carry `min_power: 0%`, which changes nothing but
  keeps the power scaling in the build. That commit is not on main.

## Ruled out

- The loop stack hotfix: main without it fails the same way.
- The firmware on boards: their outputs keep their own `min_power`, and main's CI builds every board.

## The deciding experiment

Done: main with the loop stack hotfix and that one line in `tools/render/host.py` renders (guition: PASS, 51 page
checks, 2026-11-16). A hotfix release whose checks include a host render carries that line; otherwise main gets it with
the next release.

## Pointers

`tools/render/host.py` (the template outputs), `packages/hardware/parts/guition-backlight-extras.yaml`, df32c78b.

## Solved

On dev by df32c78b. On main with the next release, or with a hotfix that carries the one line.
