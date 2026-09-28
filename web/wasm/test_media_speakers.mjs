// Real LVGL presses, group snapshots, volume commands and navigation.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const width = Number(process.env.PREVIEW_WIDTH || 480), height = Number(process.env.PREVIEW_HEIGHT || width);
const m = await createModule({ wasmBinary: readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url)) });
assert.equal(m._preview_init(width, height, Number(process.env.PREVIEW_DPI || (width === 720 ? 254 : 170)), 2, 3), 1);
const receive = connection(m);
let ms = 0;
function tick(n = 300) { for (let t = 0; t < n; t += 20) { ms += 20; m._preview_time(ms, 1789401840, 0); m._preview_render(); } }
const info = () => JSON.parse(m.ccall('preview_diagnostics', 'string', [], []));
function capture(path){
  const start=m._preview_frame(),rgb=Buffer.alloc(width*height*3);
  for(let i=0;i<width*height;i++)rgb.set(m.HEAPU8.subarray(start+i*4,start+i*4+3),i*3);
  writeFileSync(path,Buffer.concat([Buffer.from(`P6\n${width} ${height}\n255\n`),rgb]));
}
const actions = () => { const result=[]; for (;;) { const value=m.ccall('preview_next_action','string',[],[]); if (!value) return result; result.push(JSON.parse(value)); } };
function press(box, duration = 120) { const x=box.x+box.width/2,y=box.y+box.height/2; tick(); m._preview_touch(x,y,1); tick(duration); m._preview_touch(x,y,0); tick(100); }
const words = text => info().labels.filter(l => l.text === text).at(-1);
const mute = () => info().icons.filter(i => i.x < width/4).sort((a,b)=>b.y-a.y)[0];
const tile={entity:'media_player.main',name:'Music',state:'playing',a:{supported_features:12,volume_level:.32,is_volume_muted:false}};
configure(receive,'Music',1,[{...tile,slot:0,o:{size:'full'}}]);
tick();
press(mute(),850);
assert.deepEqual(actions(),[], 'unsupported player long press sends no mute or group request');
receive({...tile,op:'state',i:0,a:{...tile.a,supported_features:524300}});
tick();
press(mute(),850);
let requests=actions();
assert.equal(requests.length,1);
assert.equal(requests[0].service,'esphome.screen_media_groups');
assert.equal(requests[0].event,true);
assert.equal(requests[0].data.schema,'1');
assert.ok(words('Speakers'));
let request=requests[0];
const snapshot={op:'media_groups',schema:1,e:tile.entity,group:tile.entity,name:'Kitchen + Dining',gp:0,group_pages:1,page:0,pages:1,
  groups:[{e:tile.entity,n:'Kitchen + Dining'},{e:'media_player.office',n:'Office'}],
  speakers:[{e:tile.entity,n:'Kitchen',v:32,muted:false,enabled:true},{e:'media_player.dining',n:'Dining',v:18,muted:false,enabled:true}]};
receive({...snapshot,view:Number(request.data.view)}); tick();
assert.ok(words('Kitchen') && words('Dining'));
assert.equal(info().dropdowns.length,1,'group selector is a native LVGL dropdown');
assert.equal(info().dropdowns[0].codepoint,0xF0140);
assert.ok(info().dropdowns[0].symbol_present,'dropdown uses a real bundled down-chevron glyph');
const sliders=info().sliders.slice(-2);
assert.equal(sliders[1].value,180);
assert.ok(sliders[1].y-sliders[0].y<=height/4,'speaker rows stay compact instead of stretching over the page');
if(process.env.PREVIEW_SCREENSHOT)capture(process.env.PREVIEW_SCREENSHOT.replace(/\.ppm$/,'-rows.ppm'));
const slider=sliders[1], y=slider.y+slider.height/2;
m._preview_touch(slider.x+slider.width*.18,y,1);tick(120);
m._preview_touch(slider.x+slider.width*.4,y,1);tick(120);
m._preview_touch(slider.x+slider.width*.4,y,0);tick(100);
requests=actions();
const command=requests.find(r=>r.service==='media_player.volume_set');
assert.ok(command,'release sends one native volume command');
assert.equal(command.data.entity_id,'media_player.dining');
assert.ok(Math.abs(Number(command.data.volume_level)-.4)<.03);
assert.equal(requests.filter(r=>!r.event).length,1);
m.ccall('preview_action_response',null,['number','number','string'],[command.call_id,1,'']);
// More than one bounded packet still becomes a single native option list.
tick(2100);request=actions().filter(r=>r.event).at(-1);
assert.ok(request);
receive({...snapshot,group_pages:2,groups:[...snapshot.groups,{e:'media_player.hall',n:'Hall'},{e:'media_player.studio',n:'Studio'}],view:Number(request.data.view)});tick();
request=actions().filter(r=>r.event).at(-1);
assert.equal(request.data.gp,'1');
receive({...snapshot,gp:1,group_pages:2,groups:[{e:'media_player.garden',n:'Garden'}],view:Number(request.data.view)});tick();
assert.equal(info().dropdowns[0].options.split('\n').length,5);
// Expand the dropdown and inspect another existing group. This never joins,
// transfers playback or calls a service.
press(info().dropdowns[0]);
requests=actions();request=requests.filter(r=>r.event).at(-1);
if(request){receive({...snapshot,view:Number(request.data.view)});tick();}
assert.equal(info().dropdowns[0].open,true);
assert.ok(info().dropdowns[0].options.includes('Office'));
assert.equal(info().sliders.length,sliders.length+1,'floating menu keeps speaker sliders underneath');
assert.equal(info().dropdowns[0].codepoint,0xF0143);
assert.ok(info().dropdowns[0].symbol_present);
if(process.env.PREVIEW_SCREENSHOT)capture(process.env.PREVIEW_SCREENSHOT);
const rows=info().dropdowns[0].rows;
press({...rows,y:rows.y+rows.height});
requests=actions();request=requests.at(-1);
assert.ok(request,JSON.stringify({rows,dropdown:info().dropdowns}));
assert.ok(requests.every(r=>r.event));
assert.equal(request.data.group,'media_player.office');
receive({...snapshot,group:'media_player.office',name:'Office',speakers:[{e:'media_player.office',n:'Office speaker',v:51,enabled:true,muted:false}],view:Number(request.data.view)});tick();
assert.ok(words('Office speaker'));
// A stale reply for the previous dropdown cannot replace this group's rows.
receive({...snapshot,view:Number(request.data.view)-1});tick();
assert.ok(words('Office speaker'));
tick(8000);actions();
assert.ok(words('Unavailable'),'lost group feed removes actionable sliders');
const back=info().icons.filter(i=>i.y<height/4 && i.x<width/4).at(-1);
press(back);tick();
assert.equal(words('Speakers'),undefined);
assert.equal(m._preview_page(),0);
assert.ok(actions().every(r=>r.event));
console.log(`PASS ${width}x${height}: capability guard, long press without mute, live group rows, individual volume, picker, stale reply and timeout, back`);
