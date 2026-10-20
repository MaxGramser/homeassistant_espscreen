import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';
const m=await createModule({wasmBinary:readFileSync(new URL('../src/wasm/firmware_preview.wasm',import.meta.url))});
assert.equal(m._preview_init(800,480,133,4,4),1);
m.ccall('preview_media_screen',null,['string'],[JSON.stringify({media_screen:{entity:'media_player.test',library_entry:'test',starting_volume:.3}})]);
const receive=connection(m);
configure(receive,'Music Assistant',1,[{entity:'media_player.test',slot:0,name:'Test speaker',state:'playing',o:{size:'full'},a:{media_title:'Test track',media_artist:'Test artist',volume_level:.2,supported_features:16777215,media_duration:240,media_position:30}}]);
let ms=0;function tick(delta=200){ms+=delta;m._preview_time(ms,1789401840,0);m._preview_render();}
tick();tick();
const tree=()=>JSON.parse(m.ccall('preview_layout','string',[],[]));
const text=JSON.stringify(tree());
for(const label of ['Library','Favorites','Queue','Speakers','More'])assert.ok(text.includes(label),label+' must appear on the native main page');
const source=readFileSync(new URL('generated/firmware_renderer_manifest.h',import.meta.url),'utf8').match(/SHA256 "([a-f0-9]+)"/)[1];
assert.equal(JSON.parse(m.ccall('preview_diagnostics','string',[],[])).source,source,'WASM must match current sources');
// Native toolbar navigation remains internal while device actions are disabled.
ms+=300;m._preview_time(ms,1789401840,0);m._preview_touch(213,136,1);tick(120);
m._preview_touch(213,136,0);tick();tick();
assert.ok(JSON.stringify(tree()).includes('Playlists'),'Favorites opens its categories in the actual renderer');
m._preview_touch(35,35,1);tick(120);m._preview_touch(35,35,0);tick();tick();
// A different/stock screen must not inherit native controls.
m.ccall('preview_media_screen',null,['string'],['{}']);tick();tick();
assert.ok(!JSON.stringify(tree()).includes('Favorites'),'disabling native configuration restores stock player');
console.log('Native media main player and stock-screen isolation passed at 800x480.');
