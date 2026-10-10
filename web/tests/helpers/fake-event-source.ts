// The add-on's live streams (api/events, a firmware preview's events) as a test sees them: the fake EventSource that
// tests/helpers/browser.ts puts in place of the browser's, made, opened, fed and broken by hand.
import { FakeEventSource, lastStream } from "./browser";

export { FakeEventSource, lastStream };

/** The streams made since the test began whose address starts with `path` (without "api/"), the newest last. */
export const streamsTo = (path: string) => FakeEventSource.streams.filter((stream) => stream.url.startsWith(`api/${path}`));
/** The newest stream to `path`, opened: what the add-on does when it answers. */
export function openStream(path = "events") {
  const stream = streamsTo(path).at(-1);
  if (!stream) throw new Error(`no stream to api/${path}`);
  stream.open();
  return stream;
}
/** How many streams are open now: a stream closed by the page or given up by the browser is not. */
export const openStreams = () => FakeEventSource.streams.filter((stream) => stream.readyState !== FakeEventSource.CLOSED).length;
