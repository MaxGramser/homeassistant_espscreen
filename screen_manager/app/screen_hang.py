"""Which way a screen is to hang, standing up or lying down (app 0.4.85, firmware 0.53.0+).

Chosen beside the mockup in the editor, for a screen whose glass is not square: the layout is laid out on the grid of
that way and goes to the screen with it (begin's "upright"), which turns, starts again and keeps the way. Kept here per
Home Assistant device until the screen has it and after, so a screen whose preferences were wiped (a USB flash) is turned
back the next time its layout goes out. A screen nobody turned has no entry: it hangs the way it was built. A choice
keeps the angle its screen's own YAML was built with at the time (LVGL_ROTATION, None for its board's own): a screen
installed again with another way in New screen hangs that way, and the old choice no longer counts.
Kept apart from the saved layouts, whose records an older app reads with a fixed set of fields."""
import logging
import atomic

LOG = logging.getLogger(__name__)
WAYS = ('landscape', 'portrait')


class ScreenHang:
    def __init__(self, path):
        self.path = path
        data = atomic.read_json(path, 1)
        ways = data.get('ways') if data else None
        self.ways = {str(k): v for k, v in (ways or {}).items()
                     if isinstance(v, dict) and v.get('way') in WAYS and (v.get('built') is None or type(v.get('built')) is int)}

    def has(self, device):
        return bool(device) and device in self.ways

    def get(self, device, built=None):
        """The way chosen for the screen of `device`, when its YAML still builds at the angle it was chosen at, else None."""
        entry = self.ways.get(device) if device else None
        return entry['way'] if entry and entry.get('built') == built else None

    def set(self, device, way, built=None):
        """Keep `way` ('landscape' or 'portrait') for the screen of `device`, built at angle `built`. True when it changed."""
        entry = {'way': way, 'built': built}
        if not device or way not in WAYS or self.ways.get(device) == entry:
            return False
        self.ways[device] = entry
        self._save()
        return True

    def forget(self, device):
        if device and self.ways.pop(device, None) is not None:
            self._save()

    def _save(self):
        try:
            atomic.write_json(self.path, {'version': 1, 'ways': self.ways})
        except OSError as error:
            LOG.warning('Could not keep which way the screens hang (%s)', type(error).__name__)
