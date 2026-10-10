import { describe, expect, it } from 'vitest';
import { historyGeometry } from '../src/model/history-preview';
describe('recorder graph geometry', () => {
  it('keeps missing buckets as gaps and zero as a real value', () => {
    const result = historyGeometry({ start: 0, end: 400, values: [0, 2, null, 4], unit: '°C' })!;
    expect(result.paths).toHaveLength(2);
    expect(result.paths[0]).toContain('M27.25,47');
    expect(result.paths[1]).toContain('M172.75,3');
    expect(historyGeometry({ start: 0, end: 1, values: [null, null], unit: '' })).toBeNull();
  });
  it('retains the actual time and magnitude of extrema alongside the averages', () => {
    const result = historyGeometry({ start: 100, end: 500, values: [2, 2, 2, 2], hi: [8, 400], lo: [0, 200], unit: '' })!;
    expect(result.points).toEqual([{ x: 148.5, y: 3 }, { x: 51.5, y: 47 }]);
  });
});

describe('the history on a card (SensorHistory)', () => {
  it('says it is loading, draws the answer, and draws only the newest when the entity changes meanwhile', async () => {
    const { mount, flushPromises } = await import('@vue/test-utils');
    const { default: SensorHistory } = await import('../src/components/SensorHistory.vue');
    const { fakeApi, failure } = await import('./helpers/fake-api');
    const graph = (low: number) => ({ history: { start: 0, end: 400, values: [low, low + 2, low + 4, low + 6], unit: '°C' } });
    const api = fakeApi({ 'GET history-preview': ({ query }) => query.get('entity') === 'sensor.gone' ? failure(404, 'No recorder') : graph(1) });
    const slow = api.defer('GET history-preview');
    const card = mount(SensorHistory, { props: { entity: 'sensor.history_slow', hours: 6 } });
    expect(card.text()).toBe('Loading history…');
    await card.setProps({ entity: 'sensor.history_fast' });
    await flushPromises();
    expect(card.findAll('path')).toHaveLength(1);
    slow.resolve(graph(10));
    await flushPromises();
    expect(card.find('path').attributes('d')).toBe(historyGeometry(graph(1).history)!.paths[0]);
    await card.setProps({ entity: 'sensor.gone' });
    await flushPromises();
    expect(card.text()).toBe('No recorded history');
  });
});
