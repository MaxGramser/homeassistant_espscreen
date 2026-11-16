// The mockup's live values (app 0.2.73, stores/entities.ts loadStates): the open layout's entities are asked of the app
// sixty at a time, one round at a time, and a light group's lamps after them; what Home Assistant said lands in
// liveStates, which the mockup draws (components.spec.ts: a light that is on is lit). Took the place of a test that
// quoted the store's lines (tests/test_editor_live.py).
import { describe, expect, it, vi } from "vitest";
import { useEntitiesStore } from "../src/stores/entities";
import type { Screen } from "../src/types";

// The app as the page reaches it (api/states?entity=...): `answer` says what Home Assistant has for the ids asked.
const ids = (url: string) => new URLSearchParams(url.split("?")[1]).getAll("entity");
function app(answer: (id: string) => object | Promise<object>) {
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => {
    const states = Object.fromEntries(await Promise.all(ids(String(url)).map(async (id) => [id, await answer(id)])));
    return new Response(JSON.stringify({ states }), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
const asked = (fetch: ReturnType<typeof app>) => fetch.mock.calls.filter(([url]) => String(url).startsWith("api/states?")).map(([url]) => ids(String(url)).length);

describe("the mockup's live values", () => {
  it("asks sixty entities at a time and keeps what came", async () => {
    const fetch = app(() => ({ state: "on" }));
    const layout = Array.from({ length: 130 }, (_, i) => `light.lamp_${i}`).concat("screen.clock", "light.lamp_0");
    await useEntitiesStore().loadStates(layout);
    expect(asked(fetch)).toEqual([60, 60, 10]);
    expect(Object.keys(useEntitiesStore().liveStates)).toHaveLength(130);
    expect(useEntitiesStore().liveStates["screen.clock"]).toBeUndefined();
  });

  it("asks a light group's lamps after the layout's own", async () => {
    const fetch = app((id) => (id === "light.group" ? { state: "on", a: { entity_id: ["light.a", "light.b"] } } : { state: "off" }));
    await useEntitiesStore().loadStates(["light.group"]);
    expect(asked(fetch)).toEqual([1, 2]);
    expect(useEntitiesStore().liveStates["light.b"]).toEqual({ state: "off" });
  });

  it("drops an answer no longer wanted, and runs one round at a time", async () => {
    let release!: () => void;
    const fetch = app(() => new Promise((done) => { release = () => done({ state: "on" }); }));
    const store = useEntitiesStore();
    const first = store.loadStates(["light.a"], () => false);
    await store.loadStates(["light.a"]);
    await vi.waitFor(() => expect(release).toBeTypeOf("function"));
    expect(asked(fetch)).toEqual([1]);
    release();
    await first;
    expect(store.liveStates["light.a"]).toBeUndefined();
  });
});

describe("identify and the test alert (app 0.2.73)", () => {
  it("asks the app to blink a screen, and sends a test alert to one screen or all", async () => {
    const { useScreenStore } = await import("../src/stores/screen");
    const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
      async () => new Response(JSON.stringify({ sent: 1, failed: 0, skipped: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const screens = useScreenStore();
    await screens.identify({ id: "text.hall screen", name: "Hall" } as Screen);
    expect(fetch.mock.calls[0][0]).toBe("api/screens/text.hall%20screen/identify");
    expect(fetch.mock.calls[0][1]?.method).toBe("POST");
    const answer = await screens.sendTestAlert("all", { title: "Test" });
    expect(fetch.mock.calls[1][0]).toBe("api/alerts/test");
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({ screen: "all", data: { title: "Test" } });
    expect(answer.sent).toBe(1);
  });
});
