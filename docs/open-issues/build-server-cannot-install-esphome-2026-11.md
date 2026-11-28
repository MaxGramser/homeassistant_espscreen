# A build server on ESPHome 2026.10 cannot install the app's ESPHome 2026.11.1

## The symptom

Since the app builds with ESPHome 2026.11.1 (dev bf5d25cb, 2026-11-28), a build server running ESPHome Device Builder
2026.10.1 refuses every build the app sends: the app's log says
`<screen>.yaml builds here: the build server provision (failed to install esphome==2026.11.1 for a remote build (exit 1): ...7.2 (from esphome==2026.11.1)`,
and the build runs on the app's own machine instead (`Fallback('provision')`, screen_manager/app/build_server.py). The
builds succeed there, but on a Home Assistant host they take 20 to 40 minutes where the server took a few.

## What we know

- 2026-11-28, a home Home Assistant with a build server on a Mac: three screens (a CYD, a Guition 4 inch, a reTerminal
  D1001) were rebuilt on the app's ESPHome 2026.11.1, each through the fallback; all three run and report
  `0.68.0 (ESPHome 2026.11.1)`.
- The server installs the app's version (`target_esphome_version`) beside its own with pip. That pip run exits 1. The
  error text reaches the app cut to its last 300 characters (`_text(..., 300)`), so the requirement it could not meet is
  lost: only the end of a version, `.7.2`, is left.
- ESPHome 2026.11.1 installs fine with pip on Python 3.13 (uv, on the same day) and in its own Docker image on Python
  3.14.

## Candidates

- The server's Python is older than a requirement of ESPHome 2026.11.1 or of one of its pinned dependencies needs.
- A dependency pinned by ESPHome 2026.11.1 has no wheel for the server's platform and fails to build there.

## The deciding experiment

Read the server's own log of the failed provision (ESPHome Device Builder's log on the server), or run
`pip install esphome==2026.11.1` in a fresh virtual environment with the server's Python. Then either update the
server's ESPHome (Device Builder 2026.11 brings a Python that fits) or keep the whole pip error in the app's log: cut
the message at its start instead of its end, or log the full text the server sends.

## Pointers

`screen_manager/app/build_server.py` (`Fallback`, the `provision` reason, `_text`), docs/BUILDS.md "On a build server".
