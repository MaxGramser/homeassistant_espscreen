import esphome.codegen as cg

CODEOWNERS = ["@jesserockz", "@clydebarrow"]
DEPENDENCIES = ["i2c"]

# A copy of ESPHome's gt911 under a name of its own: only the Waveshare ESP32-S3-Touch-LCD-4 (non-B) loads it, so
# every other GT911 board keeps ESPHome's own platform. docs/WAVESHARELCD4.md says why this board needs it.
gt911_ns = cg.esphome_ns.namespace("gt911_wavesharelcd4")
