// Real firmware timeline gestures and HA position updates. No live HA actions.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const width = Number(process.env.PREVIEW_WIDTH || 480);
const m = await createModule({ wasmBinary: readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url)) });
assert.equal(m._preview_init(width, width, width === 720 ? 254 : 170, 2, 3), 1);
let receive = connection(m);
let ms = 0;
function tick(n = 100) { for(let t=0;t<n;t+=20) { ms+=20; m._preview_time(ms,1789401840,0); m._preview_render(); } }
const info=()=>JSON.parse(m.ccall('preview_diagnostics','string',[],[]));
const actions=()=>{const out=[];for(;;){const value=m.ccall('preview_next_action','string',[],[]);if(!value)return out;out.push(JSON.parse(value));}};
const slider=()=>info().sliders.sort((a,b)=>a.y-b.y)[0];
const tile={entity:'media_player.test',name:'Music',state:'playing',
  a:{media_title:'Track',supported_features:14,volume_level:.3},x:{dur:200,pos:20,at:1789401840}};
configure(receive,'Music',1,[{...tile,slot:0,o:{size:'full'}}]); tick();
assert.equal(info().sliders.length,2,'seek and volume are separate native sliders');
assert.equal(slider().value,100);
function state(pos, features=14, title='Track') {
  receive({...tile,op:'state',i:0,a:{...tile.a,supported_features:features,media_title:title},x:{...tile.x,pos}}); tick();
}
state(120); assert.equal(slider().value,600,'incoming forward seek moves the knob');
state(30); assert.equal(slider().value,150,'incoming backward seek moves the knob');
function down(fraction){const s=slider();m._preview_touch(s.x+s.width*fraction,s.y+s.height/2,1);tick(120);}
function up(fraction){const s=slider();m._preview_touch(s.x+s.width*fraction,s.y+s.height/2,0);tick(120);}
down(.15);down(.75);assert.deepEqual(actions(),[],'dragging never floods HA');up(.75);
let command=actions();assert.equal(command.length,1);
assert.equal(command[0].service,'media_player.media_seek');
assert.equal(command[0].data.entity_id,tile.entity);
assert.ok(Math.abs(Number(command[0].data.seek_position)-150)<=2,JSON.stringify(command));
m.ccall('preview_action_response',null,['number','number','string'],[command[0].call_id,1,'']);
tick(1200);assert.ok(slider().value>730,'old HA anchor cannot immediately snap the knob back');
tick(6000);
state(30);
assert.ok(slider().value>730,'an accepted seek must survive the old four-second timeout and repeated stale HA position');
state(151);assert.equal(slider().value,755,'HA confirms the requested position');
tick(500);down(.4);up(.4);
command=actions();assert.equal(command.length,1,'tapping the track also seeks');
assert.equal(command[0].service,'media_player.media_seek');
assert.ok(Math.abs(Number(command[0].data.seek_position)-80)<=2);
m.ccall('preview_action_response',null,['number','number','string'],[command[0].call_id,1,'']);
state(80);tick(500);
down(.4);down(.7);state(0,14,'Next track');up(.7);
assert.deepEqual(actions(),[],'a track change during the gesture cancels the seek');
state(70,12);assert.equal(slider().disabled,true);
down(.7);up(.7);assert.deepEqual(actions(),[],'players without SEEK remain progress-only');
assert.equal(slider().value,350);
// A normal compact tile opens the same seek control in the firmware detail card.
receive=connection(m,'3333333333333333','4444444444444444');
configure(receive,'Music',1,[{...tile,slot:0}]);tick(500);
const box=info().tiles[0];
m._preview_touch(box.x+box.width/2,box.y+box.height/2,1);tick(120);
m._preview_touch(box.x+box.width/2,box.y+box.height/2,0);tick(300);
assert.equal(info().sliders.length,2,'detail card has seek and volume controls');
actions();state(60);assert.equal(slider().value,300);
down(.3);down(.6);up(.6);
command=actions();assert.equal(command.length,1);
assert.equal(command[0].service,'media_player.media_seek');
assert.ok(Math.abs(Number(command[0].data.seek_position)-120)<=2);
m.ccall('preview_action_response',null,['number','number','string'],[command[0].call_id,1,'']);
tick(6000);state(60);
assert.ok(slider().value>=590,'detail card also keeps an accepted seek through stale HA refreshes');

function seek(fraction) {
  tick(500);down(fraction);up(fraction);
  const requests=actions();assert.equal(requests.length,1);
  assert.equal(requests[0].service,'media_player.media_seek');
  return requests[0].call_id;
}
state(30);
let call=seek(.7);
m.ccall('preview_action_response',null,['number','number','string'],[call,0,'Player unavailable']);tick(1200);
assert.equal(slider().value,150,'failed seeks return to the reported position on the next progress update');
tick(4000);
call=seek(.7);
m.ccall('preview_action_response',null,['number','number','string'],[call,-1,'']);tick(1200);
assert.equal(slider().value,150,'read-only preview must not hold a seek that never reached HA');
assert.ok(!info().labels.some(l=>l.text==='Refused'),'read-only transport is not a device refusal');
call=seek(.7);tick(9000);
assert.equal(slider().value,150,'unanswered seeks expire instead of inventing playback indefinitely');

const old=seek(.4);call=seek(.7);
m.ccall('preview_action_response',null,['number','number','string'],[call,1,'']);
m.ccall('preview_action_response',null,['number','number','string'],[old,0,'Late failure']);tick(6000);
assert.ok(slider().value>=690,'an older response must not cancel the latest accepted seek');
state(10);
assert.equal(slider().value,50,'a fresh HA position from another controller takes over');

call=seek(.7);
m.ccall('preview_action_response',null,['number','number','string'],[call,1,'']);
state(0,14,'Another track');
assert.equal(slider().value,0,'track changes clear the accepted estimate');

call=seek(.7);
m.ccall('preview_action_response',null,['number','number','string'],[call,1,'']);
receive=connection(m,'5555555555555555','6666666666666666');
configure(receive,'Music',1,[{...tile,slot:0,o:{size:'full'},
  a:{...tile.a,media_title:'Another track'},x:{...tile.x,pos:0}}]);tick(500);
assert.equal(slider().value,0,'a new session of the same track cannot inherit an old seek');
console.log(`PASS ${width}x${width}: native seek, delayed state confirmation, failures, timeout, read-only transport, latest request, track and session guards`);
