// The tests' own helpers (tests/helpers/): a pinia of its own per test, a composable run as a component runs it, the
// add-on's API played from a table, and the clock.
import { mount } from "@vue/test-utils";
import { defineStore } from "pinia";
import { describe, expect, it } from "vitest";
import { defineComponent, h, onMounted, ref, watch } from "vue";
import { getJson, send } from "../src/api";
import { useFakeClock } from "./helpers/clock";
import { failure, fakeApi, reply } from "./helpers/fake-api";
import { testingPinia } from "./helpers/pinia";
import { inScope, withSetup } from "./helpers/with-setup";

const useCounter = defineStore("helpers-counter", () => {
  const count = ref(0);
  const add = (by = 1) => { count.value += by; };
  return { count, add };
});

describe("the tests' pinia", () => {
  it("is a new one for every test: what one test left in a store, the next does not see (1)", () => {
    useCounter().add(5);
    expect(useCounter().count).toBe(5);
  });
  it("is a new one for every test: what one test left in a store, the next does not see (2)", () => {
    expect(useCounter().count).toBe(0);
  });
  it("reaches the components a test mounts", () => {
    useCounter().add(2);
    const view = mount(defineComponent({ setup: () => { const counter = useCounter(); return () => h("b", counter.count); } }));
    expect(view.text()).toBe("2");
  });
  it("spies on the actions and still runs them for a flow, or stubs them when asked", () => {
    testingPinia();
    const counter = useCounter();
    counter.add(3);
    expect(counter.add).toHaveBeenCalledWith(3);
    expect(counter.count).toBe(3);
    testingPinia({ stubActions: true });
    const stubbed = useCounter();
    stubbed.add(3);
    expect(stubbed.count).toBe(0);
  });
});

describe("a composable run without a component", () => {
  it("in a scope: its watches go with the stop", async () => {
    const source = ref(1), seen: number[] = [];
    const { result, stop } = inScope(() => { watch(source, (value) => seen.push(value)); return "ran"; });
    expect(result).toBe("ran");
    source.value = 2;
    await Promise.resolve();
    stop();
    source.value = 3;
    await Promise.resolve();
    expect(seen).toEqual([2]);
  });
  it("in a mounted app: onMounted runs, the texts and the stores are there", () => {
    const mounted: string[] = [];
    const { result, unmount } = withSetup(() => { onMounted(() => mounted.push("mounted")); return useCounter(); });
    expect(mounted).toEqual(["mounted"]);
    result.add();
    expect(useCounter().count).toBe(1);
    unmount();
  });
});

describe("the add-on's API played by a test", () => {
  it("answers by route, with the route's parameters, and records every request", async () => {
    const api = fakeApi({
      "GET inventory": { screens: [] },
      "PUT screens/:id": ({ params, body }) => ({ saved: true, id: params.id, title: body.layout.title }),
    });
    expect(await getJson("inventory?light=1")).toEqual({ screens: [] });
    expect(await send("screens/living%20room", "PUT", { layout: { title: "Hall" } })).toEqual({ saved: true, id: "living room", title: "Hall" });
    expect(api.count("PUT screens/:id")).toBe(1);
    expect(api.asked("inventory")[0].query.get("light")).toBe("1");
    expect(api.calls.map((call) => `${call.method} ${call.path}`)).toEqual(["GET inventory", "PUT screens/living%20room"]);
  });
  it("answers an error as the add-on does, and a request it does not know with 404", async () => {
    fakeApi({ "POST screens/:id/identify": failure(503, "Home Assistant did not answer in time.") });
    await expect(send("screens/hall/identify", "POST")).rejects.toThrow("Home Assistant did not answer in time.");
    await expect(getJson("nothing")).rejects.toThrow("GET nothing is not in the test's API");
    fakeApi({ "DELETE screens/:id": reply(204) });
    expect(await send("screens/hall", "DELETE")).toBeNull();
  });
  it("holds an answer back until the test lets it go, or loses it", async () => {
    const api = fakeApi({ "GET firmware": { job: null } });
    const held = api.defer("GET firmware");
    let answer: unknown = null;
    const asking = getJson("firmware").then((data) => (answer = data));
    await Promise.resolve();
    expect(answer).toBeNull();
    held.resolve({ job: { state: "running" } });
    await asking;
    expect(answer).toEqual({ job: { state: "running" } });
    // Released without an answer of its own the route answers; rejected, the answer is lost on the way.
    const own = api.defer("GET firmware");
    own.resolve();
    expect(await getJson("firmware")).toEqual({ job: null });
    api.defer("GET firmware").reject();
    await expect(getJson("firmware")).rejects.toThrow("Failed to fetch");
  });
});

describe("the tests' clock", () => {
  it("starts at a fixed moment and runs what is due, with the promises it starts", async () => {
    const clock = useFakeClock();
    expect(new Date(clock.now()).toISOString()).toBe("2026-10-10T10:42:00.000Z");
    let done = false;
    setTimeout(() => Promise.resolve().then(() => { done = true; }), 1000);
    expect(clock.timers()).toBe(1);
    await clock.tick(1000);
    expect(done).toBe(true);
  });
});
