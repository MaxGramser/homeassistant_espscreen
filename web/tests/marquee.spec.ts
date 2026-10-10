import { afterEach, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick } from 'vue';
import MarqueeText from '../src/components/MarqueeText.vue';

afterEach(() => vi.unstubAllGlobals());
it('scrolls only overflowing text, remeasures after resize, follows a new text and cleans up', async () => {
  // Every observer the text gets, what it watches and whether it let go.
  const observers: { callback: () => void; watched: Element[]; done: boolean }[] = [];
  vi.stubGlobal('ResizeObserver', class {
    entry: (typeof observers)[number];
    constructor(callback: () => void) { this.entry = { callback, watched: [], done: false }; observers.push(this.entry); }
    observe(element: Element) { this.entry.watched.push(element); }
    disconnect() { this.entry.done = true; }
  });
  const resized = () => observers.at(-1)!.callback();
  const view = mount(MarqueeText, { props: { text: 'Long track title' } });
  const viewport = view.element;
  const text = view.get('.marquee-text').element;
  Object.defineProperty(viewport, 'clientWidth', { configurable: true, value: 100 });
  Object.defineProperty(text, 'scrollWidth', { configurable: true, value: 220 });
  resized(); await nextTick();
  expect(view.classes()).toContain('scrolling');
  expect(view.get('.marquee-copy').attributes('aria-hidden')).toBe('true');
  expect(view.attributes('style')).toContain('252px');
  Object.defineProperty(viewport, 'clientWidth', { value: 300 });
  resized(); await nextTick();
  expect(view.classes()).not.toContain('scrolling');
  expect(view.find('.marquee-copy').exists()).toBe(false);
  await view.setProps({ text: 'New track' });
  expect(view.attributes('title')).toBe('New track');
  // The new text is a new element, and it is the one measured from now on.
  expect(observers.at(-1)!.watched).toContain(view.get('.marquee-text').element);
  view.unmount();
  expect(observers.every((observer) => observer.done)).toBe(true);
});
