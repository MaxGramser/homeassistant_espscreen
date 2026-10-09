"""Push a demo layout with every card type straight into a screen's inbox.

Uses the same message builder as ESP Screen Manager, but with synthetic states,
so rendering can be checked without touching Home Assistant. The running
manager restores the real layout on its next keepalive (about two minutes).
"""
import math
import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import time
import yaml
from aioesphomeapi import APIClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
from core import Grid, extras, state_message, validate_layout, parse_shape  # noqa: E402
from layout_migrations import migrate_legacy  # noqa: E402
from page_layout import compile_tiles  # noqa: E402
from page_delivery import Sender  # noqa: E402

def demo_layout():
    return validate_layout({'title': 'Demo cards', 'tiles': [
        {'entity': 'screen.clock', 'name': '', 'options': {'display': 'analog', 'background': 'none'}},
        {'entity': 'weather.demo', 'name': 'Outside', 'options': {'display': 'forecast'}},
        {'entity': 'sensor.demo_temperature', 'name': 'Living room', 'options': {'display': 'graph', 'icon': 'thermometer'}},
        {'entity': 'person.demo', 'name': 'Max', 'options': {}},
        {'entity': 'timer.demo', 'name': 'Eggs', 'options': {'icon': 'chef-hat'}},
        {'entity': 'sun.sun', 'name': 'Sun', 'options': {'display': 'sunpath'}},
        {'entity': 'sensor.demo_energy', 'name': 'Usage today', 'options': {'display': 'graph', 'size': 'wide'}},
        {'entity': 'light.demo', 'name': 'Table lamp', 'options': {'display': 'watch', 'size': 'wide', 'icon': 'lamp'}},
        {'entity': 'weather.demo_default', 'name': 'Weather now', 'options': {}},
    ]})

# Direct controls on wide cards (firmware 0.2.19+): one card per control set.
def controls_layout():
    return validate_layout({'title': 'Direct control', 'tiles': [
        {'entity': 'cover.demo_curtain', 'name': 'Curtains Window covering', 'options': {'size': 'wide', 'icon': 'curtains'}},
        {'entity': 'climate.demo_ac', 'name': 'AC', 'options': {'size': 'wide'}},
        {'entity': 'media_player.demo_sonos', 'name': 'Sonos', 'options': {'size': 'wide', 'icon': 'speaker'}},
        {'entity': 'climate.demo_heating', 'name': 'Heating', 'options': {'size': 'wide', 'controls': 'mode', 'icon': 'radiator'}},
        {'entity': 'media_player.demo_radio', 'name': 'Sonos bedroom', 'options': {'size': 'wide', 'controls': 'playback', 'icon': 'radio'}},
        {'entity': 'vacuum.demo_robot', 'name': 'Pippa', 'options': {'size': 'wide'}},
        {'entity': 'switch.demo_desk', 'name': 'Desk', 'options': {'size': 'wide', 'background': 'blue', 'icon': 'power-socket-eu'}},
        {'entity': 'light.demo_table_lamp', 'name': 'Table lamp', 'options': {'size': 'wide', 'controls': 'brightness', 'icon': 'lamp'}},
        {'entity': 'number.demo_target', 'name': 'Target humidity', 'options': {'size': 'wide', 'icon': 'water-percent'}},
        {'entity': 'select.demo_mode', 'name': 'Heating mode', 'options': {'size': 'wide', 'icon': 'thermostat'}},
        {'entity': 'timer.demo_eggs', 'name': 'Eggs', 'options': {'size': 'wide', 'icon': 'chef-hat'}},
        {'entity': 'scene.demo_evening', 'name': 'Evening', 'options': {'size': 'wide', 'icon': 'sofa'}},
        {'entity': 'fan.demo_fan', 'name': 'Fan', 'options': {'size': 'wide'}},
        {'entity': 'cover.demo_shutter', 'name': 'Shutter', 'options': {'size': 'wide', 'controls': 'position', 'icon': 'window-shutter'}},
        {'entity': 'light.demo_ceiling', 'name': 'Ceiling light', 'options': {'size': 'wide', 'icon': 'ceiling-light'}},
        {'entity': 'weather.demo_outside', 'name': 'Outside', 'options': {'display': 'forecast'}},
        {'entity': 'script.demo_tv', 'name': 'Turn on TV', 'options': {'icon': 'television'}},
        {'entity': 'scene.demo_morning', 'name': 'Morning', 'options': {'icon': 'weather-sunset-up'}},
    ]})

def controls_states(now):
    end = now + timedelta(minutes=4, seconds=32)
    return {
        'cover.demo_curtain': {'state': 'open', 'attributes': {'current_position': 80, 'device_class': 'curtain', 'supported_features': 15}},
        'climate.demo_ac': {'state': 'cool', 'attributes': {'current_temperature': 21.5, 'temperature': 20, 'min_temp': 16, 'max_temp': 32, 'target_temp_step': 1.0, 'hvac_modes': ['off', 'heat_cool', 'cool', 'heat', 'fan_only', 'dry'], 'fan_modes': ['auto', 'low', 'medium', 'high'], 'fan_mode': 'low', 'swing_modes': ['off', 'both', 'vertical', 'horizontal'], 'swing_mode': 'off', 'supported_features': 425}},
        'media_player.demo_sonos': {'state': 'playing', 'attributes': {'volume_level': 0.17, 'is_volume_muted': False, 'media_title': 'TV', 'supported_features': 8321599}},
        'climate.demo_heating': {'state': 'heat', 'attributes': {'current_temperature': 19.5, 'temperature': 21, 'hvac_action': 'heating', 'hvac_modes': ['off', 'heat', 'auto']}},
        'media_player.demo_radio': {'state': 'playing', 'attributes': {'volume_level': 0.15, 'media_title': 'NPO Radio 2', 'supported_features': 8321599}},
        'vacuum.demo_robot': {'state': 'docked', 'attributes': {'battery_level': 100, 'fan_speed': 'max', 'fan_speed_list': ['quiet', 'balanced', 'turbo', 'max'], 'supported_features': 30524}},
        'switch.demo_desk': {'state': 'on', 'attributes': {}},
        'light.demo_table_lamp': {'state': 'on', 'attributes': {'brightness': 163}},
        'number.demo_target': {'state': '55', 'attributes': {'min': 30, 'max': 70, 'step': 5, 'unit_of_measurement': '%'}},
        'select.demo_mode': {'state': 'Comfort', 'attributes': {'options': ['Eco', 'Comfort', 'Boost']}},
        'timer.demo_eggs': {'state': 'active', 'attributes': {'finishes_at': end.isoformat(), 'duration': '0:05:00', 'remaining': '0:05:00'}},
        'scene.demo_evening': {'state': (now - timedelta(hours=3)).isoformat(), 'attributes': {}},
        'fan.demo_fan': {'state': 'off', 'attributes': {'percentage': 0}},
        'cover.demo_shutter': {'state': 'open', 'attributes': {'current_position': 35, 'supported_features': 15}},
        'light.demo_ceiling': {'state': 'off', 'attributes': {}},
        'weather.demo_outside': {'state': 'rainy', 'attributes': {'temperature': 18.4, 'temperature_unit': '°C', 'humidity': 92, 'wind_speed': 12.2, 'wind_speed_unit': 'km/h', 'apparent_temperature': 17.1,
                                                     'wind_bearing': 225, 'pressure': 1012, 'pressure_unit': 'hPa', 'visibility': 9.7, 'visibility_unit': 'km', 'precipitation_unit': 'mm'}},
        'script.demo_tv': {'state': 'off', 'attributes': {'last_triggered': (now - timedelta(hours=2, minutes=8)).isoformat()}},
        'scene.demo_morning': {'state': (now - timedelta(days=1, hours=5)).isoformat(), 'attributes': {}},
    }

def demo_states(now):
    end = now + timedelta(minutes=4, seconds=32)
    return {
        'weather.demo': {'state': 'partlycloudy', 'attributes': {'temperature': 18.4, 'temperature_unit': '°C'}},
        'weather.demo_default': {'state': 'rainy', 'attributes': {'temperature': 12.0, 'temperature_unit': '°C'}},
        'sensor.demo_temperature': {'state': '21.5', 'attributes': {'unit_of_measurement': '°C'}},
        'sensor.demo_energy': {'state': '7.42', 'attributes': {'unit_of_measurement': 'kWh'}},
        'person.demo': {'state': 'home', 'attributes': {'icon': 'mdi:account-child'}},
        'timer.demo': {'state': 'active', 'attributes': {'finishes_at': end.isoformat(), 'duration': '0:05:00', 'remaining': '0:05:00'}},
        'sun.sun': {'state': 'above_horizon', 'attributes': {'next_rising': (now + timedelta(hours=9)).isoformat(), 'next_setting': (now + timedelta(hours=2)).isoformat()}},
        'light.demo': {'state': 'on', 'attributes': {'brightness': 180}},
    }

def demo_forecast(now):
    conditions = ['sunny', 'partlycloudy', 'rainy', 'cloudy', 'lightning-rainy', 'snowy', 'partlycloudy']
    return [{'datetime': (now + timedelta(days=i)).isoformat(), 'condition': conditions[i], 'temperature': 21 - i, 'templow': 11 + i // 2,
             'precipitation': [0, 0, 4.2, 0.3, 11.5, 2, 0][i], 'precipitation_probability': [5, 20, 80, 30, 95, 60, 10][i]}
            for i in range(7)]

def demo_hourly(now):
    # Two days of hours: the first ten as they always were, then a day that warms and cools and rains in the evening.
    conditions = ['rainy', 'rainy', 'partlycloudy', 'partlycloudy', 'sunny', 'sunny', 'cloudy', 'lightning-rainy', 'rainy', 'cloudy']
    start = now.replace(minute=0, second=0, microsecond=0)
    hours = [{'datetime': (start + timedelta(hours=i)).isoformat(), 'condition': conditions[i], 'temperature': 18.4 + i * 0.6,
              'precipitation': [0.4, 0.2, 0, 0, 0, 0, 0, 2.1, 1.0, 0][i], 'precipitation_probability': [70, 55, 10, 5, 0, 0, 15, 85, 60, 20][i]}
             for i in range(10)]
    for i in range(10, 48):
        at = start + timedelta(hours=i)
        warm = 4 * math.sin((at.hour - 9) / 24 * 2 * math.pi)
        hours.append({'datetime': at.isoformat(), 'condition': 'rainy' if 18 <= at.hour <= 21 else 'partlycloudy' if 8 <= at.hour <= 17 else 'cloudy',
                      'temperature': round(16 + warm, 1), 'precipitation': 1.2 if 18 <= at.hour <= 21 else 0, 'precipitation_probability': 70 if 18 <= at.hour <= 21 else 10})
    return hours

def configuration(grid, rotate=0, digital=False, wide=False, controls=False, now=None, titles=None):
    """A canonical synthetic fixture, using the real board grid and formatter.

    The explicit fixture import is the only legacy-format boundary here. The
    screen receives protocol 2 through the same acknowledged sender as the app.
    """
    now = now or datetime.now(timezone.utc)
    layout, states = (controls_layout(), controls_states(now)) if controls else (demo_layout(), demo_states(now))
    if digital:
        layout['tiles'][0]['options'] = {'display': 'digital'}
    elif wide:
        layout['tiles'][0]['options'] = {'display': 'analog', 'size': 'wide'}
    layout['tiles'] = layout['tiles'][rotate:] + layout['tiles'][:rotate]
    for tile, slot in zip(layout['tiles'], grid.pack(layout['tiles'])):
        tile['slot'] = slot
    if titles: layout['page_titles'] = titles
    record = migrate_legacy(layout, grid)
    tiles = compile_tiles(record['layout'], grid)
    values = []
    for i, tile in enumerate(tiles):
        forecast = demo_forecast(now) if tile['entity'].startswith('weather.') else None
        hourly = demo_hourly(now) if tile['entity'].startswith('weather.') else None
        # The firmware this fixture renders draws the weather card's week (hello weather_week).
        message = state_message(i, tile, states, extras(tile, states, forecast, None, hourly, now, week=True), week=True)
        if tile['entity'].startswith('sensor.'):
            message['history'] = {'hours': 24, 'values': [round(18 + 4 * ((k * 7) % 11) / 10, 2) if k % 5 else None for k in range(24)]}
        values.append(message)
    bars = [[{'k': 'clock'}] for _ in record['layout']['pages']]
    region = {'keepalive': 120, 'clock_24h': True, 'numbers': 'point', 'group_min': 1, 'percent_space': False}
    return record, values, bars, region


def api_sender(client, services):
    """Native ESPHome responses acknowledge this call, never a cached text state."""
    service = next(service for service in services if service.name == 'screen_message')
    async def send(message):
        answer = await client.execute_service(service, {'message': json.dumps(message, ensure_ascii=False, separators=(',', ':'))}, return_response=True)
        if answer is None or not answer.success:
            raise RuntimeError(answer.error_message if answer else 'No screen response')
        return json.loads(answer.response_data)
    return Sender(send)


async def screen_grid(client, entities):
    """Wait for this connected board's reported grid; never guess its shape."""
    diagnostic = next(entity for entity in entities if entity.name == 'Screen layout')
    found = asyncio.get_running_loop().create_future()
    def state(update):
        if getattr(update, 'key', None) != diagnostic.key: return
        shape = parse_shape(getattr(update, 'state', None))
        if shape and not found.done(): found.set_result(Grid(shape['columns'], shape['rows']))
    client.subscribe_states(state)
    return await asyncio.wait_for(found, 10)

async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', required=True)
    p.add_argument('--name', required=True, help='Expected DEVICE_NAME')
    p.add_argument('--secrets', type=Path, default=Path(__file__).resolve().parents[1] / 'secrets.yaml')
    p.add_argument('--rotate', type=int, default=0, help='Put tile N first, so later pages land on page 1')
    p.add_argument('--digital', action='store_true', help='Digital clock on a single tile instead of the analog calendar card without a background')
    p.add_argument('--wide', action='store_true', help='Analog clock double-width (dial with digital time and date)')
    p.add_argument('--controls', action='store_true', help='Double-width cards with direct control (firmware 0.2.19+), three per page')
    args = p.parse_args()
    client = APIClient(args.host, 6053, noise_psk=yaml.safe_load(args.secrets.read_text())['api_encryption_key'],
                       client_info='Demo layout', expected_name=args.name)
    await client.connect(login=True)
    try:
        entities, services = await client.list_entities_services()
        # Firmware built before the English translation still names this entity in Dutch.
        inbox = next(e for e in entities if type(e).__name__ == 'TextInfo' and e.name in ('Tile settings', 'Tegelinstellingen'))
        grid = await screen_grid(client, entities)
        started = time.monotonic()
        count = len(controls_layout()['tiles']) if args.controls else 9
        record, values, bars, region = configuration(grid, args.rotate % count, args.digital, args.wide, args.controls)
        sender = api_sender(client, services)
        await sender.synchronize(inbox.object_id, record, region, values, bars)
        print(f'Demo layout applied in {time.monotonic() - started:.1f}s; {len(record["layout"]["pages"])} pages, {len(values)} tiles')
    finally:
        await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
