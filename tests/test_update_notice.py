"""Updates said in Home Assistant (update_notice.py, docs/BUILDS.md "Updates of a screen"): one notification naming each
screen with what waits, said on a change only, taken away once nothing waits; and ha_notice, the one way to leave one."""
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
import ha_notice  # noqa: E402
from update_notice import NOTIFICATION, UpdateNotice  # noqa: E402


class HA:
    def __init__(self):
        self.calls = []

    async def request(self, kind, **data):
        self.calls.append((data['service'], data['service_data']))


class Updates:
    def __init__(self):
        self.firmware = {'hall': '0.64.0'}

    def firmware_waiting(self, screen):
        return self.firmware.get(screen['id'])


class Plugins:
    def __init__(self):
        self.updates = {'hall': [('rain', '0.6.1', 'Rain')]}

    def updates_on(self, inbox):
        return self.updates.get(inbox, [])


class Manager:
    def __init__(self):
        self.ha, self.updates, self.plugins = HA(), Updates(), Plugins()

    def screens(self):
        return [{'id': 'hall', 'name': 'Hall'}, {'id': 'desk', 'name': 'Desk'}]

    def screen(self, inbox):
        return next(s for s in self.screens() if s['id'] == inbox)


class Notice(unittest.IsolatedAsyncioTestCase):
    async def test_what_waits_is_said_once_and_taken_away_when_nothing_waits(self):
        m = Manager()
        notice = UpdateNotice(m)
        await notice.announce()
        service, data = m.ha.calls[-1]
        self.assertEqual((service, data['notification_id']), ('create', NOTIFICATION))
        self.assertIn('**Hall**', data['message'])
        self.assertIn('0.64.0', data['message'])
        self.assertIn('Rain 0.6.1', data['message'])
        self.assertNotIn('Desk', data['message'])
        await notice.announce()
        self.assertEqual(len(m.ha.calls), 1, 'said on a change only')
        m.updates.firmware.clear()
        m.plugins.updates.clear()
        await notice.announce()
        self.assertEqual(m.ha.calls[-1], ('dismiss', {'notification_id': NOTIFICATION}))

    async def test_a_home_assistant_that_cannot_be_told_fails_nothing(self):
        class Broken:
            async def request(self, kind, **data):
                raise ConnectionError('gone')
        await ha_notice.show(Broken(), 'x', 'message')
        await ha_notice.dismiss(None, 'x')


if __name__ == '__main__':
    unittest.main()
