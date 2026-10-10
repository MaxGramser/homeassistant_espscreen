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
  it("goes where it is sent, follows the address bar while started, and knows only its own views", () => {
    vi.stubGlobal("scrollTo", vi.fn());
    const ui = useUiStore();
    const stop = ui.start();
    ui.go("#settings");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect([location.hash, ui.route]).toEqual(["#settings", "#settings"]);
    history.replaceState(null, "", "#nowhere");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect([ui.hash, ui.route]).toEqual(["#nowhere", ""]);
    stop();
    history.replaceState(null, "", "#alerts");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(ui.hash).toBe("#nowhere");
    // Sent to the view the address already names, the store takes it at once (no hashchange comes).
    ui.go("#nowhere" as any);
    expect(ui.hash).toBe("#nowhere");
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
