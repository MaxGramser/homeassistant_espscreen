import { expect, it } from 'vitest';
import { barKeys, availableControl, controlKeys } from '../src/model/tall-controls';

it('shows exactly the supported media subset within the chosen group', () => {
  for (let flags = 0; flags < 64; flags++) {
    const a = { supported_features: flags };
    expect(controlKeys('media_player', 'playback', 'playing', a).map(k => k.icon)).toEqual([
      ...(flags & 16 ? ['skip-previous'] : []), ...(flags & 1 ? ['pause'] : []), ...(flags & 32 ? ['skip-next'] : []),
    ]);
    expect(Boolean(availableControl('media_player', 'volume', 'playing', a))).toBe(Boolean(flags & 12));
  }
  expect(controlKeys('media_player', 'playback', 'idle', { supported_features: 16384 })).toEqual([{ icon: 'play', disabled: false, primary: true }]);
});
it('uses cover capabilities, direction and end stops and vacuum capabilities/state', () => {
  expect(controlKeys('cover', 'buttons', 'open', { supported_features: 3, current_position: 100, device_class: 'curtain' })).toEqual([
    { icon: 'arrow-expand-horizontal', disabled: true, primary: false }, { icon: 'arrow-collapse-horizontal', disabled: false, primary: false },
  ]);
  expect(controlKeys('cover', 'buttons', 'closed', { supported_features: 0 })).toEqual([]);
  expect(controlKeys('vacuum', 'buttons', 'cleaning', { supported_features: 4 | 16 }).map(k => k.icon)).toEqual(['pause', 'home-map-marker']);
  expect(controlKeys('vacuum', 'buttons', 'docked', { supported_features: 8192 }).map(k => k.icon)).toEqual(['play']);
  expect(controlKeys('timer', 'buttons', 'active', {}).map(k => k.icon)).toEqual(['pause', 'close']);
});
it('keeps unsupported saved slider/setpoint choices inert', () => {
  for (const [domain, kind, attrs] of [
    ['light', 'brightness', { supported_color_modes: ['onoff'] }], ['fan', 'speed', { supported_features: 0 }],
    ['cover', 'position', { supported_features: 3 }], ['climate', 'setpoint', { supported_features: 0 }],
  ] as const) expect(availableControl(domain, kind, 'on', attrs)).toBe('');
  expect(availableControl('climate', 'setpoint', 'heat', { supported_features: 1 })).toBe('setpoint');
  // A thermostat with only a range has its -/+ with the chip (firmware 0.19.0+); an older screen draws it without them.
  expect(availableControl('climate', 'setpoint', 'heat_cool', { supported_features: 2 })).toBe('setpoint');
  expect(availableControl('climate', 'setpoint', 'heat_cool', { supported_features: 2 }, false)).toBe('');
  expect(availableControl('light', 'brightness', 'on', { supported_color_modes: ['rgbww'] })).toBe('brightness');
  expect(availableControl('media_player', 'playback', 'unavailable', { supported_features: 49 })).toBe('');
  expect(availableControl('light', null, 'on', { supported_color_modes: ['brightness'] })).toBe('');
});
it('limits modes to real choices and disables selects with fewer than two options', () => {
  // A thermostat's modes are its mode bar (tile_controls::climate_bar_keys, firmware 0.19.0): heat and cool first, never
  // off (the tile's circle switches it), the mode it is in always shown, "…" in the last place.
  expect(controlKeys('climate', 'mode', 'cool', { hvac_modes: ['fan_only', 'cool', 'off'] }).map(k => k.mode)).toEqual(['cool', 'fan_only']);
  const six = { hvac_modes: ['off', 'heat_cool', 'cool', 'heat', 'fan_only', 'dry'] };
  expect(controlKeys('climate', 'mode', 'cool', six).map(k => k.mode ?? k.icon)).toEqual(['heat', 'cool', 'dots-horizontal']);
  expect(barKeys(six, 'cool').map(k => k.mode)).toEqual(['heat', 'cool', 'heat_cool', 'dry', 'fan_only']);
  expect(barKeys(six, 'cool', 2).map(k => k.mode)).toEqual(['heat', 'cool']);
  expect(barKeys(six, 'dry', 3).map(k => k.mode ?? k.icon)).toEqual(['heat', 'dry', 'dots-horizontal']);
  expect(barKeys({ hvac_modes: ['off', 'heat'] }, 'heat')).toEqual([]);
  expect(barKeys(six, 'cool', 1)).toEqual([]);
  expect(controlKeys('select', 'stepper', 'Eco', { options: ['Eco'] }).every(k => k.disabled)).toBe(true);
});

// A humidifier (firmware 0.42.0+) is a thermostat in percent: its humidity between - and + and as a slider whatever it
// reports, its own modes in the order its integration lists them with Home Assistant's icons, and its toggle.
it('gives a humidifier its controls and its own modes', () => {
  for (const kind of ['setpoint', 'setpoint_mode', 'slider', 'toggle']) expect(availableControl('humidifier', kind, 'on', {})).toBe(kind);
  expect(availableControl('humidifier', 'stepper', 'on', {})).toBe('');
  expect(availableControl('humidifier', 'setpoint', 'unavailable', {})).toBe('');
  const a = { supported_features: 1, available_modes: ['normal', 'eco', 'turbo'], mode: 'eco' };
  expect(controlKeys('humidifier', 'mode', 'on', a)).toEqual([
    { icon: '', cp: 'F058E', mode: 'normal' }, { icon: '', cp: 'F032A', mode: 'eco' }, { icon: '', cp: 'F09DE', mode: 'turbo' },
  ]);
  expect(availableControl('humidifier', 'mode', 'on', a)).toBe('mode');
  // The mode it is in stays in sight, a mode of its own name kept as it is.
  const many = { available_modes: ['normal', 'eco', 'away', 'boost', 'comfort', 'home', 'sleep', 'auto'], mode: 'Auto' };
  expect(barKeys(many, 'on', 3, 'humidifier').map(k => k.mode ?? k.icon)).toEqual(['normal', 'eco', 'dots-horizontal']);
  expect(barKeys({ ...many, mode: 'sleep' }, 'on', 3, 'humidifier').map(k => k.mode ?? k.icon)).toEqual(['normal', 'sleep', 'dots-horizontal']);
  expect(barKeys({ available_modes: ['normal'], mode: 'normal' }, 'on', 6, 'humidifier')).toEqual([]);
  expect(availableControl('humidifier', 'mode', 'on', { available_modes: ['normal'] })).toBe('');
});

it('keeps slats independent of the primary choice and follows every cover feature mask', async () => {
  const { coverPrimary, hasCoverTilt, withCoverTilt, coverTiltKind, coverTiltKeys } = await import('../src/model/tall-controls');
  for (const primary of ['none', 'buttons', 'position']) {
    const selected = withCoverTilt(primary, true);
    expect(hasCoverTilt(selected)).toBe(true);
    expect(coverPrimary(selected)).toBe(primary);
    expect(withCoverTilt(coverPrimary(selected), false)).toBe(primary);
  }
  for (let flags = 0; flags < 256; flags++) {
    const attrs = { supported_features: flags, current_tilt_position: 100 };
    expect(coverTiltKind('open', attrs)).toBe(flags & 128 ? 'position' : flags & 112 ? 'buttons' : '');
    expect(coverTiltKind('unavailable', attrs)).toBe('');
    expect(coverTiltKeys(attrs).map(k => k.icon)).toEqual([
      ...(flags & 16 ? ['blinds-open'] : []), ...(flags & 64 ? ['stop'] : []), ...(flags & 32 ? ['blinds'] : []),
    ]);
    expect(availableControl('cover', 'position_tilt', 'open', attrs)).toBe(flags & 4 ? 'position' : '');
    expect(availableControl('cover', 'tilt', 'open', attrs)).toBe('');
  }
});
