import { describe, expect, it } from 'vitest';
import { cardGraph } from '../src/model/history-preview';
describe('the graph on a card (render_graph)', () => {
  it('runs the line past a missing average and scales between the lowest and the highest', () => {
    const graph = cardGraph([0, 2, null, 4], 200, 50, 2)!;
    // The first average at the bottom, the last at the top, each at its own place of 24 across the width.
    expect(graph.line.startsWith('M1,48')).toBe(true);
    expect(graph.line.endsWith(`L${Math.round((1 + 3 * 197 / 23) * 100) / 100},3`)).toBe(true);
    expect(graph.line.match(/M/g)).toHaveLength(1);
    expect(graph.area.endsWith('L1,50 Z')).toBe(true);
    expect(cardGraph([null, null], 200, 50, 2)).toBeNull();
  });
  it('draws one level in the middle, and a single average across the width', () => {
    expect(cardGraph([5, 5, 5], 200, 50, 2)!.line).toContain(',25.5');
    expect(cardGraph([5], 200, 50, 2)!.line.endsWith('L199,25.5')).toBe(true);
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
