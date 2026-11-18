import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { screenFixture } from './helpers/fixtures';
import LookTip from '../src/components/LookTip.vue';
import { addTile, startTile } from '../src/editor/tiles';
import { lookOf, lookOptions, startLook, startRange } from '../src/model/sensor-look';
import { useDocumentStore } from '../src/stores/document';
import { useEntitiesStore } from '../src/stores/entities';
import { useInspectorStore } from '../src/stores/inspector';
import { useInventoryStore } from '../src/stores/inventory';
import { useScreenStore } from '../src/stores/screen';
import { useSessionStore } from '../src/stores/session';
import { useUiStore } from '../src/stores/ui';

// A sensor starts as a meter (model/sensor-look.ts, docs/METER.md "The first look"): the look and range that suit what
// it measures, the plain value for a counter, a word or an older screen, and the tip beside it offers the other looks.
const all = () => true, old = (major: number, minor: number) => major === 0 && minor < 56;
const facts = (state: string, a: Record<string, unknown>) => ({ state, a });

describe('the look a sensor starts with', () => {
  it('fits what it measures', () => {
    expect(startLook('sensor.humidity', facts('54', { unit_of_measurement: '%', device_class: 'humidity', state_class: 'measurement' }), all))
      .toEqual({ display: 'meter' });
    expect(startLook('sensor.phone_battery', facts('81', { unit_of_measurement: '%', device_class: 'battery' }), all))
      .toEqual({ display: 'meter', meter: 'bar' });
    expect(startLook('sensor.living', facts('21.4', { unit_of_measurement: '°C', device_class: 'temperature', state_class: 'measurement' }), all))
      .toEqual({ display: 'meter', meter: 'tape', min: 10, max: 30 });
    expect(startLook('sensor.power', facts('840', { unit_of_measurement: 'W', device_class: 'power', state_class: 'measurement' }), all))
      .toEqual({ display: 'meter', meter: 'bar', min: 0, max: 1000 });
  });

  it('keeps the plain value for a counter, a word, no number now and an older screen', () => {
    expect(startLook('sensor.energy', facts('12043.2', { unit_of_measurement: 'kWh', device_class: 'energy', state_class: 'total_increasing' }), all)).toBeNull();
    expect(startLook('sensor.washer', facts('Washing', {}), all)).toBeNull();
    expect(startLook('sensor.living', facts('unavailable', { unit_of_measurement: '°C', device_class: 'temperature' }), all)).toBeNull();
    expect(startLook('sensor.humidity', facts('54', { unit_of_measurement: '%' }), old)).toBeNull();
    expect(startLook('binary_sensor.door', facts('on', {}), all)).toBeNull();
    expect(startLook('sensor.unknown', null, all)).toBeNull();
  });

  it('widens a room to hold a cold or hot value, in either unit', () => {
    expect(startRange(facts('-3.2', { unit_of_measurement: '°C', device_class: 'temperature' }))).toEqual([-5, 30]);
    expect(startRange(facts('71', { unit_of_measurement: '°F', device_class: 'temperature' }))).toEqual([50, 86]);
    expect(startRange(facts('54', { unit_of_measurement: '%' }))).toBeNull();
  });

  it('keeps the range across the meter looks and none on the graph or the value', () => {
    expect(lookOptions('ring', [10, 30])).toEqual({ display: 'meter', min: 10, max: 30 });
    expect(lookOptions('graph', [10, 30])).toEqual({ display: 'graph' });
    expect(lookOf({ display: 'meter' })).toBe('ring');
    expect(lookOf({ display: 'meter', meter: 'tape' })).toBe('tape');
    expect(lookOf(undefined)).toBe('standard');
    expect(lookOf({ display: 'watch' })).toBe('watch');
    expect(lookOptions('watch', [10, 30])).toEqual({ display: 'watch' });
  });
});

describe('a sensor added to a screen', () => {
  const slot = { template: '<div><slot /></div>' };
  const STUBS = { PopoverRoot: slot, PopoverPortal: slot, PopoverContent: slot, PopoverAnchor: true };
  const LIVE = { state: '21.4', a: { unit_of_measurement: '°C', device_class: 'temperature', state_class: 'measurement' } };
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ states: { 'sensor.living': LIVE }, previews: [], capabilities: {} }))));
    useScreenStore().selected = null;
    useInventoryStore().inventory = { screens: [screenFixture({ id: 'test', name: 'Test', firmware: '0.61.0', online: true,
      layout: { title: 'Home', tiles: [] } })], entities: [{ id: 'sensor.living', name: 'Living room', state: '21.4' }] } as any;
    useSessionStore().select('test');
  });
  const added = () => useDocumentStore().layout!.tiles.find((tile) => tile.entity === 'sensor.living')!;

  it('starts as a tape when the screen draws meters, the plain value when it does not', () => {
    useEntitiesStore().liveStates['sensor.living'] = LIVE as any;
    expect(startTile('sensor.living').options).toMatchObject({ display: 'meter', meter: 'tape', min: 10, max: 30 });
    useInventoryStore().inventory.screens[0].firmware = '0.55.0';
    expect(startTile('sensor.living').options?.display).toBeUndefined();
  });

  it('lands a percentage as a ring the page saves, without the ring written out', async () => {
    useEntitiesStore().liveStates['sensor.humidity'] = { state: '54', a: { unit_of_measurement: '%', device_class: 'humidity', state_class: 'measurement' } } as any;
    useInventoryStore().inventory.entities.push({ id: 'sensor.humidity', name: 'Humidity', state: '54' } as any);
    await addTile('sensor.humidity');
    const tile = useDocumentStore().layout!.tiles.find((item) => item.entity === 'sensor.humidity');
    expect(tile?.options?.display).toBe('meter');
    expect(tile?.options).not.toHaveProperty('meter');
  });

  it('reads the sensor first, lands as a meter and offers the other looks beside it', async () => {
    vi.useFakeTimers();
    const tip = mount(LookTip, { attachTo: document.body, global: { stubs: STUBS } });
    await addTile('sensor.living');
    expect(added().options).toMatchObject({ display: 'meter', meter: 'tape', min: 10, max: 30 });
    expect(useUiStore().lookTip).toEqual({ tileId: added().id });
    vi.advanceTimersByTime(500);
    await nextTick(); await nextTick();
    const looks = () => [...document.querySelectorAll<HTMLElement>('.look-tip .grow-set')];
    expect(looks().map((look) => look.dataset.look)).toEqual(['ring', 'tape', 'bar', 'graph', 'watch', 'standard']);
    expect(looks()[1].getAttribute('aria-checked')).toBe('true');
    // Pointed at, the ring is drawn on the tile with the same range; a click keeps the bar.
    looks()[0].dispatchEvent(new Event('pointerenter'));
    expect(useInspectorStore().optionPreview).toEqual({ tileId: added().id, key: 'display', value: 'meter', with: { min: 10, max: 30 } });
    looks()[2].click();
    await nextTick();
    expect(added().options).toMatchObject({ display: 'meter', meter: 'bar', min: 10, max: 30 });
    looks()[5].click();
    await nextTick();
    expect(added().options?.display).toBe('standard');
    expect(added().options?.min).toBeUndefined();
    (document.querySelector('.look-tip .grow-never') as HTMLElement).click();
    await nextTick();
    expect([useUiStore().lookTip, useUiStore().lookTips]).toEqual([null, false]);
    tip.unmount();
    vi.useRealTimers();
  });
});
