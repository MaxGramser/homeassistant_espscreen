"""Updates said in Home Assistant (docs/BUILDS.md, "Updates of a screen"): one notification that names every screen with
an update waiting, its firmware's (Updater) and its plugins' (Plugins), made again when what waits changes and taken
away once nothing waits. Looked at every EVERY seconds, said only on a change."""
import asyncio
import logging

import ha_notice
from i18n import screen_t

LOG = logging.getLogger('screen_manager')
NOTIFICATION = 'tessera_updates'


class UpdateNotice:
    EVERY = 900

    def __init__(self, manager):
        self.manager = manager
        self.said = None   # what the notification says now: {(inbox, what, version)}; None until the first look

    def waiting(self):
        """Every update a screen has waiting: {inbox: [(what, version, name)]}, 'firmware' for its own and a plugin's id
        for each plugin with a newer release than it runs."""
        updates, plugins = self.manager.updates, getattr(self.manager, 'plugins', None)
        out = {}
        for screen in self.manager.screens():
            items = []
            firmware = updates.firmware_waiting(screen)
            if firmware:
                items.append(('firmware', firmware, None))
            if plugins is not None:
                items += plugins.updates_on(screen['id'])
            if items:
                out[screen['id']] = items
        return out

    async def announce(self):
        """Say what waits, when it changed since the last look. A first look with nothing waiting takes away a
        notification an earlier run of the app may have left."""
        waiting = self.waiting()
        now = {(inbox, what, version) for inbox, items in waiting.items() for what, version, _ in items}
        if now == self.said:
            return
        self.said = now
        ha = getattr(self.manager, 'ha', None)
        if not now:
            await ha_notice.dismiss(ha, NOTIFICATION)
            return
        lines = []
        for inbox, items in waiting.items():
            screen = self.manager.screen(inbox) or {}
            what = ', '.join(screen_t('addon.notify.updates_firmware', version=version) if item == 'firmware'
                             else f'{name or item} {version}' for item, version, name in items)
            lines.append(f'- **{screen.get("name") or inbox}**: {what}')
        await ha_notice.show(ha, NOTIFICATION, screen_t('addon.notify.updates') + '\n\n' + '\n'.join(lines))

    async def run(self):
        while True:
            try:
                await self.announce()
            except Exception:   # the next look says it
                LOG.exception('Looking for updates to say in Home Assistant')
            await asyncio.sleep(self.EVERY)
