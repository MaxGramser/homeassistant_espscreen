// What the browser has and jsdom lacks, so the store and the components meet the same globals in a test as on the page:
// media queries, the observers, a stream from the add-on, the clipboard, and a tab that can be hidden. Each is inert
// until a test moves it (setMedia, a stream's open or fail, setHidden), and tests/setup.ts puts every one back after
// each test. A test that needs another one still stubs it (vi.stubGlobal), which vitest undoes before the next.

/** A stream from the add-on (api/events) that a test opens, feeds and breaks by hand. */
export class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  /** Every stream made since the last reset, the newest last. */
  static streams: FakeEventSource[] = [];
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSED = 2;
  readyState = 0;
  withCredentials = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor(public url: string) {
    FakeEventSource.streams.push(this);
  }
  close() { this.readyState = 2; }
  addEventListener() {}
  removeEventListener() {}
  /** The add-on answers: the stream is open. */
  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  /** One message, as the add-on sends it: JSON. */
  send(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
  /** The stream breaks. The browser tries again by itself (CONNECTING), or gives up for good (CLOSED), as it does when
   * ingress answers 502 while the add-on restarts. */
  fail(closed = false) {
    this.readyState = closed ? 2 : 0;
    this.onerror?.(new Event("error"));
  }
}
/** The newest stream, or none. */
export const lastStream = () => FakeEventSource.streams.at(-1);

class InertObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}

type Listener = (event: MediaQueryListEvent) => void;
class FakeMediaQueryList {
  matches = false;
  onchange: Listener | null = null;
  listeners = new Set<Listener>();
  constructor(public media: string) {}
  addEventListener(_type: string, listener: Listener) { this.listeners.add(listener); }
  removeEventListener(_type: string, listener: Listener) { this.listeners.delete(listener); }
  addListener(listener: Listener) { this.listeners.add(listener); }
  removeListener(listener: Listener) { this.listeners.delete(listener); }
  dispatchEvent() { return true; }
}
const media = new Map<string, FakeMediaQueryList>();
const mediaList = (query: string) => media.get(query) ?? media.set(query, new FakeMediaQueryList(query)).get(query)!;
/** A media query that starts or stops matching (a window as narrow as a phone), told to whoever listens. */
export function setMedia(query: string, matches: boolean) {
  const list = mediaList(query);
  list.matches = matches;
  const event = { matches, media: query } as MediaQueryListEvent;
  for (const listener of list.listeners) listener(event);
  list.onchange?.(event);
}
/** How many listen to a media query: none once what started them has stopped. */
export const mediaListeners = (query: string) => mediaList(query).listeners.size;

let copied = "";
/** What the last copy put on the clipboard. */
export const clipboardText = () => copied;

/** The tab hidden or shown again, with the event the page gets. */
export function setHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => (hidden ? "hidden" : "visible") });
  document.dispatchEvent(new Event("visibilitychange"));
}

const global = globalThis as Record<string, unknown>;
/** Puts what jsdom lacks in place, once per test file (tests/setup.ts). */
export function installBrowser() {
  global.EventSource ??= FakeEventSource;
  global.ResizeObserver ??= class extends InertObserver {};
  global.IntersectionObserver ??= class extends InertObserver {};
  if (!window.matchMedia) Object.defineProperty(window, "matchMedia", { configurable: true, writable: true, value: (query: string) => mediaList(query) });
  if (!("clipboard" in navigator)) Object.defineProperty(navigator, "clipboard", { configurable: true,
    value: { writeText: async (text: string) => { copied = text; }, readText: async () => copied } });
}

/** Everything a test moved, back as it was (tests/setup.ts, after each test). */
export function resetBrowser() {
  FakeEventSource.streams = [];
  for (const list of media.values()) { list.matches = false; list.listeners.clear(); list.onchange = null; }
  copied = "";
  delete (document as unknown as Record<string, unknown>).hidden;
  delete (document as unknown as Record<string, unknown>).visibilityState;
}
