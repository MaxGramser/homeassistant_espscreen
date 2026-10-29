"""Video in Home Assistant (Settings): the tessera_video integration, which this app ships and installs only on request.

A screen with Screen camera's part Video serves its camera as live video with sound over RTSP (the plugins repository,
screen_camera). Home Assistant shows it through the custom integration in ha_integration/tessera_video: a camera
"Video" on the screen's own ESPHome device, played through go2rtc as WebRTC. This module

- writes that folder into Home Assistant's configuration folder (custom_components/tessera_video), when a person presses
  Install, and says whether the copy there is this app's (`status`);
- after Home Assistant restarted with it (a new custom integration loads only at a start), adds one entry of it for each
  screen that has the video and takes away the entry of a screen that lost it (`Videos.sync`), through the same config
  flow Home Assistant's own Add integration dialog takes, as ha_pairing.py does for the ESPHome integration.

Nothing reaches Home Assistant before the person asked: without the folder there, sync does nothing.
"""
import json
import logging
import os
import time
from pathlib import Path

import atomic
from i18n import t

LOG = logging.getLogger('screen_manager')

DOMAIN = 'tessera_video'
SOURCE = Path(__file__).parent / 'ha_integration' / DOMAIN
# The plugin and its part that give a screen the video (tessera-plugins, plugins/screen_camera/parts/video.yaml).
PLUGIN, PART = 'screen_camera', 'video'
# How often sync looks, and how long a screen's entry may wait for its ESPHome device before a new try.
INTERVAL = 30


def target(config=None):
    """Where the integration goes: <Home Assistant configuration>/custom_components/tessera_video."""
    return Path(config or os.environ.get('HA_CONFIG', '/homeassistant')) / 'custom_components' / DOMAIN


def files():
    """{relative path: bytes} of the integration as this app ships it."""
    return {str(path.relative_to(SOURCE)): path.read_bytes()
            for path in sorted(SOURCE.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}


def version():
    return json.loads((SOURCE / 'manifest.json').read_text(encoding='utf8'))['version']


def status(directory):
    """Whether the integration is there and equal to what this app version writes."""
    if not (directory / 'manifest.json').is_file():
        return {'installed': False, 'current': False, 'path': str(directory), 'version': version()}
    try:
        current = all((directory / name).read_bytes() == data for name, data in files().items())
    except OSError:
        current = False
    return {'installed': True, 'current': current, 'path': str(directory), 'version': version()}


def install(directory):
    """Write the integration, replacing an older copy, each file whole or not at all. Home Assistant loads a new or
    changed custom integration only at its next start: the editor then offers to restart it."""
    try:
        for name, data in files().items():
            atomic.write_text(directory / name, data.decode('utf-8'), mode=0o644)
    except OSError as error:
        raise ValueError(t('addon.errors.video.not_written', folder=directory,
                           reason=error.strerror or type(error).__name__)) from error
    LOG.info('Tessera video %s written to %s; Home Assistant loads it at its next start', version(), directory)
    return {**status(directory), 'restart': True}


def video_screens(plugins, screens):
    """({device id: screen name} of the screens that run the video, Screen camera built with its part Video; the device
    ids of the other screens this app knows, which do not). A screen whose build is under way or failed is in neither:
    what it runs is not known yet."""
    wanted, without = {}, set()
    for screen in screens:
        device = screen.get('device_id')
        if not device:
            continue
        record = next((r for r in plugins.store.of(screen['id']) if r.get('id') == PLUGIN), None)
        state = (record or {}).get('state', 'active')
        if record and state == 'active' and PART in (record.get('parts') or []):
            wanted[device] = screen.get('name') or device
        elif record is None or state == 'active':
            without.add(device)
    return wanted, without


class Videos:
    """Keeps one tessera_video entry for each screen with the video, once the integration is loaded in Home Assistant."""

    def __init__(self, directory):
        self.directory = directory
        self.loaded = None      # the version Home Assistant runs, None when it has not loaded the integration
        self.tried = {}         # device id -> monotonic time an entry may be tried again
        self.entries = 0

    async def loaded_version(self, ha):
        try:
            manifest = await ha.request('manifest/get', integration=DOMAIN)
        except Exception:  # noqa: BLE001 - not loaded (not installed, or not restarted since)
            return None
        return manifest.get('version') if isinstance(manifest, dict) else None

    async def sync(self, ha, wanted, without=()):
        """One look, with what video_screens() says: an entry for each screen with the video that has none, and away
        with the entry of a screen of this app that no longer has it. An entry of a device this app does not know (a
        screen built elsewhere, added by hand) stays. Returns what it did, for the log and the tests."""
        if not (self.directory / 'manifest.json').is_file():
            self.loaded = None
            return {'added': [], 'removed': []}
        self.loaded = await self.loaded_version(ha)
        if self.loaded is None:
            return {'added': [], 'removed': []}
        entries = [e for e in await ha.request('config_entries/get', domain=DOMAIN) or [] if isinstance(e, dict)]
        self.entries = len(entries)
        # Which screen an entry is for: Home Assistant's list of entries leaves their unique id out, so the device
        # registry says it, through the camera the entry put on the screen's device. An entry on no device yet (its
        # screen's ESPHome device is not there) is left alone, and the flow below says it is there already.
        ours = {e.get('entry_id'): e for e in entries}
        have = {}
        for device in getattr(ha, 'devices', None) or []:
            for entry_id in (device or {}).get('config_entries') or []:
                if entry_id in ours:
                    have[device.get('id')] = ours[entry_id]
        added, removed, now = [], [], time.monotonic()
        for device, name in wanted.items():
            if device in have or now < self.tried.get(device, 0):
                continue
            self.tried[device] = now + INTERVAL * 10
            if await self.add(ha, device) == 'added':
                added.append(device)
                LOG.info('%s: its video is in Home Assistant', name)
        for device, entry in have.items():
            if device in without and entry.get('entry_id'):
                await ha.delete_config_entry(entry['entry_id'])
                removed.append(device)
                LOG.info('%s: its video left Home Assistant (no Video on the screen any more)', entry.get('title') or device)
        return {'added': added, 'removed': removed}

    async def add(self, ha, device):
        """The integration's own dialog, answered with the screen's device: 'added', 'there' when the screen has an entry
        already, or None. A flow that does not end is closed again."""
        form = await ha.flow('post', 'flow', {'handler': DOMAIN})
        if form.get('type') != 'form' or not form.get('flow_id'):
            return None
        done = await ha.flow('post', f"flow/{form['flow_id']}", {'device': device})
        if done.get('type') == 'create_entry':
            return 'added'
        if done.get('type') == 'form' and done.get('flow_id'):
            await ha.flow('delete', f"flow/{done['flow_id']}")
        return 'there' if done.get('type') == 'abort' and done.get('reason') == 'already_configured' else None
