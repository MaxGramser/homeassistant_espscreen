// Whether the editor reaches ESP Screen Manager (ConnectionBar): a calm line while it cannot, "Connection restored" for a
// moment when it is back, and nothing at all while all is well.
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import ConnectionBar from "../src/components/ConnectionBar.vue";
import { useInventoryStore } from "../src/stores/inventory";

describe("the connection bar", () => {
  it("says the add-on cannot be reached, says it is back, and then goes", async () => {
    vi.useFakeTimers();
    const inv = useInventoryStore();
    const bar = mount(ConnectionBar, { global: { stubs: { transition: true } } });
    expect(bar.find("#connection-bar").exists()).toBe(false);
    inv.reachable = false;
    await nextTick();
    expect(bar.find("#connection-bar").text()).toContain("ESP Screen Manager can't be reached. Your changes stay here. Trying again…");
    inv.reachable = true;
    await nextTick();
    expect(bar.find("#connection-bar").text()).toContain("Connection restored");
    expect(bar.find("#connection-bar").classes()).toContain("back");
    vi.advanceTimersByTime(3000);
    await nextTick();
    expect(bar.find("#connection-bar").exists()).toBe(false);
    // Lost again before the line went: the line says so at once.
    inv.reachable = false;
    await nextTick();
    inv.reachable = true;
    await nextTick();
    inv.reachable = false;
    await nextTick();
    expect(bar.find("#connection-bar").classes()).not.toContain("back");
  });
});
