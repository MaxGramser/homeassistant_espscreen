import { beforeEach, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { screenFixture } from './page-fixtures';
import { resizeChoices, resizeTile, select, setTileOption, state, tileSizeChoices, undo } from '../src/store';
import TileResize from '../src/components/TileResize.vue';
import TileInspector from '../src/components/TileInspector.vue';

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ states: {}, previews: [], capabilities: {} }))));
  state.dirty = false; state.busy = false; state.selected = null;
  state.inventory = { screens: [screenFixture({ id: 'test', name: 'Test', firmware: '0.3.1', online: true,
    tile_sizes: ['single', 'wide', 'full', 'tall', 'square'],
    layout: { title: 'Home', tiles: [{ entity: 'light.test', name: 'Test', slot: 0 }] },
  })], entities: [] };
  select('test');
});
const tile = () => state.layout!.tiles[0];
it('defaults to stable sizes even when firmware advertises larger rectangles', () => {
  expect(tileSizeChoices(tile())).toEqual(['single', 'wide', 'full']);
  expect(resizeChoices(tile(), 'rows')).toEqual([]);
  setTileOption(tile(), 'size', 'square');
  expect(tile().options?.size).not.toBe('square');
  expect(mount(TileResize, { props: { tile: tile() } }).find('.rows').exists()).toBe(false);
  expect(mount(TileInspector, { props: { tile: tile() } }).text()).not.toContain('2 × 2');
});
it('gates height on both the editor flag and the advertised firmware capability', () => {
  state.inventory.editor_features = { tall_tiles: true };
  expect(resizeChoices(tile(), 'rows')).toEqual(['single', 'tall']);
  state.inventory.screens[0].tile_sizes = ['single', 'wide', 'full'];
  expect(resizeChoices(tile(), 'rows')).toEqual(['single']);
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(false);
});
it('preserves experimental saved tiles when the environment flag is switched off', () => {
  state.inventory.editor_features = { tall_tiles: true };
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  const before = JSON.stringify(state.document);
  state.inventory.editor_features = { tall_tiles: false };
  expect(resizeChoices(tile(), 'rows')).toEqual([]);
  expect(resizeChoices(tile(), 'columns')).toEqual([]);
  expect(JSON.stringify(state.document)).toBe(before);
});
it('keeps the anchor, blocks occupied cells and gives each committed resize one undo step', () => {
  const original = JSON.stringify(state.document);
  expect(resizeTile(tile(), 'wide', 'columns')).toBe(true);
  expect(tile().slot).toBe(0);
  undo(); expect(JSON.stringify(state.document)).toBe(original);
  const neighbour = JSON.parse(JSON.stringify(state.document!.pages[0].tiles[0]));
  neighbour.id = 'neighbour'; neighbour.content = { kind: 'entity', entityId: 'light.other' };
  neighbour.placement.column = 1; state.document!.pages[0].tiles.push(neighbour);
  expect(resizeTile(tile(), 'wide', 'columns')).toBe(false);
  expect(state.document!.pages[0].tiles[1].placement.column).toBe(1);
});
it('supports keyboard resizing without invoking tile movement', async () => {
  const view = mount(TileResize, { props: { tile: tile() } });
  await view.get('.columns').trigger('keydown', { key: 'ArrowRight' });
  expect(tile().options?.size).toBe('wide');
  expect(tile().slot).toBe(0);
});
it('does not offer shrinking a forecast card below its required width', () => {
  const card = state.document!.pages[0].tiles[0];
  card.content = { kind: 'entity', entityId: 'weather.test' };
  card.appearance.display = 'forecast'; card.appearance.presentation = 'wide';
  card.placement.columns = 2;
  expect(resizeChoices(tile(), 'columns')).toEqual(['wide']);
});
it('commits a pointer resize once and rechecks the developer flag at release', async () => {
  state.inventory.editor_features = { tall_tiles: true };
  const host = document.createElement('div'); host.className = 'tile'; document.body.append(host);
  vi.spyOn(host, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
  const view = mount(TileResize, { props: { tile: tile() }, attachTo: host });
  const before = JSON.stringify(state.document);
  await view.get('.columns').trigger('pointerdown', { button: 0, pointerId: 1, clientX: 100, clientY: 50 });
  window.dispatchEvent(Object.assign(new Event('pointerup'), { pointerId: 1, clientX: 200, clientY: 50 }));
  expect(tile().options?.size).toBe('wide');
  undo(); expect(JSON.stringify(state.document)).toBe(before);
  await view.get('.rows').trigger('pointerdown', { button: 0, pointerId: 2, clientX: 50, clientY: 100 });
  state.inventory.editor_features = { tall_tiles: false };
  window.dispatchEvent(Object.assign(new Event('pointerup'), { pointerId: 2, clientX: 50, clientY: 200 }));
  expect(JSON.stringify(state.document)).toBe(before);
  view.unmount(); host.remove();
});
it('previews a pointer gesture without changing the document and cancels on Escape', async () => {
  const host = document.createElement('div'); host.className = 'tile'; document.body.append(host);
  vi.spyOn(host, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
  const view = mount(TileResize, { props: { tile: tile() }, attachTo: host });
  const before = JSON.stringify(state.document);
  await view.get('.columns').trigger('pointerdown', { button: 0, pointerId: 1, clientX: 100, clientY: 50 });
  window.dispatchEvent(Object.assign(new Event('pointermove'), { pointerId: 1, clientX: 200, clientY: 50, preventDefault() {} }));
  expect(JSON.stringify(state.document)).toBe(before);
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
  window.dispatchEvent(Object.assign(new Event('pointerup'), { pointerId: 1, clientX: 200, clientY: 50 }));
  expect(JSON.stringify(state.document)).toBe(before);
  view.unmount(); host.remove();
});

it('gaining height never opts into a default control, through either resize route', () => {
  state.inventory.editor_features = { tall_tiles: true };
  state.inventory.controls = { light: { default: 'toggle', choices: [{ key: 'toggle', label: 'Power' }, { key: 'none', label: 'None' }] } };
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  expect(tile().options?.controls).toBe('none');
  undo();
  setTileOption(tile(), 'size', 'square');
  expect(tile().options?.controls).toBe('none');
});

it('keeps already chosen controls when a wide tile gains height', () => {
  state.inventory.editor_features = { tall_tiles: true };
  setTileOption(tile(), 'size', 'wide');
  setTileOption(tile(), 'controls', 'brightness');
  expect(resizeTile(tile(), 'square', 'rows')).toBe(true);
  expect(tile().options?.controls).toBe('brightness');
});

it('resizes a Go to page tile by its edge without giving it controls (app 0.4.1)', () => {
  state.inventory.editor_features = { tall_tiles: true };
  state.inventory.screens[0] = screenFixture({ ...state.inventory.screens[0], layout: { title: 'Home', pages: 2, tiles: [{ entity: 'screen.page_2', name: 'More', slot: 0 }] } });
  select(null); select('test');
  expect(resizeChoices(tile(), 'rows')).toContain('tall');
  expect(state.toast).toBeNull();
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  expect(state.toast).toBeNull();
  expect(tile().options?.size).toBe('tall');
  expect(tile().options?.controls).toBeUndefined();
});
