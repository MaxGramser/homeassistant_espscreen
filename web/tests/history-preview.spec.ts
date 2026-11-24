import { describe, expect, it } from 'vitest';
import { cardGraph } from '../src/model/history-preview';
describe('the graph on a card (render_graph)', () => {
  // The points themselves are the firmware's: tests/test_editor_parity.py (Graph) compares them with render_graph.
  it('runs one line past a missing average, from the bottom to the top, with the area under it closed', () => {
    const graph = cardGraph([0, 2, null, 4], 200, 50, 2)!;
    expect(graph.line.startsWith('M1,48')).toBe(true);
    expect(graph.line.endsWith('L26,3')).toBe(true);
    expect(graph.line.match(/M/g)).toHaveLength(1);
    expect(graph.area.endsWith('L1,50 Z')).toBe(true);
    expect(cardGraph([null, null], 200, 50, 2)).toBeNull();
  });
  it('draws one level in the middle, and a single average across the width', () => {
    expect(new Set(cardGraph([5, 5, 5], 200, 50, 2)!.line.match(/,\d+/g))).toEqual(new Set([',25']));
    expect(cardGraph([5], 200, 50, 2)!.line.endsWith('L199,25')).toBe(true);
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
    expect(card.findAll('path.line')).toHaveLength(1);
    slow.resolve(graph(10));
    await flushPromises();
    expect(card.find('path.line').attributes('d')).toBe(cardGraph(graph(1).history.values, 200, 50, 2)!.line);
    await card.setProps({ entity: 'sensor.gone' });
    await flushPromises();
    expect(card.text()).toBe('No recorded history');
  });
});
