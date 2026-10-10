// What the editor remembers of itself in this browser (composables/usePreference.ts): under the names and values it always
// had, written as it changes and only then, never the default by itself, and nothing lost where the browser keeps nothing.
import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { flagSerializer, renewable, usePreference } from "../../src/composables/usePreference";
import { inScope } from "../helpers/with-setup";

describe("a preference", () => {
  it("reads what the browser kept, in the values it always had, and the default when nothing is kept", () => {
    localStorage.setItem("esp-screens.sidebar-folded", "1");
    const { result: folded } = inScope(() => usePreference("esp-screens.sidebar-folded", false, { serializer: flagSerializer }));
    expect(folded.value).toBe(true);
    const { result: open } = inScope(() => usePreference("esp-screens.full-editor", false, { serializer: flagSerializer }));
    expect(open.value).toBe(false);
    // The default is never written by itself.
    expect(localStorage.getItem("esp-screens.full-editor")).toBeNull();
  });

  it("writes a change at once, and only a change", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { result: width } = inScope(() => usePreference("esp-screens.sidebar-width", 248, { serializer: { read: Number, write: String } }));
    width.value = 300;
    expect(localStorage.getItem("esp-screens.sidebar-width")).toBe("300");
    width.value = 300;
    expect(setItem).toHaveBeenCalledTimes(1);
  });

  it("keeps JSON when it is given no serializer", () => {
    const { result } = inScope(() => usePreference<{ open: string[] }>("esp-screens.test-json", { open: [] }));
    result.value = { open: ["kitchen"] };
    expect(JSON.parse(localStorage.getItem("esp-screens.test-json")!)).toEqual({ open: ["kitchen"] });
  });

  it("follows a key that changes, such as the screen it belongs to, without writing one into the other", () => {
    localStorage.setItem("esp-screens-mode:hall", "advanced");
    const screen = ref("hall");
    const { result: mode } = inScope(() => usePreference(() => `esp-screens-mode:${screen.value}`, "simple"
      , { serializer: { read: (raw) => (raw === "advanced" ? "advanced" : "simple"), write: (value) => value } }));
    expect(mode.value).toBe("advanced");
    screen.value = "kitchen";
    expect(mode.value).toBe("simple");
    mode.value = "advanced";
    screen.value = "hall";
    expect(mode.value).toBe("advanced");
    expect([localStorage.getItem("esp-screens-mode:hall"), localStorage.getItem("esp-screens-mode:kitchen")]).toEqual(["advanced", "advanced"]);
  });

  it("goes on where the browser keeps nothing: the default, and no exception on a read or a write", () => {
    const blocked = () => { throw new DOMException("The operation is insecure.", "SecurityError"); };
    vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked, removeItem: blocked });
    const { result: height } = inScope(() => usePreference("esp-screens.library-height", 300, { serializer: { read: Number, write: String } }));
    expect(height.value).toBe(300);
    height.value = 340;
    expect(height.value).toBe(340);
  });

  it("follows another tab only where it asks to", async () => {
    const quiet = inScope(() => usePreference("esp-screens.test-tabs", "a"));
    const listening = inScope(() => usePreference("esp-screens.test-tabs", "a", { listen: true }));
    localStorage.setItem("esp-screens.test-tabs", JSON.stringify("b"));
    window.dispatchEvent(new StorageEvent("storage", { key: "esp-screens.test-tabs", newValue: JSON.stringify("b"), storageArea: localStorage }));
    await nextTick();
    expect([quiet.result.value, listening.result.value]).toEqual(["a", "b"]);
    listening.stop();
  });
});

describe("preferences a module keeps", () => {
  it("are made again by the next call, reading the storage as it is then, and the old ones write no more", () => {
    const make = renewable(() => usePreference("esp-screens.sidebar-folded", false, { serializer: flagSerializer }));
    const first = make();
    first.value = true;
    expect(localStorage.getItem("esp-screens.sidebar-folded")).toBe("1");
    localStorage.clear();
    const second = make();
    expect(second.value).toBe(false);
    first.value = false;
    first.value = true;
    expect(localStorage.getItem("esp-screens.sidebar-folded")).toBeNull();
  });
});
