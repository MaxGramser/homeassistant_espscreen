import { beforeEach, expect, it, vi } from 'vitest';
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { screenFixture } from './helpers/fixtures';
import GrowTip from '../src/components/GrowTip.vue';
import { resizeTile } from '../src/editor/tiles';
import { useDocumentStore } from '../src/stores/document';
import { useInspectorStore } from '../src/stores/inspector';
import { useInventoryStore } from '../src/stores/inventory';
import { useScreenStore } from '../src/stores/screen';
import { useSessionStore } from '../src/stores/session';
import { useUiStore } from '../src/stores/ui';

// The tip beside a tile that grew (app 0.4.89): the sets its room offers, the one its growing chose first, a choice
// pointed at drawn on the tile, a click kept, Done and "Don't show again" letting it go.
const COVER = { default: 'buttons', choices: ['buttons', 'position', 'tilt', 'buttons_tilt', 'position_tilt', 'none'].map((key) => ({ key, label: `L:${key}` })) };
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ states: {}, previews: [], capabilities: {} }))));
  useScreenStore().selected = null;
  useInventoryStore().inventory = { screens: [screenFixture({ id: 'test', name: 'Test', firmware: '0.56.0', online: true,
    tile_sizes: ['single', 'wide', 'full', 'tall', 'square'], layout: { title: 'Home', tiles: [{ entity: 'cover.blind', name: 'Blind', slot: 0 }] } })],
    entities: [], editor_features: { tall_tiles: true }, controls: { cover: COVER } };
  useSessionStore().select('test');
});
// jsdom can't place a popover (tests/setup.ts): the tip's content is drawn in place, as it is when open.
const slot = { template: '<div><slot /></div>' };
const STUBS = { PopoverRoot: slot, PopoverPortal: slot, PopoverContent: slot, PopoverAnchor: true };
const view = () => mount(GrowTip, { attachTo: document.body, global: { stubs: STUBS } });
const tile = () => useDocumentStore().layout!.tiles[0];
const sets = () => [...document.querySelectorAll('.grow-set')];

// It comes when the hand rests after the release, not while it is still sizing.
async function rest() {
  expect(document.querySelector('.grow-tip')).toBeNull();
  vi.advanceTimersByTime(800);
  await nextTick(); await nextTick();
}
beforeEach(() => { vi.useFakeTimers(); return () => vi.useRealTimers(); });

it('lists what the room offers, richest first, previews a choice and keeps a click', async () => {
  const tip = view();
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  await nextTick();
  await rest();
  expect(sets().map((set) => set.querySelector('.grow-name')!.textContent)).toEqual(['L:position_tilt', 'L:buttons_tilt', 'L:buttons', 'L:position', 'L:tilt', 'No controls']);
  expect(sets()[0].getAttribute('aria-checked')).toBe('true');
  sets()[1].dispatchEvent(new Event('pointerenter'));
  expect(useInspectorStore().optionPreview).toEqual({ tileId: tile().id, key: 'controls', value: 'buttons_tilt' });
  (sets()[5] as HTMLElement).click();
  await nextTick(); await nextTick();
  expect(tile().options?.controls).toBe('none');
  expect(useInspectorStore().optionPreview).toBeNull();
  (document.querySelector('.grow-tip .btn.primary') as HTMLElement).click();
  await nextTick(); await nextTick();
  expect(useUiStore().growTip).toBeNull();
  expect(document.querySelector('.grow-tip')).toBeNull();
  tip.unmount();
});

it("stays away once told not to show again, while the richer default still comes", async () => {
  const tip = view();
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  await nextTick();
  await rest();
  (document.querySelector('.grow-never') as HTMLElement).click();
  await nextTick(); await nextTick();
  expect(useUiStore().growTips).toBe(false);
  useDocumentStore().undo();
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  await nextTick(); await nextTick();
  expect(tile().options?.controls).toBe('position_tilt');
  expect(document.querySelector('.grow-tip')).toBeNull();
  tip.unmount();
});

it('stays away when the user moves on before it comes, and goes when the size is undone', async () => {
  const tip = view();
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  await nextTick();
  window.dispatchEvent(new Event('pointerdown'));
  await rest();
  expect(document.querySelector('.grow-tip')).toBeNull();
  expect(useUiStore().growTip).toBeNull();
  expect(tile().options?.controls).toBe('position_tilt');
  useDocumentStore().undo();
  expect(resizeTile(tile(), 'tall', 'rows')).toBe(true);
  await nextTick();
  await rest();
  expect(document.querySelector('.grow-tip')).not.toBeNull();
  useDocumentStore().undo();
  await nextTick(); await nextTick();
  expect(document.querySelector('.grow-tip')).toBeNull();
  tip.unmount();
});
