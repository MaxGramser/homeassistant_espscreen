"""Optional audio uses the existing screen-owned settings flow and same-device test buttons."""
import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from test_screen_owned_settings import fake_ha, Manager, with_screen_grid
from server import create_app
from core import AUDIO_SETTINGS, AUDIO_TEST_BUTTONS, SETTING_ENTITIES, WAKE_WORD_OPTIONS


class AudioSettings(unittest.IsolatedAsyncioTestCase):
    def manager(self, directory, *, audio=True, tests=True):
        ha = fake_ha(firmware='0.22.0')
        if audio:
            for key in AUDIO_SETTINGS:
                domain, name = SETTING_ENTITIES[key]
                entity = f'{domain}.office_1_{key}'
                ha.registry.append({'entity_id': entity, 'device_id': 'd1', 'platform': 'esphome', 'original_name': name})
                ha.states[entity] = {'state': {'microphone_alc': 'on', 'speaker_volume': '25', 'wake_word': 'Okay Nabu'}.get(key, 'off')}
        if tests:
            for key, name in AUDIO_TEST_BUTTONS.items():
                entity = f'button.office_1_test_{key}'
                ha.registry.append({'entity_id': entity, 'device_id': 'd1', 'platform': 'esphome', 'original_name': name})
                ha.states[entity] = {'state': 'unknown'}  # never pressed is a usable button
            ha.registry.append({'entity_id': 'sensor.audio_status', 'device_id': 'd1', 'platform': 'esphome', 'original_name': 'Audio test status'})
            ha.states['sensor.audio_status'] = {'state': 'Idle'}
            ha.registry.append({'entity_id': 'binary_sensor.audio_active', 'device_id': 'd1', 'platform': 'esphome', 'original_name': 'Audio test active'})
            ha.states['binary_sensor.audio_active'] = {'state': 'off'}
        return Manager(with_screen_grid(ha), Path(directory) / 'screens.json')

    async def test_settings_from_ha_and_editor_changes_use_same_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            view = m.settings_view(m.screen('text.screen'))
            self.assertTrue(AUDIO_SETTINGS <= set(view['keys']))
            self.assertEqual(view['values']['speaker_volume'], 25)
            await m.change_settings('text.screen', {'speaker_volume': 45, 'tap_sound': True})
            self.assertIn(('number.set_value', {'entity_id': 'number.office_1_speaker_volume', 'value': 45}), m.ha.calls)
            self.assertIn(('switch.turn_on', {'entity_id': 'switch.office_1_tap_sound'}), m.ha.calls)
            before = m.settings_states_key()
            m.ha.states['number.office_1_speaker_volume'] = {'state': '60'}
            self.assertNotEqual(m.settings_states_key(), before)
            self.assertEqual(m.settings_view(m.screen('text.screen'))['values']['speaker_volume'], 60)
            m.ha.states['switch.office_1_microphone_alc'] = {'state': 'unavailable'}
            self.assertIn('microphone_alc', m.settings_view(m.screen('text.screen'))['unavailable'])

    async def test_automatic_gain_round_trip_and_retired_manual_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            self.assertTrue(m.settings_view(m.screen('text.screen'))['values']['microphone_alc'])
            await m.change_settings('text.screen', {'microphone_alc': False})
            self.assertIn(('switch.turn_off', {'entity_id': 'switch.office_1_microphone_alc'}), m.ha.calls)
            before = m.settings_states_key()
            m.ha.states['switch.office_1_microphone_alc']['state'] = 'off'
            self.assertNotEqual(m.settings_states_key(), before)
            self.assertFalse(m.settings_view(m.screen('text.screen'))['values']['microphone_alc'])
            await m.change_settings('text.screen', {'microphone_alc': True})
            self.assertIn(('switch.turn_on', {'entity_id': 'switch.office_1_microphone_alc'}), m.ha.calls)
            for key in ('microphone_gain', 'microphone_digital_gain'):
                m.ha.registry.append({'entity_id': 'number.old_' + key, 'device_id': 'd1', 'platform': 'esphome', 'original_name': key.replace('_', ' ').capitalize()})
                m.ha.states['number.old_' + key] = {'state': '6'}
                self.assertNotIn(key, m.settings_view(m.screen('text.screen'))['keys'])
                with self.assertRaises(ValueError):
                    await m.change_settings('text.screen', {key: 6})

    async def test_wake_word_round_trip_and_unknown_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            screen = m.screen('text.screen')
            self.assertEqual(m.settings_view(screen)['values']['wake_word'], 0)
            await m.change_settings('text.screen', {'wake_word': 1})
            self.assertIn(('select.select_option', {'entity_id': 'select.office_1_wake_word', 'option': 'Hey Jarvis'}), m.ha.calls)
            m.ha.states['select.office_1_wake_word']['state'] = 'Hey Jarvis'
            self.assertEqual(m.settings_view(screen)['values']['wake_word'], 1)
            for index, name in enumerate(WAKE_WORD_OPTIONS):
                await m.change_settings('text.screen', {'wake_word': index})
                self.assertIn(('select.select_option', {'entity_id': 'select.office_1_wake_word', 'option': name}), m.ha.calls)
                m.ha.states['select.office_1_wake_word']['state'] = name
                self.assertEqual(m.settings_view(screen)['values']['wake_word'], index)
            m.ha.states['select.office_1_wake_word']['state'] = 'Unsupported model'
            self.assertIn('wake_word', m.settings_view(screen)['unavailable'])

    async def test_activity_is_device_state_and_triggers_editor_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            screen = m.screen('text.screen')
            self.assertEqual(m.settings_view(screen)['audio_diagnostics']['active'], 'off')
            before = m.settings_states_key()
            m.ha.states['binary_sensor.audio_active']['state'] = 'on'
            self.assertNotEqual(m.settings_states_key(), before)
            self.assertEqual(m.settings_view(screen)['audio_diagnostics']['active'], 'on')

    async def test_audio_absent_does_not_create_fake_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, audio=False, tests=False)
            view = m.settings_view(m.screen('text.screen'))
            self.assertFalse(AUDIO_SETTINGS & set(view['keys']))
            self.assertEqual(view['audio_tests'], [])
            with self.assertRaises(ValueError):
                await m.change_settings('text.screen', {'tap_sound': True})

    async def test_diagnostic_changes_trigger_editor_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            before = m.settings_states_key()
            m.ha.states['sensor.audio_status']['state'] = 'Microphone test'
            self.assertNotEqual(before, m.settings_states_key())
            self.assertEqual(m.settings_view(m.screen('text.screen'))['audio_diagnostics']['status'], 'Microphone test')

    async def test_test_buttons_are_csrf_protected_and_bound_to_this_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.ha.registry.insert(0, {'entity_id': 'button.other_speaker', 'device_id': 'other', 'platform': 'esphome', 'original_name': 'Test speaker'})
            m.ha.registry.insert(0, {'entity_id': 'button.fake_speaker', 'device_id': 'd1', 'platform': 'template', 'original_name': 'Test speaker'})
            async with TestClient(TestServer(create_app(m, True))) as client:
                inventory = await (await client.get('/api/inventory?light=1')).json()
                headers = {'X-Screen-CSRF': inventory['csrf']}
                url = '/api/screens/text.screen/audio-test'
                self.assertEqual((await client.post(url, json={'test': 'speaker'})).status, 403)
                self.assertEqual((await client.post(url, headers=headers, json={'test': 'speaker'})).status, 200)
                self.assertEqual(m.ha.calls[-1], ('button.press', {'entity_id': 'button.office_1_test_speaker'}))
                for body in ({'test': 'restart'}, {'test': []}, {'entity_id': 'button.other_speaker'}, []):
                    self.assertEqual((await client.post(url, headers=headers, json=body)).status, 400)
                m.ha.states['button.office_1_test_speaker']['state'] = 'unavailable'
                self.assertEqual((await client.post(url, headers=headers, json={'test': 'speaker'})).status, 400)
                self.assertEqual((await client.post('/api/screens/unknown/audio-test', headers=headers, json={'test': 'speaker'})).status, 400)
