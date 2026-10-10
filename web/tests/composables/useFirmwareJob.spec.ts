// The add-on's firmware job followed by whoever shows it (composables/useFirmwareJob.ts): one poll for all of them, as
// often as the most eager one wants, never while the tab is hidden, gone with the last of them.
import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { followBuilds, useFirmwareJob } from "../../src/composables/useFirmwareJob";
import { state } from "../../src/store";
import type { Inventory } from "../../src/types";
import { setHidden } from "../helpers/browser";
import { useFakeClock } from "../helpers/clock";
import { failure, fakeApi } from "../helpers/fake-api";
import { inScope } from "../helpers/with-setup";

const job = (n: number) => ({ job: { file: "hall.yaml", state: "running", stage: `step ${n}` }, logs: [`line ${n}`] });

describe("the firmware job", () => {
  it("is asked for once every three seconds however many follow it, and not while the tab is hidden", async () => {
    const clock = useFakeClock();
    let n = 0;
    const api = fakeApi({ "GET firmware": () => job(++n) });
    const first = inScope(() => useFirmwareJob()), second = inScope(() => useFirmwareJob());
    await clock.tick(9000);
    expect(api.count("firmware")).toBe(3);
    setHidden(true);
    await nextTick();
    await clock.tick(30000);
    expect(api.count("firmware")).toBe(3);
    setHidden(false);
    await nextTick();
    await clock.tick(3000);
    expect(api.count("firmware")).toBe(4);
    // The last one to go takes the poll with it.
    first.stop();
    await clock.tick(3000);
    expect(api.count("firmware")).toBe(5);
    second.stop();
    await clock.tick(30000);
    expect(api.count("firmware")).toBe(5);
    expect(clock.timers()).toBe(0);
  });

  it("is asked as often as the most eager follower wants while it is active, and hands every answer to each", async () => {
    const clock = useFakeClock();
    let n = 0;
    const api = fakeApi({ "GET firmware": () => job(++n) });
    const checking = ref(false), seen: string[] = [], others: string[] = [];
    inScope(() => useFirmwareJob({ onAnswer: (data) => others.push(data.job.stage) }));
    const check = inScope(() => useFirmwareJob({ interval: 1200, active: checking, onAnswer: (data) => seen.push(data.job.stage) }));
    await clock.tick(6000);
    expect(api.count("firmware")).toBe(2);
    checking.value = true;
    await nextTick();
    await clock.tick(6000);
    expect(api.count("firmware")).toBe(7);
    checking.value = false;
    await nextTick();
    await clock.tick(6000);
    expect(api.count("firmware")).toBe(9);
    expect(seen).toEqual(others);
    expect(seen.at(-1)).toBe("step 9");
    // A view's own look reaches the others too.
    await check.result.refresh();
    await nextTick();
    expect(others.at(-1)).toBe("step 10");
  });

  it("tells a follower when a poll failed, and asks again at the next turn", async () => {
    const clock = useFakeClock();
    const api = fakeApi({ "GET firmware": failure(502, "Bad gateway") });
    const errors: string[] = [];
    inScope(() => useFirmwareJob({ onError: (error) => errors.push(error.message) }));
    await clock.tick(6000);
    expect(errors).toEqual(["Bad gateway", "Bad gateway"]);
    api.on("GET firmware", job(1));
    await clock.tick(3000);
    expect(state.firmwareJob?.logs).toEqual(["line 1"]);
  });

  it("is followed by the store only while something builds, for the build log", async () => {
    const clock = useFakeClock();
    const api = fakeApi({ "GET firmware": job(1) });
    state.inventory = { screens: [], entities: [], builds: {} } as unknown as Inventory;
    const stop = followBuilds();
    await clock.tick(30000);
    expect(api.count("firmware")).toBe(0);
    state.updating = ["hall"];
    await nextTick();
    await clock.tick(9000);
    expect(api.count("firmware")).toBe(3);
    expect(state.firmwareJob?.logs).toEqual(["line 1"]);
    state.updating = [];
    await nextTick();
    await clock.tick(30000);
    expect(api.count("firmware")).toBe(3);
    stop();
    expect(vi.getTimerCount()).toBe(0);
  });
});
