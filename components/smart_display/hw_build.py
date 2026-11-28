"""The build's half of the capability record (hw.h, docs/PLATFORM_PLAN.md 3.3): which HW_* defines a configuration gets.

A screen has a speaker, a microphone, an echo canceller or a camera of its own when a component of that kind is in the
configuration ESPHome validated, wherever it came from: a part file (packages/hardware/parts/), a feature file, the
board's own override. Nothing here reads a board's name, a chip or a pin, and nothing reads an id: a second speaker
under another id counts as a speaker. Pure, so tests/test_hw.py runs it without ESPHome; smart_display/__init__.py
hands it CORE.config."""

# The define, and the top-level keys of a configuration that earn it (any of them, with at least one entry).
DEFINES = {
    "HW_SPEAKER": ("speaker",),
    "HW_MICROPHONE": ("microphone",),
    # An echo canceller between the speaker and the microphone: Espressif's AEC through the esp_audio_stack component
    # (packages/hardware/parts/es7210/aec.yaml), or ESPHome's own should it bring one under this name.
    "HW_ECHO_CANCEL": ("esp_aec",),
    # The board's own camera, as Screen camera brings it (plugin_manifest.FEATURES, 'camera').
    "HW_CAMERA": ("esp_video_camera",),
}


def present(config, key):
    """Whether `key` is a domain of the configuration with at least one entry: a list of platforms or a single block."""
    value = config.get(key)
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return True


def defines(config):
    """The HW_* defines a configuration earns, in DEFINES' order."""
    return [name for name, keys in DEFINES.items() if any(present(config, key) for key in keys)]
