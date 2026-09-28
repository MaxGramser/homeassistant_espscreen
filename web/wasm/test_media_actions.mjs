// A real LVGL mute-button tap must use HA's current group, not cached membership.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const width = Number(process.env.PREVIEW_WIDTH || 480), height = width;
const m = await createModule({ wasmBinary: readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url)) });
assert.equal(m._preview_init(width, height, width === 720 ? 254 : 170, 2, 3), 1);
const receive = connection(m);
let ms = 0;
function tick(n = 300) { ms += n; m._preview_time(ms, 1789401840, 0); m._preview_render(); }
const tile = { entity: 'media_player.test', name: 'Music', state: 'playing',
  a: { media_title: 'Track', supported_features: 12, volume_level: .32, is_volume_muted: false } };
configure(receive, 'Media', 1, [{ ...tile, slot: 0, o: { size: 'full' } }]);
tick();
const template = "{{ (['media_player.test'] + (state_attr('media_player.test', 'group_members') or [])) | unique | list }}";
for (const muted of [true, false]) {
  const info = JSON.parse(m.ccall('preview_diagnostics', 'string', [], []));
  const icon = info.icons.filter(i => i.x < width / 4).sort((a, b) => b.y - a.y)[0];
  assert.ok(icon && icon.y > height * .6, 'volume icon at the bottom of the real media card');
  const x = icon.x + icon.width / 2, y = icon.y + icon.height / 2;
  tick(); m._preview_touch(x, y, 1); tick(120); m._preview_touch(x, y, 0); tick();
  const request = JSON.parse(m.ccall('preview_next_action', 'string', [], []));
  assert.equal(request.service, 'media_player.volume_mute');
  assert.deepEqual(request.data, { entity_id: tile.entity, is_volume_muted: String(muted) });
  assert.deepEqual(request.templates, { entity_id: template });
  assert.ok(request.call_id > 0);
  assert.equal(m.ccall('preview_next_action', 'string', [], []), '', 'one explicit group action per tap');
  if (muted && process.env.PREVIEW_ACTION_OUTPUT) writeFileSync(process.env.PREVIEW_ACTION_OUTPUT, JSON.stringify(request));
  m.ccall('preview_action_response', null, ['number', 'number', 'string'], [request.call_id, 1, '']);
  receive({ ...tile, op: 'state', i: 0, a: { ...tile.a, is_volume_muted: muted } });
  tick(4000);
}
receive({...tile,op:'state',i:0,a:{...tile.a,supported_features:63|16384}});tick(1000);
for(const [codepoint,service] of [[0xF04AD,'media_player.media_next_track'],[0xF04AE,'media_player.media_previous_track']]){
  const info=JSON.parse(m.ccall('preview_diagnostics','string',[],[]));
  const icon=info.icons.find(i=>i.codepoint===codepoint);
  assert.ok(icon,`playback key ${service} exists`);
  const x=icon.x+icon.width/2,y=icon.y+icon.height/2;
  tick();m._preview_touch(x,y,1);tick(120);m._preview_touch(x,y,0);tick();
  const request=JSON.parse(m.ccall('preview_next_action','string',[],[]));
  assert.equal(request.service,service);
  assert.equal(request.data.entity_id,tile.entity);
  m.ccall('preview_action_response',null,['number','number','string'],[request.call_id,1,'']);
  tick(4000);
}
// Both states of the main key use the same native play/pause action. The
// reported HA state, rather than the local tap alone, decides which icon shows.
for (const [before, glyph, after, confirmedGlyph] of [
  ['playing', 0xF03E4, 'paused', 0xF040A],
  ['paused', 0xF040A, 'playing', 0xF03E4],
]) {
  receive({...tile,op:'state',i:0,state:before,a:{...tile.a,supported_features:63|16384}});tick(1000);
  const info=JSON.parse(m.ccall('preview_diagnostics','string',[],[]));
  const icon=info.icons.find(i=>i.codepoint===glyph);
  assert.ok(icon,`${before} shows its matching play/pause key`);
  const x=icon.x+icon.width/2,y=icon.y+icon.height/2;
  m._preview_touch(x,y,1);tick(120);m._preview_touch(x,y,0);tick();
  const request=JSON.parse(m.ccall('preview_next_action','string',[],[]));
  assert.equal(request.service,'media_player.media_play_pause');
  assert.equal(request.data.entity_id,tile.entity);
  assert.equal(m.ccall('preview_next_action','string',[],[]),'','one play/pause action per tap');
  m.ccall('preview_action_response',null,['number','number','string'],[request.call_id,1,'']);
  receive({...tile,op:'state',i:0,state:after,a:{...tile.a,supported_features:63|16384}});tick(4000);
  assert.ok(JSON.parse(m.ccall('preview_diagnostics','string',[],[])).icons.some(i=>i.codepoint===confirmedGlyph),
    'Home Assistant confirmation updates the main key');
}
console.log(`PASS ${width}x${height}: mute/unmute group template, next/previous, play/pause, confirmation and preserved volume`);
