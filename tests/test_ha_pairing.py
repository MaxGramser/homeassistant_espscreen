"""A screen in Home Assistant without a step there (app 0.4.73, ha_pairing.py).

The app keeps looking until each screen it made is in Home Assistant and may perform actions: it answers Home
Assistant's discovery with the screen's own key, looks a screen up by its name when Home Assistant did not discover it,
gives the key back when Home Assistant asks for it again, and turns on "Allow the device to perform Home Assistant
actions" for a new screen and for one whose tap Home Assistant ignored. The fake below answers the config flows and
options flows the way Home Assistant's REST API did on the bench (Home Assistant 2026.9.4) and in its source
(homeassistant/components/esphome/config_flow.py): which step it asks, what a wrong key gets, and that the Configure
form starts at the current value.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import ha_pairing  # noqa: E402
from ha_pairing import Pairing, discovered_node, usable_key  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from aiohttp.test_utils import TestClient, TestServer
    from firmware import Firmware
    from manager_fixtures import with_screen_grid
    from server import HomeAssistant, Manager, Refused, create_app
    from test_screen_owned_settings import fake_ha

KEY = 'MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI='  # 32 bytes in base64, as New screen writes one
OLD = 'b2xkb2xkb2xkb2xkb2xkb2xkb2xkb2xkb2xkb2xkMTI='


class Clock:
    """time.monotonic() and time.time() that move only when a test says so."""
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def time(self):
        return 1_800_000_000 + self.now


class FakeHA:
    """Home Assistant's ESPHome flows, entries and repairs for screens on a pretend network.

    `network` is what the screens themselves hold: {node: {'key', 'mac'}}. A discovery is added with `discover`."""

    def __init__(self, clock, network=None, knows_key=False):
        self.clock = clock
        self.network = network if network is not None else {'kitchen-2': {'key': KEY, 'mac': 'aa:01'}}
        self.knows_key, self.resolvable = knows_key, True
        self.progress, self.entries, self.options, self.devices = {}, {}, {}, []
        self.blocked, self.calls, self.serial = set(), [], 0

    # -- what the app reads --
    async def flows(self):
        return [{'flow_id': flow_id, 'handler': 'esphome', 'step_id': flow['step'], 'context': flow['context']}
                for flow_id, flow in self.progress.items()]

    async def esphome_entries(self):
        return dict(self.entries)

    async def actions_blocked(self):
        return set(self.blocked)

    # -- what a screen does on the network --
    def discover(self, node, friendly=None):
        self.serial += 1
        name = node if friendly in (None, node) else f'{friendly} ({node})'
        self.progress[f'F{self.serial}'] = {'step': 'discovery_confirm', 'node': node,
                                            'context': {'source': 'zeroconf', 'title_placeholders': {'name': name}}}

    def paired(self, node, state='loaded', age=10 ** 6, allowed=True):
        """A screen Home Assistant already has, with its device."""
        entry_id = f'E-{node}'
        self.entries[entry_id] = {'entry_id': entry_id, 'domain': 'esphome', 'state': state,
                                  'created_at': self.clock.time() - age, 'node': node}
        self.options[entry_id] = {'allow_service_calls': allowed}
        self.devices = [d for d in self.devices if d['id'] != f'd-{node}'] + [{'id': f'd-{node}', 'config_entries': [entry_id]}]

    def screens(self):
        """The screens the app sees in Home Assistant's registry."""
        return [{'node': entry['node'], 'device_id': f"d-{entry['node']}", 'name': entry['node']} for entry in self.entries.values()]

    def create(self, flow_id, node):
        self.progress.pop(flow_id, None)
        self.paired(node, age=0, allowed=False)
        return {'type': 'create_entry', 'flow_id': flow_id, 'result': {'entry_id': f'E-{node}'}}

    # -- Home Assistant's REST API for flows --
    async def flow(self, method, path, data=None):
        self.calls.append((method, path, data))
        parts = path.split('/')
        if parts[0] == 'options':
            if method == 'delete':
                return {}
            if len(parts) == 2:
                return {'type': 'form', 'flow_id': 'O-' + data['handler'], 'step_id': 'init',
                        'data_schema': [{'name': 'allow_service_calls', 'default': self.options[data['handler']]['allow_service_calls']},
                                        {'name': 'subscribe_logs', 'default': False}]}
            self.options[parts[2][2:]] = {'subscribe_logs': False, **data}
            return {'type': 'create_entry', 'flow_id': parts[2]}
        if len(parts) == 1:
            self.serial += 1
            self.progress[f'U{self.serial}'] = {'step': 'user', 'node': None, 'context': {'source': 'user'}}
            return {'type': 'form', 'flow_id': f'U{self.serial}', 'step_id': 'user'}
        flow_id = parts[1]
        if method == 'delete':
            self.progress.pop(flow_id, None)
            return {}
        flow = self.progress[flow_id]
        node, step = flow['node'], flow['step']

        def form(step_id, errors=None):
            flow['step'] = step_id
            return {'type': 'form', 'flow_id': flow_id, 'step_id': step_id, 'errors': errors or {}}
        if step == 'user':
            node = flow['node'] = data['host'].removesuffix('.local')
            if node not in self.network or not self.resolvable:
                return form('user', {'base': 'resolve_error'})
            if any(e['node'] == node for e in self.entries.values()):
                self.progress.pop(flow_id)
                return {'type': 'abort', 'flow_id': flow_id, 'reason': 'already_configured_updates'}
            return self.create(flow_id, node) if self.knows_key else form('encryption_key')
        if step == 'discovery_confirm':
            return self.create(flow_id, node) if self.knows_key else form('encryption_key')
        if step == 'encryption_key':
            if data.get('noise_psk') != self.network[node]['key']:
                return form('encryption_key', {'base': 'invalid_psk'})
            if any(e['node'] == node for e in self.entries.values()):
                return {**form('name_conflict'), 'type': 'menu', 'menu_options': ['name_conflict_migrate', 'name_conflict_overwrite']}
            return self.create(flow_id, node)
        if step == 'name_conflict':
            self.progress.pop(flow_id)
            return {'type': 'abort', 'flow_id': flow_id, 'reason': 'name_conflict_migrated'}
        if step == 'reauth_confirm':
            if data.get('noise_psk') != self.network[node]['key']:
                return form('reauth_confirm', {'base': 'invalid_psk'})
            self.progress.pop(flow_id)
            self.entries[f'E-{node}']['state'] = 'loaded'
            return {'type': 'abort', 'flow_id': flow_id, 'reason': 'reauth_successful'}
        raise AssertionError(f'unexpected step {step}')


OURS = {'kitchen-2': {'api_key': KEY, 'friendly': 'Kitchen 2'}}


class TheDiscoveredDevice(unittest.TestCase):
    def test_is_known_by_its_node_inside_the_title_home_assistant_gives_it(self):
        # Seen on the bench: "Guition Wallbox (guition-wallbox)" for a friendly name, the node alone when they match.
        def flow(name, source='zeroconf'):
            return {'handler': 'esphome', 'context': {'source': source, 'title_placeholders': {'name': name}}}
        self.assertEqual(discovered_node(flow('Guition Wallbox (guition-wallbox)')), 'guition-wallbox')
        self.assertEqual(discovered_node(flow('wow')), 'wow')
        self.assertEqual(discovered_node(flow('Hall (upstairs) (hall-2)')), 'hall-2')
        for source in ('user', 'reauth', 'reconfigure'):
            self.assertIsNone(discovered_node(flow('Hall (hall)', source)), source)
        self.assertIsNone(discovered_node({**flow('hall'), 'handler': 'wled'}))

    def test_a_key_is_offered_only_as_new_screen_writes_one(self):
        self.assertTrue(usable_key(KEY))
        for key in (None, '', '!secret api_encryption_key', 'not base64 at all', 'c2hvcnQ='):
            self.assertFalse(usable_key(key), key)


class Looking(unittest.IsolatedAsyncioTestCase):
    """The app's look every few seconds, on a clock the test moves."""

    def setUp(self):
        self.clock = Clock()
        patch = mock.patch.object(ha_pairing, 'time', self.clock)
        patch.start()
        self.addCleanup(patch.stop)
        self.ha = FakeHA(self.clock)
        self.pairing = Pairing()

    async def look(self, seconds=ha_pairing.INTERVAL, ours=OURS):
        self.clock.now += seconds
        await self.pairing.run(self.ha, ours, self.ha.screens())

    def steps(self):
        return [(method, path) for method, path, _ in self.ha.calls]


class AScreenJoinsTheNetwork(Looking):
    async def test_its_discovery_is_answered_with_its_key_and_its_actions_turned_on(self):
        self.ha.discover('kitchen-2', 'Kitchen 2')
        await self.look()
        self.assertEqual(self.ha.calls[:2], [('post', 'flow/F1', {}), ('post', 'flow/F1', {'noise_psk': KEY})])
        self.assertEqual(self.steps()[2:], [('post', 'options/flow'), ('post', 'options/flow/O-E-kitchen-2')])
        self.assertTrue(self.ha.options['E-kitchen-2']['allow_service_calls'])
        # Done: the next looks change nothing.
        before = len(self.ha.calls)
        await self.look()
        await self.look(ha_pairing.ISSUES + 1)
        self.assertEqual(len(self.ha.calls), before)

    async def test_home_assistant_that_knows_the_key_is_not_asked_it(self):
        # With the ESPHome Device Builder app, Home Assistant reads the key from the same YAML.
        self.ha.knows_key = True
        self.ha.discover('kitchen-2', 'Kitchen 2')
        await self.look()
        self.assertEqual(self.steps(), [('post', 'flow/F1'), ('post', 'options/flow'), ('post', 'options/flow/O-E-kitchen-2')])

    async def test_a_screen_that_still_runs_older_firmware_is_added_once_it_has_its_key(self):
        # Found while its old firmware still runs: that key is not the profile's. A little later it is.
        self.ha.network['kitchen-2']['key'] = OLD
        self.ha.discover('kitchen-2', 'Kitchen 2')
        await self.look()
        self.assertEqual(self.ha.entries, {})
        self.assertEqual(self.pairing.state, {'kitchen-2': 'adding'})
        await self.look()   # not again right away
        self.assertEqual(len(self.ha.calls), 2)
        self.ha.network['kitchen-2']['key'] = KEY
        await self.look(ha_pairing.AGAIN)
        self.assertIn('E-kitchen-2', self.ha.entries)
        self.assertTrue(self.ha.options['E-kitchen-2']['allow_service_calls'])
        self.assertEqual(self.pairing.state, {})

    async def test_a_screen_home_assistant_did_not_discover_is_looked_up_by_its_name(self):
        # No discovery (mDNS does not reach Home Assistant, or someone dismissed or ignored it).
        self.ha.resolvable = False
        await self.look()
        self.assertEqual(self.ha.calls, [], 'a moment for the discovery first')
        await self.look(ha_pairing.LOOK_UP[0])
        self.assertEqual(self.ha.calls[1], ('post', 'flow/U1', {'host': 'kitchen-2.local', 'port': 6053}))
        # Not found: the flow it started is closed again, and it keeps looking, less often.
        self.assertEqual(self.ha.calls[-1], ('delete', 'flow/U1', None))
        self.assertEqual(self.ha.progress, {})
        self.ha.resolvable = True
        await self.look(ha_pairing.LOOK_UP[1] - 1)
        self.assertEqual(len(self.ha.calls), 3)
        await self.look(1)
        self.assertIn('E-kitchen-2', self.ha.entries)
        self.assertTrue(self.ha.options['E-kitchen-2']['allow_service_calls'])

    async def test_a_board_that_takes_over_a_paired_screens_name_keeps_its_history(self):
        # A replacement flashed from the same profile: Home Assistant's own "migrate".
        self.ha.paired('kitchen-2')
        self.ha.discover('kitchen-2', 'Kitchen 2')
        await self.look()
        self.assertIn(('post', 'flow/F1', {'next_step_id': 'name_conflict_migrate'}), self.ha.calls)
        self.assertEqual(self.ha.progress, {})

    async def test_a_screen_that_stays_found_but_not_added_gets_the_way_by_hand(self):
        self.ha.network['kitchen-2']['key'] = OLD
        self.ha.discover('kitchen-2', 'Kitchen 2')
        await self.look()
        self.assertEqual(self.pairing.state, {'kitchen-2': 'adding'})
        await self.look(ha_pairing.HELP_AFTER)
        self.assertEqual(self.pairing.state, {'kitchen-2': 'failed'})

    async def test_other_devices_and_profiles_without_a_usable_key_are_left_alone(self):
        self.ha.network['airco'] = {'key': KEY, 'mac': 'aa:02'}
        self.ha.discover('airco', 'Airco')
        await self.look(60, ours={})
        self.assertEqual(self.ha.calls, [])
        await self.look(60)
        self.assertNotIn(('post', 'flow/F1', {}), self.ha.calls)


class AScreenHomeAssistantHas(Looking):
    async def test_new_keys_from_new_screen_are_given_back_when_home_assistant_asks(self):
        # The integration stays loaded while Home Assistant asks for the key again (its reauth flow).
        self.ha.paired('kitchen-2', state='loaded')
        self.ha.progress['R1'] = {'step': 'reauth_confirm', 'node': 'kitchen-2',
                                  'context': {'source': 'reauth', 'entry_id': 'E-kitchen-2', 'title_placeholders': {'name': 'Kitchen 2'}}}
        await self.look()
        self.assertEqual(self.ha.calls[0], ('post', 'flow/R1', {'noise_psk': KEY}))
        self.assertEqual(self.ha.progress, {})
        # A reauth of an integration that is not one of these screens is not this app's.
        self.ha.paired('hall')
        self.ha.progress['R2'] = {'step': 'reauth_confirm', 'node': 'hall',
                                  'context': {'source': 'reauth', 'entry_id': 'E-hall', 'title_placeholders': {'name': 'Hall'}}}
        calls = len(self.ha.calls)
        await self.look(ha_pairing.AGAIN)
        self.assertFalse(any(path == 'flow/R2' for _, path, _ in self.ha.calls[calls:]))

    async def test_a_screen_someone_just_added_in_home_assistant_may_perform_actions(self):
        self.ha.paired('hall', age=30, allowed=False)
        await self.look(ours={})
        self.assertTrue(self.ha.options['E-hall']['allow_service_calls'])

    async def test_a_screen_this_app_made_is_checked_once_and_left_as_it_is_when_allowed(self):
        self.ha.paired('kitchen-2')
        await self.look()
        await self.look()
        self.assertEqual(self.steps(), [('post', 'options/flow'), ('delete', 'options/flow/O-E-kitchen-2')])

    async def test_an_integration_from_elsewhere_added_long_ago_keeps_what_someone_chose(self):
        self.ha.paired('hall', allowed=False)
        await self.look(ours={})
        self.assertFalse(self.ha.options['E-hall']['allow_service_calls'])
        self.assertEqual(self.ha.calls, [])

    async def test_a_tap_home_assistant_ignored_turns_the_actions_on(self):
        # Its repair issue: service_calls_not_enabled-<mac>.
        self.ha.paired('hall', allowed=False)
        await self.look(ours={})
        self.ha.blocked = {'d-hall'}
        self.pairing.issues_due = True
        await self.look(ours={})
        self.assertTrue(self.ha.options['E-hall']['allow_service_calls'])
        # Not every few seconds while Home Assistant still lists the issue.
        calls = len(self.ha.calls)
        self.pairing.issues_due = True
        await self.look(ours={})
        self.assertEqual(len(self.ha.calls), calls)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class ThroughTheApp(unittest.IsolatedAsyncioTestCase):
    def manager(self, tmp):
        (Path(tmp) / 'screens.json').write_text(json.dumps({'version': 1, 'screens': {}}))
        ha = with_screen_grid(fake_ha())
        flows = FakeHA(Clock())
        ha.flows, ha.flow, ha.esphome_entries, ha.actions_blocked = flows.flows, flows.flow, flows.esphome_entries, flows.actions_blocked
        ha.flow_ha = flows
        # The app's own reading of what Home Assistant found, on the fake's list of flows.
        ha.discovered_esphome = types.MethodType(HomeAssistant.discovered_esphome, ha)
        manager = Manager(ha, Path(tmp) / 'screens.json')
        manager.firmware = Firmware(Path(tmp) / 'esphome', Path(tmp) / 'data')
        manager.firmware.create({'board': 'cyd', 'name': 'kitchen-2', 'friendly_name': 'Kitchen 2',
                                 'wifi_ssid': 'ssid', 'wifi_password': 'password'})
        flows.network['kitchen-2']['key'] = manager.firmware.profile_names()['kitchen-2.yaml']['api_key']
        return manager

    async def test_new_screen_follows_the_screen_into_home_assistant(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp)
            manager.ha.flow_ha.discover('kitchen-2', 'Kitchen 2')
            async with TestClient(TestServer(create_app(manager, True))) as client:
                before = await (await client.get('/api/inventory?light=1')).json()
                # Found on the network: the device's title is "Kitchen 2 (kitchen-2)", and the page knows it as seen.
                self.assertEqual([(p['node'], p['seen']) for p in before['pending']], [('kitchen-2', True)])
                await manager.pair_screens()
                calls = manager.ha.flow_ha.calls
                self.assertEqual([path for _, path, _ in calls], ['flow/F1', 'flow/F1', 'options/flow', 'options/flow/O-E-kitchen-2'])
                # The profile's own key, the one New screen wrote into its YAML.
                self.assertEqual(calls[1][2], {'noise_psk': manager.ha.flow_ha.network['kitchen-2']['key']})

    async def test_the_notice_lets_a_screen_perform_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self.manager(tmp)
            manager.ha.flow_ha.entries['E1'] = {'entry_id': 'E1', 'domain': 'esphome', 'state': 'loaded', 'created_at': 0, 'node': 'office-1'}
            manager.ha.flow_ha.options['E1'] = {'allow_service_calls': False}
            manager.ha.devices = [{'id': 'd1', 'name': 'Office 1', 'config_entries': ['E1']}]
            async with TestClient(TestServer(create_app(manager, True))) as client:
                first = await (await client.get('/api/inventory?light=1')).json()
                inbox = first['screens'][0]['id']
                refused = await client.post(f'/api/screens/{inbox}/allow-actions')
                self.assertEqual(refused.status, 403)
                answer = await client.post(f'/api/screens/{inbox}/allow-actions', headers={'X-Screen-CSRF': first['csrf']})
                self.assertEqual(answer.status, 200)
                self.assertEqual(await answer.json(), {'allowed': True, 'name': 'Office 1'})
                self.assertTrue(manager.ha.flow_ha.options['E1']['allow_service_calls'])

                # Home Assistant does not let the app's token change an integration: the page says where to do it.
                async def not_allowed(method, path, data=None):
                    raise Refused('This app may not change it.')
                manager.ha.flow = not_allowed
                refused = await client.post(f'/api/screens/{inbox}/allow-actions', headers={'X-Screen-CSRF': first['csrf']})
                self.assertEqual(refused.status, 400)
                self.assertEqual((await refused.json())['error'], 'This app may not change it.')


if __name__ == '__main__':
    unittest.main()
