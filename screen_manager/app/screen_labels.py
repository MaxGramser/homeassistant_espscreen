"""A screen's own name in this app (app 0.4.2): a label the editor shows instead of Home Assistant's device name.

Only the editor reads it. Home Assistant, the screen's YAML and its ESPHome name stay as they are, so a label
needs no flash and cannot break a pairing. Kept per Home Assistant device, which outlives a renamed inbox."""
import logging
import atomic

LOG = logging.getLogger(__name__)
MAX_LENGTH = 40


class ScreenLabels:
    def __init__(self, path):
        self.path = path
        data = atomic.read_json(path, 1)
        labels = data.get('labels') if data else None
        self.labels = {str(k): v for k, v in (labels or {}).items() if isinstance(v, str) and v.strip()}

    def get(self, device):
        return self.labels.get(device) if device else None

    def set(self, device, label):
        """An empty label gives the screen Home Assistant's name back."""
        label = ' '.join(str(label or '').split())[:MAX_LENGTH]
        if label:
            self.labels[device] = label
        elif self.labels.pop(device, None) is None:
            return None
        self._save()
        return label or None

    def forget(self, device):
        if device and self.labels.pop(device, None) is not None:
            self._save()

    def _save(self):
        try:
            atomic.write_json(self.path, {'version': 1, 'labels': self.labels})
        except OSError as error:
            LOG.warning('Could not keep the screen names (%s)', type(error).__name__)
