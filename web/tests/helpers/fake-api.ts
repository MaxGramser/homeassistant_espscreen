// The add-on's API as a test plays it: a table of routes ("PUT screens/:id", "GET firmware", "inventory") with the answer
// each gives, every request recorded, an answer held back until the test lets it go (defer), and an error answered the
// way the add-on answers one, as JSON {"error": "..."} with its status. It takes the place of fetch for the test (vitest
// puts the real one back after it). A request no route knows is answered 404, so a test sees what it did not expect
// instead of a hang.
import { vi } from "vitest";

export type ApiRequest = { method: string; path: string; params: Record<string, string>; query: URLSearchParams; body: any; init: RequestInit };
/** What a route answers: a body (sent as JSON with 200), or a reply() with its own status. */
export type Answer = unknown;
export type Handler = (request: ApiRequest) => Answer | Promise<Answer>;
type Route = { key: string; method: string | null; pattern: RegExp; names: string[]; handler: Handler };

const REPLY = Symbol("reply");
type Reply = { [REPLY]: true; status: number; body: unknown };
/** An answer with a status of its own: reply(409, { error: "Changed elsewhere" }), or reply(204) for no body. */
export const reply = (status: number, body?: unknown): Reply => ({ [REPLY]: true, status, body });
/** An error as the add-on answers one: its status and {"error": message}. */
export const failure = (status: number, message: string) => reply(status, { error: message });
const isReply = (value: unknown): value is Reply => Boolean(value && typeof value === "object" && REPLY in value);
// A deferred answer released without one of its own: the route's handler answers.
const HANDLER = Symbol("handler");

// "PUT screens/:id" or "screens/:id" (any method), with or without "api/" in front.
function parse(route: string): Omit<Route, "handler"> {
  const [first, second] = route.trim().split(/\s+/);
  const [method, path] = second === undefined ? [null, first] : [first.toUpperCase(), second];
  const names: string[] = [];
  const pattern = new RegExp(`^${path.replace(/^\/?(api\/)?/, "").split("/").map((part) =>
    part.startsWith(":") ? (names.push(part.slice(1)), "([^/]+)") : part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("/")}$`);
  return { key: `${method ?? "*"} ${pattern.source}`, method, pattern, names };
}
function respond(answer: Answer) {
  const { status, body } = isReply(answer) ? answer : { status: 200, body: answer };
  return new Response(body === undefined || status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function fakeApi(routes: Record<string, Handler | Answer> = {}) {
  const table: Route[] = [];
  const calls: ApiRequest[] = [];
  const parked = new Map<string, Promise<Answer>[]>();
  const find = (method: string, path: string) => {
    for (const route of table) {
      if (route.method && route.method !== method) continue;
      const found = route.pattern.exec(path);
      if (found) return { route, params: Object.fromEntries(route.names.map((name, i) => [name, decodeURIComponent(found[i + 1])])) };
    }
    return null;
  };
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://editor.invalid/");
    const path = url.pathname.replace(/^\/(api\/)?/, "");
    const method = (init.method || "GET").toUpperCase();
    let body: unknown = init.body;
    if (typeof body === "string") try { body = JSON.parse(body); } catch { /* not JSON: as it was sent */ }
    const found = find(method, path);
    const request: ApiRequest = { method, path, params: found?.params || {}, query: url.searchParams, body, init };
    calls.push(request);
    if (!found) return respond(failure(404, `${method} ${path} is not in the test's API`));
    // A held answer comes when the test lets it go; a rejected one is an answer lost on the way (fetch throws).
    const gate = parked.get(found.route.key)?.shift();
    const held = gate ? await gate : HANDLER;
    return respond(held === HANDLER ? await found.route.handler(request) : held);
  });
  const api = {
    fetch,
    /** Every request so far, in order: its method, path (without api/), route parameters, query and body. */
    calls,
    /** Adds a route, or replaces the one with the same method and path. */
    on(route: string, answer: Handler | Answer) {
      const parsed = parse(route);
      const index = table.findIndex((other) => other.key === parsed.key);
      if (index >= 0) table.splice(index, 1);
      // The newest first: a route given later narrows one given before it ("PUT screens/:id" over "screens/:id").
      table.unshift({ ...parsed, handler: typeof answer === "function" ? (answer as Handler) : () => answer });
      return api;
    },
    /** The requests to one route ("PUT screens/:id", "firmware"), or all of them. */
    asked(route?: string) {
      if (!route) return [...calls];
      const { method, pattern } = parse(route);
      return calls.filter((call) => (!method || call.method === method) && pattern.test(call.path));
    },
    /** How many requests went to a route, or to any. */
    count: (route?: string) => api.asked(route).length,
    /** The next request to `route` waits until the test answers it: resolve() with the route's own answer or another,
     * reject() for an answer lost on the way. */
    defer(route: string) {
      const { key } = parse(route);
      if (!table.some((other) => other.key === key)) throw new Error(`${route} is not in the test's API`);
      let resolve!: (answer: Answer) => void, reject!: (error: unknown) => void;
      const gate = new Promise<Answer>((yes, no) => { resolve = yes; reject = no; });
      (parked.get(key) ?? parked.set(key, []).get(key)!).push(gate);
      return {
        resolve: (...answer: [Answer?]) => resolve(answer.length ? answer[0] : HANDLER),
        reject: (error: unknown = new TypeError("Failed to fetch")) => reject(error),
      };
    },
  };
  for (const [route, answer] of Object.entries(routes)) api.on(route, answer);
  vi.stubGlobal("fetch", fetch);
  return api;
}
export type FakeApi = ReturnType<typeof fakeApi>;
