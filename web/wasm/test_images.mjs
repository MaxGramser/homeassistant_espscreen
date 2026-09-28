// Actual firmware image requests, ESPHome BMP decoding and LVGL pixels.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import createModule from '../src/wasm/firmware_preview.js';
import { connection, configure } from './test_protocol.mjs';

const m = await createModule({ wasmBinary: readFileSync(new URL('../src/wasm/firmware_preview.wasm', import.meta.url)) });
const width = Number(process.env.PREVIEW_WIDTH || 480), height = Number(process.env.PREVIEW_HEIGHT || 480);
assert.equal(m._preview_init(width, height, Number(process.env.PREVIEW_DPI || 170), 2, 3), 1);
let ms = 0;
let receive = connection(m), revision = 1;
function layout(tiles) {
  const key = (++revision).toString(16).padStart(16, '0');
  receive = connection(m, key, key);
  configure(receive, 'Images', 1, tiles);
}
function tick(n = 300) { ms += n; m._preview_time(ms, 1789401840, 0); m._preview_render(); }
const diagnostics = () => JSON.parse(m.ccall('preview_diagnostics', 'string', [], []));
const action = () => JSON.parse(m.ccall('preview_next_action', 'string', [], []));
const nextImage = () => JSON.parse(m.ccall('preview_next_image', 'string', [], []));
const tile = { entity: 'media_player.test', name: 'Music', slot: 0, state: 'playing',
  a: { media_title: 'Track', supported_features: 0 }, x: { pic: 'picture1', artist: 'Artist' }, o: { size: 'full' } };

function bmp(w, h, palette = false) {
  const offset = palette ? 62 : 54, stride = Math.ceil(w * (palette ? 1 : 3) / 4) * 4;
  const bytes = Buffer.alloc(offset + stride * h);
  bytes.write('BM'); bytes.writeUInt32LE(bytes.length, 2); bytes.writeUInt32LE(offset, 10);
  bytes.writeUInt32LE(40, 14); bytes.writeUInt32LE(w, 18); bytes.writeUInt32LE(h, 22);
  bytes.writeUInt16LE(1, 26); bytes.writeUInt16LE(palette ? 8 : 24, 28);
  if (palette) { bytes.writeUInt32LE(2, 46); bytes[56] = 255; bytes[59] = 255; }
  // Bottom-up BMP: upper half red, lower half green. Padding is non-pixel data.
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const p = offset + y * stride + x * (palette ? 1 : 3);
    if (palette) bytes[p] = y < h / 2 ? 1 : 0;
    else bytes[p + (y < h / 2 ? 1 : 2)] = 255;
  }
  return bytes;
}
function deliver(request, body) {
  const pointer = m._preview_image_buffer(request.id, body.length);
  assert.ok(pointer);
  m.HEAPU8.set(body, pointer);
  assert.equal(m._preview_image_ready(request.id, 1), 1);
  tick();
}
function expectImage() {
  const images = diagnostics().images;
  assert.equal(images.length, 1, JSON.stringify(diagnostics()));
  const image = images[0], pointer = m._preview_frame();
  const pixel = y => { const start = pointer + (y * width + image.x + Math.floor(image.width / 2)) * 4; return [...m.HEAPU8.subarray(start, start + 3)]; };
  assert.deepEqual(pixel(image.y + Math.floor(image.height / 4)), [255, 0, 0]);
  assert.deepEqual(pixel(image.y + Math.floor(image.height * 3 / 4)), [0, 255, 0]);
  return image;
}

layout([tile]);
tick(); tick();
const cover = action();
assert.equal(cover.service, 'esphome.screen_camera'); assert.equal(cover.event, true);
assert.equal(cover.data.entity, tile.entity);
const size = Number(cover.data.size);
assert.ok(size >= 48 && size <= 320);
receive({ op: 'camera', t: 'cover', e: tile.entity, u: 'http://firmware-preview.invalid/abcdefghijklmnop.bmp', view: Number(cover.data.view) });
tick(800);
deliver(nextImage(), bmp(size, size));
assert.equal(expectImage().width, size, 'firmware-selected artwork dimensions');
assert.equal(m.ccall('preview_next_action', 'string', [], []), '', 'cover is cached until the track changes');

// Tap the firmware image itself. Enlargement and return are LVGL operations,
// with no browser overlay and no playback command.
function tap(x, y) {
  tick(); m._preview_touch(x, y, 1); tick(120); m._preview_touch(x, y, 0); tick();
}
const beforeZoom = diagnostics().images[0];
tap(beforeZoom.x + beforeZoom.width / 2, beforeZoom.y + beforeZoom.height / 2);
assert.deepEqual(diagnostics().images,[beforeZoom],'loading full art never enlarges the rounded thumbnail');
tick();
const fullArt=action();
assert.equal(fullArt.service,'esphome.screen_camera');
assert.equal(fullArt.data.full,'1');
assert.equal(Number(fullArt.data.size),Math.min(width,height));
receive({op:'camera',t:'cover',e:tile.entity,u:'http://firmware-preview.invalid/fullsizeartcover.bmp',view:Number(fullArt.data.view)});
tick(800);
deliver(nextImage(),bmp(Number(fullArt.data.size),Number(fullArt.data.size)));
const fullImage=diagnostics().images.at(-1);
assert.equal(fullImage.width,Math.min(width,height));
assert.equal(fullImage.scale,256,'full-resolution artwork replaces the thumbnail');
tap(width / 2, height / 2);
assert.equal(diagnostics().images.length, 1, 'second tap returns to the same player');
assert.deepEqual(diagnostics().images[0], beforeZoom);
assert.equal(m.ccall('preview_next_action', 'string', [], []), '', 'viewing art changes no playback');

// An old image response must not attach to a different track/layout.
const { o, slot, ...state } = tile;
receive({ ...state, op: 'state', i: 0, x: { ...tile.x, pic: 'picture2' } });
tick(); tick();
const second = action();
receive({ op: 'camera', t: 'cover', e: tile.entity, u: 'http://firmware-preview.invalid/qrstuvwxyzabcdef.bmp', view: Number(second.data.view) });
tick(800);
const stale = nextImage();
layout([]); tick(); tick();
assert.equal(m._preview_image_buffer(stale.id, 100), 0, 'released downloads reject late bytes');
assert.equal(m._preview_image_ready(stale.id, 1), 0);
assert.equal(diagnostics().images.length, 0);

// Compact album-art tiles request the firmware's shared strip, decoded with
// the same 8-bit BMP support as ESPHome. Include a padded row.
layout([{ ...tile, x: { ...tile.x, pic: 'picture3' }, o: { display: 'cover' } }]);
tick(); tick();
const live = action();
assert.equal(live.data.tiles, tile.entity);
assert.equal(live.data.entity, undefined);
const side = Number(live.data.size);
receive({ op: 'camera', t: 'live', e: tile.entity, u: 'http://firmware-preview.invalid/abcdefghijklmnop.bmp', view: Number(live.data.view) });
tick(800);
deliver(nextImage(), bmp(side, side, true));
expectImage();

// The next track must replace full-screen pixels without a blank frame or a
// thumbnail flash. Reusing the downloader must not overwrite the visible copy.
layout([{...tile,x:{...tile.x,pic:'picture-live'}}]); tick(); tick();
const initial=action();
receive({op:'camera',t:'cover',e:tile.entity,u:'http://firmware-preview.invalid/initialtrackcover.bmp',view:Number(initial.data.view)});
tick(800); deliver(nextImage(),bmp(Number(initial.data.size),Number(initial.data.size)));
const art=diagnostics().images[0]; tap(art.x+art.width/2,art.y+art.height/2);tick();
const initialFull=action();
receive({op:'camera',t:'cover',e:tile.entity,u:'http://firmware-preview.invalid/initialtrackfullart.bmp',view:Number(initialFull.data.view)});
tick(800);deliver(nextImage(),bmp(width,height));
const pixel=()=>{const p=m._preview_frame()+(Math.floor(height/4)*width+Math.floor(width/2))*4;return [...m.HEAPU8.subarray(p,p+3)];};
assert.deepEqual(pixel(),[255,0,0]);
receive({...state,op:'state',i:0,a:{...tile.a,media_title:'Next track'},x:{...tile.x,pic:'picture-next'}}); tick();tick();
const changed=action(); assert.equal(changed.data.full,'1');
assert.deepEqual(pixel(),[255,0,0],'previous art remains visible during the next request');
receive({op:'camera',t:'cover',e:tile.entity,u:'http://firmware-preview.invalid/nexttrackfullart.bmp',view:Number(changed.data.view)});
tick(800);
assert.deepEqual(pixel(),[255,0,0],'releasing the shared download buffer cannot change visible pixels');
const blue=bmp(width,height);
for(let p=54;p<blue.length;p+=3){blue[p]=255;blue[p+1]=0;blue[p+2]=0;}
deliver(nextImage(),blue);
assert.deepEqual(pixel(),[0,0,255],'the complete new image replaces the previous track');
assert.equal(diagnostics().images.at(-1).scale,256);
tap(width/2,height/2);
assert.ok(diagnostics().images.length<=1,'tap returns after a live artwork swap');
console.log(`PASS ${width}x${height}: firmware cover and strip requests, ESPHome 24/8-bit decoding, LVGL artwork pixels, caching and stale download rejection`);
