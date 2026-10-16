// Real LVGL menu, real touch/hold handling, no browser drawing or physical-device actions.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const wasmBinary = readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url));
for (const [width, height, dpi] of [[720, 720, 255], [480, 480, 170], [320, 240, 143]]) {
  const m = await createModule({ wasmBinary });
  assert.equal(m._preview_init(width, height, dpi, 2, 3), 1);
  let ms = 0;
  function tick(duration = 64) {
    for (let t = 0; t < duration; t += 32) { ms += 32; m._preview_time(ms, 1789401840, 7200); m._preview_render(); }
  }
  const objects = () => JSON.parse(m.ccall('preview_layout', 'string', [], [])).objects;
  const label = text => objects().find(o => o.type === 'label' && o.text === text);
  const send = (exportName, data) => m.ccall(exportName, null, ['string'], [JSON.stringify(data)]);
  const next = () => m.ccall('preview_next_setting', 'string', [], []);
  function tap(x, y) { tick(256); m._preview_touch(x, y, 1); tick(128); m._preview_touch(x, y, 0); tick(256); }
  function tapLabel(text) {
    const o = label(text); assert.ok(o, `Missing ${text}: ${JSON.stringify(objects().filter(o => o.type === 'label'))}`);
    tap(Math.round((o.x1 + o.x2) / 2), Math.round((o.y1 + o.y2) / 2));
  }
  configure(connection(m), 'Test room', 1, [{ entity: 'screen.clock', name: 'Clock', slot: 0, state: '', a: {}, o: { display: 'digital' } }]);
  send('preview_settings', { name: 'Test panel', values: { dark_mode: false, swipe_pages: true } });
  const rows = [{ key: 'aec', entity: 'switch.test_aec', label: 'Echo cancellation', kind: 'switch', value: true, available: true },
    { key: 'gain', entity: 'number.test_gain', label: 'Gain', kind: 'number', value: 30, min: 0, max: 36, step: 3, unit: 'dB', available: true }];
  send('preview_extras', rows);
  tick();
  // A short press must not open Settings; a hold on the title must.
  tap(width / 2, 12);
  assert.ok(!label('Settings'));
  m._preview_touch(width / 2, 12, 1); tick(1664); m._preview_touch(width / 2, 12, 0); tick();
  assert.ok(label('Settings'), 'Holding the real firmware title opens Settings');
  assert.ok(label('Settings').line_height > 10, 'Settings uses the firmware profile font');
  tapLabel('Extras');
  assert.ok(label('Echo cancellation'));
  assert.ok(label('30dB'));
  tapLabel('Echo cancellation');
  assert.equal(next(), '', 'Disabled device control never emits a setting command');
  m._preview_settings_controls(1);
  tapLabel('Echo cancellation');
  assert.deepEqual(JSON.parse(next()), { entity: 'switch.test_aec', value: false });
  // A real-device push updates the existing page and emits no write back to HA.
  send('preview_extras', rows.map(r => ({ ...r, value: r.key === 'aec' ? false : 33 })));
  tick();
  assert.ok(label('33dB'));
  assert.equal(next(), '');
  tapLabel('Echo cancellation');
  assert.deepEqual(JSON.parse(next()), { entity: 'switch.test_aec', value: true });
  // An unavailable setting cannot run, even when the user has enabled device control.
  send('preview_extras', rows.map(r => ({ ...r, available: false })));
  tick();
  assert.ok(label('Unavailable'), 'Missing HA state is not displayed as zero or off');
  tapLabel('Echo cancellation');
  assert.equal(next(), '');
  // Header Back returns first to the menu, then to the tile page.
  tap(Math.round(width * .07), Math.round(height * .07));
  assert.ok(label('Settings'));
  tap(Math.round(width * .07), Math.round(height * .07));
  assert.ok(!label('Settings'));
  assert.ok(!label('Echo cancellation'));
  console.log(`PASS settings ${width}x${height}: hold, firmware fonts, Extras, push, control guard and back`);
}
