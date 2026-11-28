"""A glass that takes no finger (the reTerminal E1001's): the touchscreen platform `no_touch`, which never reports a
touch. The shared tree reads a touch panel named `ts_touch` on every board (packages/core.yaml hands it to LVGL and
listens to it for the standby), so a board without one names this in its place and changes nothing of the shared
tree. Its pages turn with its keys (packages/features/page-keys.yaml); docs/RETERMINAL_E1001.md says what that board
can and cannot do without a finger.
"""
import esphome.config_validation as cv

CONFIG_SCHEMA = cv.invalid("no_touch is a platform of the touchscreen component: touchscreen: - platform: no_touch")
