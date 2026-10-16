import { beforeEach, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { screenFixture } from './helpers/fixtures';
import TileResize from '../src/components/TileResize.vue';
import TileInspector from '../src/components/TileInspector.vue';
import { useUiStore } from "../src/stores/ui";
import { useScreenStore } from "../src/stores/screen";
import { useSessionStore } from "../src/stores/session";
import { useInventoryStore } from "../src/stores/inventory";
import { resizeChoices, resizeTile, setTileOption, tileSizeChoices } from "../src/editor/tiles";
import { useDocumentStore } from "../src/stores/document";

let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => { doc = useDocumentStore(); });

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ states: {}, previews: [], capabilities: {} }))));
  useScreenStore().selected = null;
  useInventoryStore().inventory = { screens: [screenFixture({ id: 'test', name: 'Test', firmware: '0.3.1', online: true,
    tile_sizes: ['single', 'wide', 'full', 'tall', 'square'],
    layout: { title: 'Home', tiles: [{ entity: 'light.test', name: 'Test', slot: 0 }] },
  })], entities: [] };
  useSessionStore().select('test');
});
const tile = () => doc.layout!.tiles[0];
it('defaults to stable sizes even when firmware advertises larger rectangles', () => {
  expect(tileSizeChoices(tile())).toEqual(['single', 'wide', 'full']);
  expect(resizeChoices(tile(), 'rows')).toEqual([]);
  setTileOption(tile(), 'size', 'square');
  expect(tile().options?.size).not.toBe('square');
  expect(mount(TileResize, { props: { tile: tile() } }).find('.rows').exists()).toBe(false);
  expect(mount(TileInspector, { props: { tile: tile() } }).text()).not.toContain('2 × 2');
});
it('gates height on both the editor flag and the advertised firmware capability', () => {
  useInventoryStore().inventory.editor_features = { tall_tiles: true };
  expect(resizeChoices(tile(), 'rows')).toEqual(['single', 'tall']);
  useInventoryStore().inventory.screens[0].tile_sizes = ['single', 'wide', 'full'];
  expect(resizeChoices(tile(), 'rows')).toEqual(['single']);
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(false);
});
it('preserves experimental saved tiles when the environment flag is switched off', () => {
  useInventoryStore().inventory.editor_features = { tall_tiles: true };
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  const before = JSON.stringify(doc.document);
  useInventoryStore().inventory.editor_features = { tall_tiles: false };
  expect(resizeChoices(tile(), 'rows')).toEqual([]);
  expect(resizeChoices(tile(), 'columns')).toEqual([]);
  expect(JSON.stringify(doc.document)).toBe(before);
});
it('keeps the anchor, blocks occupied cells and gives each committed resize one undo step', () => {
  const original = JSON.stringify(doc.document);
  expect(resizeTile(tile(), 'wide', 'columns')).toBe(true);
  expect(tile().slot).toBe(0);
  doc.undo(); expect(JSON.stringify(doc.document)).toBe(original);
  const neighbour = JSON.parse(JSON.stringify(doc.document!.pages[0].tiles[0]));
  neighbour.id = 'neighbour'; neighbour.content = { kind: 'entity', entityId: 'light.other' };
  neighbour.placement.column = 1; doc.document!.pages[0].tiles.push(neighbour);
  expect(resizeTile(tile(), 'wide', 'columns')).toBe(false);
  expect(doc.document!.pages[0].tiles[1].placement.column).toBe(1);
});
it('supports keyboard resizing without invoking tile movement', async () => {
  const view = mount(TileResize, { props: { tile: tile() } });
  await view.get('.columns').trigger('keydown', { key: 'ArrowRight' });
  expect(tile().options?.size).toBe('wide');
  expect(tile().slot).toBe(0);
});
it('does not offer shrinking a forecast card below its required width', () => {
  const card = doc.document!.pages[0].tiles[0];
  card.content = { kind: 'entity', entityId: 'weather.test' };
  card.appearance.display = 'forecast'; card.appearance.presentation = 'wide';
  card.placement.columns = 2;
  expect(resizeChoices(tile(), 'columns')).toEqual(['wide']);
});
it('commits a pointer resize once and rechecks the developer flag at release', async () => {
  useInventoryStore().inventory.editor_features = { tall_tiles: true };
  const host = document.createElement('div'); host.className = 'tile'; document.body.append(host);
  vi.spyOn(host, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
  const view = mount(TileResize, { props: { tile: tile() }, attachTo: host });
  const before = JSON.stringify(doc.document);
  await view.get('.columns').trigger('pointerdown', { button: 0, pointerId: 1, clientX: 100, clientY: 50 });
  window.dispatchEvent(Object.assign(new Event('pointerup'), { pointerId: 1, clientX: 200, clientY: 50 }));
  expect(tile().options?.size).toBe('wide');
  doc.undo(); expect(JSON.stringify(doc.document)).toBe(before);
  await view.get('.rows').trigger('pointerdown', { button: 0, pointerId: 2, clientX: 50, clientY: 100 });
  useInventoryStore().inventory.editor_features = { tall_tiles: false };
  window.dispatchEvent(Object.assign(new Event('pointerup'), { pointerId: 2, clientX: 50, clientY: 200 }));
  expect(JSON.stringify(doc.document)).toBe(before);
  view.unmount(); host.remove();
});
it('previews a pointer gesture without changing the document and cancels on Escape', async () => {
  const host = document.createElement('div'); host.className = 'tile'; document.body.append(host);
  vi.spyOn(host, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
  const view = mount(TileResize, { props: { tile: tile() }, attachTo: host });
  const before = JSON.stringify(doc.document);
  await view.get('.columns').trigger('pointerdown', { button: 0, pointerId: 1, clientX: 100, clientY: 50 });
  window.dispatchEvent(Object.assign(new Event('pointermove'), { pointerId: 1, clientX: 200, clientY: 50, preventDefault() {} }));
  expect(JSON.stringify(doc.document)).toBe(before);
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
  window.dispatchEvent(Object.assign(new Event('pointerup'), { pointerId: 1, clientX: 200, clientY: 50 }));
  expect(JSON.stringify(doc.document)).toBe(before);
  view.unmount(); host.remove();
});

it('a tile that grows by its edge shows the richest set it has room for, and the tip asks (app 0.4.89)', () => {
  useInventoryStore().inventory.editor_features = { tall_tiles: true };
  useInventoryStore().inventory.controls = { light: { default: 'toggle', choices: [{ key: 'toggle', label: 'Power' }, { key: 'brightness', label: 'Brightness' }, { key: 'none', label: 'None' }] } };
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  expect(tile().options?.controls).toBe('brightness');
  expect(useUiStore().growTip).toMatchObject({ before: 'single', size: 'tall', applied: 'brightness' });
  doc.undo();
  expect(tile().options?.controls).toBeUndefined();
  // The inspector's own route keeps what the tile had: nothing is suggested there.
  setTileOption(tile(), 'size', 'square');
  expect(tile().options?.controls).toBe('none');
});

const COVER = { default: 'buttons', choices: ['buttons', 'position', 'tilt', 'buttons_tilt', 'position_tilt', 'none'].map((key) => ({ key, label: key })) };
const cover = (options = {}) => {
  useInventoryStore().inventory.editor_features = { tall_tiles: true };
  useInventoryStore().inventory.controls = { cover: COVER };
  useInventoryStore().inventory.screens[0] = screenFixture({ ...useInventoryStore().inventory.screens[0], layout: { title: 'Home', tiles: [{ entity: 'cover.blind', name: 'Blind', slot: 0, options }] } });
  useSessionStore().select(null); useSessionStore().select('test');
};
it.each([
  [{ size: 'wide' }, 'square', 'position_tilt'],
  [{ size: 'wide', controls: 'buttons' }, 'square', 'buttons_tilt'],
  [{ size: 'wide', controls: 'position' }, 'square', 'position_tilt'],
  [{}, 'tall', 'position_tilt'],
  // A cover lays its controls out by its room (firmware 0.57.0): the slats come on a card one row high too.
  [{}, 'wide', 'position_tilt'],
])('a blind that grows keeps what it drew and gains what fits: %j to %s', (options, size, controls) => {
  cover(options);
  expect(resizeTile(tile(), size as never, size === 'wide' ? 'columns' : 'rows')).toBe(true);
  expect(tile().options?.controls ?? 'buttons').toBe(controls);
  expect(useUiStore().growTip?.size).toBe(size);
});
it('a tile that shrinks keeps what it has, and no tip shows', () => {
  cover({ size: 'square', controls: 'buttons_tilt' });
  expect(resizeTile(tile(), 'wide', 'rows')).toBe(true);
  expect(tile().options?.controls).toBe('buttons_tilt');
  expect(useUiStore().growTip).toBeNull();
});
it('a tile with a face without controls keeps it as it grows, and no tip shows', () => {
  cover({ display: 'watch' });
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  expect(tile().options?.display).toBe('watch');
  expect(tile().options?.controls ?? 'none').toBe('none');
  expect(useUiStore().growTip).toBeNull();
});

it('keeps already chosen controls when a wide tile gains height', () => {
  useInventoryStore().inventory.editor_features = { tall_tiles: true };
  setTileOption(tile(), 'size', 'wide');
  setTileOption(tile(), 'controls', 'brightness');
  expect(resizeTile(tile(), 'square', 'rows')).toBe(true);
  expect(tile().options?.controls).toBe('brightness');
});

it('resizes a Go to page tile by its edge without giving it controls (app 0.4.1)', () => {
  useInventoryStore().inventory.editor_features = { tall_tiles: true };
  useInventoryStore().inventory.screens[0] = screenFixture({ ...useInventoryStore().inventory.screens[0], layout: { title: 'Home', pages: 2, tiles: [{ entity: 'screen.page_2', name: 'More', slot: 0 }] } });
  useSessionStore().select(null); useSessionStore().select('test');
  expect(resizeChoices(tile(), 'rows')).toContain('tall');
  expect(useUiStore().notice).toBeNull();
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  expect(useUiStore().notice).toBeNull();
  expect(tile().options?.size).toBe('tall');
  expect(tile().options?.controls).toBeUndefined();
});

it('grows the map tile by its edge without giving it controls, so the add-on saves it', () => {
  useInventoryStore().inventory.editor_features = { tall_tiles: true };
  useInventoryStore().inventory.screens[0] = screenFixture({ id: 'test', name: 'Test', firmware: '0.3.1', online: true,
    tile_sizes: ['single', 'wide', 'full', 'tall', 'square'], layout: { title: 'Home', tiles: [{ entity: 'screen.map', name: '', slot: 0, options: { size: 'wide', display: 'map' } }] } });
  useScreenStore().selected = null; useSessionStore().select('test');
  // As the editor makes it: the built-in card by its name (the fixture reads every entity as one of Home Assistant's).
  doc.document!.pages[0].tiles[0].content = { kind: 'builtin', name: 'map' };
  expect(resizeTile(tile(), 'square', 'rows')).toBe(true);
  expect(tile().options?.size).toBe('square');
  expect(tile().options?.controls).toBeUndefined();
});

const pluginTile = async () => {
  const { usePluginsStore } = await import("../src/stores/plugins");
  usePluginsStore().index = [{ id: 'waste_collection', tiles: [{ id: 'next', min: '1x1', max: '2x2' }] }] as never;
  useInventoryStore().inventory.editor_features = { tall_tiles: true, plugins: true };
  doc.document!.pages[0].tiles[0].content = { kind: 'plugin', plugin: 'waste_collection', tile: 'next' } as never;
  expect(tile().entity).toBe('plugin:waste_collection.next');
};

it("resizes a plugin's tile by its edge without giving it controls (GitHub #224)", async () => {
  await pluginTile();
  expect(resizeTile(tile(), 'wide', 'columns')).toBe(true);
  expect(resizeTile(tile(), 'square', 'rows')).toBe(true);
  expect(tile().options?.size).toBe('square');
  expect(tile().options?.controls).toBeUndefined();
});

it("frees a plugin's tile that got controls before when it is resized (GitHub #224)", async () => {
  await pluginTile();
  doc.document!.pages[0].tiles[0].interaction = { controls: 'none' } as never;
  expect(resizeTile(tile(), 'wide', 'columns')).toBe(true);
  expect(tile().options?.size).toBe('wide');
  expect(tile().options?.controls).toBeUndefined();
});
