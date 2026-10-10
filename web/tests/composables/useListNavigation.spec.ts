// The arrows walking a list of results from its field, Enter taking the one in focus (composables/useListNavigation.ts).
import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { useListNavigation } from "../../src/composables/useListNavigation";
import { inScope } from "../helpers/with-setup";

const key = (name: string) => new KeyboardEvent("keydown", { key: name, cancelable: true });

describe("walking a list", () => {
  it("stops at the ends, or goes round with wrap, and tells where the focus went", () => {
    const moved = vi.fn();
    const { result: plain } = inScope(() => useListNavigation(["a", "b", "c"]));
    plain.move(-1); expect(plain.active.value).toBe(0);
    plain.move(5); expect(plain.active.value).toBe(2);
    const { result: round } = inScope(() => useListNavigation(["a", "b", "c"], { wrap: true, onMove: moved }));
    round.move(-1); expect(round.current.value).toBe("c");
    round.move(1); expect(round.current.value).toBe("a");
    expect(moved.mock.calls.map(([index]) => index)).toEqual([2, 0]);
  });
  it("takes the arrows and Enter, and leaves a key it has no use for", () => {
    const picked: string[] = [];
    const { result } = inScope(() => useListNavigation(["a", "b"], { onPick: (item) => (item === "b" ? (picked.push(item), true) : false) }));
    const down = key("ArrowDown");
    expect(result.onKey(down)).toBe(true);
    expect(down.defaultPrevented).toBe(true);
    const enter = key("Enter");
    expect([result.onKey(enter), enter.defaultPrevented, picked]).toEqual([true, true, ["b"]]);
    result.move(-1);
    const refused = key("Enter");
    expect([result.onKey(refused), refused.defaultPrevented]).toEqual([false, false]);
    expect(result.onKey(key("Escape"))).toBe(false);
  });
  it("starts at the first again when the search changes, and walks nothing in an empty list", async () => {
    const query = ref(""), items = ref(["a", "b", "c"]);
    const { result } = inScope(() => useListNavigation(items, { resetOn: query }));
    result.move(2);
    query.value = "b";
    await nextTick();
    expect(result.active.value).toBe(0);
    items.value = [];
    result.move(1);
    expect([result.active.value, result.current.value]).toEqual([0, undefined]);
  });
});
