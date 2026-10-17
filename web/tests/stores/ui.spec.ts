// The page around the screens (stores/ui.ts): a toast that goes by itself, the view the address names, the phone's
// editor of everyday changes, and what its start follows until it is stopped.
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { useUiStore } from "../../src/stores/ui";
import { setMedia } from "../helpers/browser";

const PHONE = "(max-width: 640px)";

afterEach(() => vi.useRealTimers());

describe("the toast", () => {
  it("goes after five seconds, eight when it offers something to do, and a new one starts the count again", () => {
    vi.useFakeTimers();
    const ui = useUiStore();
    ui.toast("Saved");
    vi.advanceTimersByTime(4999);
    expect(ui.notice?.message).toBe("Saved");
    vi.advanceTimersByTime(1);
    expect(ui.notice).toBeNull();
    const run = vi.fn();
    ui.toast("Tile removed", { label: "Undo", run });
    vi.advanceTimersByTime(7000);
    ui.toast("Saved again");
    vi.advanceTimersByTime(4999);
    expect(ui.notice?.message).toBe("Saved again");
    vi.advanceTimersByTime(1);
    expect(ui.notice).toBeNull();
    ui.toast("Tile removed", { label: "Undo", run });
    vi.advanceTimersByTime(7999);
    expect(ui.notice?.action?.run).toBe(run);
    ui.dismissToast();
    expect(ui.notice).toBeNull();
  });
});

describe("the view the address names", () => {
  it("goes where it is sent, reads the address as the router does, and knows only its own views", async () => {
    vi.stubGlobal("scrollTo", vi.fn());
    const ui = useUiStore();
    const { router } = await import("../../src/router");
    await ui.go("#settings");
    expect([router.currentRoute.value.path, location.hash, ui.route]).toEqual(["/settings", "#/settings", "#settings"]);
    // An address the editor does not know is the overview.
    await router.push("/nowhere");
    expect([router.currentRoute.value.path, ui.route]).toEqual(["/", ""]);
    // A hash from before the router (#alerts, a kept link) still opens its page: a router made on that address, as
    // the page's is when it loads, reads it as /alerts.
    history.replaceState(null, "", "#alerts");
    const { createRouter, createWebHashHistory } = await import("vue-router");
    const kept = createRouter({ history: createWebHashHistory(), routes: router.options.routes });
    await kept.push(kept.options.history.location);
    expect(kept.currentRoute.value.path).toBe("/alerts");
    // The main view, with no session to name the open screen, is the overview.
    await ui.go("");
    expect([router.currentRoute.value.path, ui.route]).toEqual(["/", ""]);
    // A screen's Override YAML by its profile, which a reload keeps.
    await ui.openOverride("hall.yaml");
    expect([router.currentRoute.value.path, ui.route, ui.overrideProfile]).toEqual(["/override/hall.yaml", "#override", "hall.yaml"]);
    await ui.openOverride(null);
    expect([ui.route, ui.overrideProfile]).toEqual(["#override", null]);
  });

  it("comes back to the last address when the page starts without one, as it does in Home Assistant's frame", async () => {
    const { router, restoreKeptRoute } = await import("../../src/router");
    await router.replace("/");
    await router.push("/screens/text.hall_tiles");
    expect(sessionStorage.getItem("esp-screens.route")).toBe("/screens/text.hall_tiles");
    // Home Assistant makes the frame anew at the bare address, which the router has read as the overview by the time the
    // page restores: the kept one comes back.
    await router.replace("/");
    sessionStorage.setItem("esp-screens.route", "/screens/text.hall_tiles");
    await restoreKeptRoute();
    expect(router.currentRoute.value.fullPath).toBe("/screens/text.hall_tiles");
    // A tab whose last address was the overview stays there.
    await router.replace("/");
    expect(sessionStorage.getItem("esp-screens.route")).toBe("/");
    await restoreKeptRoute();
    expect(router.currentRoute.value.fullPath).toBe("/");
    // An address that is there wins over the kept one.
    sessionStorage.setItem("esp-screens.route", "/plugins");
    history.replaceState(null, "", "#/alerts");
    await router.replace("/alerts");
    await restoreKeptRoute();
    expect(router.currentRoute.value.fullPath).toBe("/alerts");
  });
});

describe("the phone", () => {
  it("is the editor of everyday changes on a narrow window, followed while started, unless this browser chose the whole editor", async () => {
    const ui = useUiStore();
    const stop = ui.start();
    expect(ui.phone).toBe(false);
    setMedia(PHONE, true);
    await nextTick();
    expect([ui.narrowPhone, ui.phone]).toEqual([true, true]);
    ui.addSheet = true; ui.pagesSheet = true; ui.menuOpen = true;
    ui.setFullEditor(true);
    expect([ui.phone, ui.addSheet, ui.pagesSheet, ui.menuOpen]).toEqual([false, false, false, false]);
    expect(localStorage.getItem("esp-screens.full-editor")).toBe("1");
    ui.setFullEditor(false);
    expect(ui.phone).toBe(true);
    stop();
    setMedia(PHONE, false);
    await nextTick();
    expect(ui.narrowPhone).toBe(true);
  });
});
