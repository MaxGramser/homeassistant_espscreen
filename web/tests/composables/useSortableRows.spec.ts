// A list reordered by dragging its rows (composables/useSortableRows.ts): the row takes the place the pointer passes, the
// order is kept when it is let go and not when the drag is cancelled, a control in a row is no handle, and the arrow keys
// move the focused row.
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { useSortableRows } from "../../src/composables/useSortableRows";
import { pointer } from "./pointer";

// Three rows of 20 px, one under the other.
function list(start: string[], extra: Partial<Parameters<typeof useSortableRows<string>>[0]> = {}) {
  const items = ref(start), commit = vi.fn((next: string[]) => { items.value = next; });
  let rows!: ReturnType<typeof useSortableRows<string>>;
  const view = mount(defineComponent({
    setup() {
      rows = useSortableRows<string>({ rows: ".row", items: () => items.value, commit, skip: "button", grip: ".grip", ...extra });
      return () => h("div", (rows.live.value || items.value).map((name, i) => h("div", {
        class: "row", tabindex: 0, key: name, onPointerdown: (e: PointerEvent) => rows.down(e, i), onKeydown: (e: KeyboardEvent) => rows.key(e, i),
      }, [h("span", { class: "grip" }), name, h("button", "x")])));
    },
  }), { attachTo: document.body });
  view.findAll(".row").forEach((row, i) => { row.element.getBoundingClientRect = () => ({ top: i * 20, height: 20, bottom: i * 20 + 20, left: 0, right: 100, width: 100 }) as DOMRect; });
  return { view, items, commit, rows: () => rows };
}

describe("a list sorted by dragging", () => {
  it("moves the dragged row to where the pointer passed, and keeps the order when it is let go", async () => {
    const { view, items, commit, rows } = list(["media", "camera", "clock"]);
    view.findAll(".row")[0].element.dispatchEvent(pointer("pointerdown", { y: 5 }));
    document.dispatchEvent(pointer("pointermove", { y: 35 }));
    expect(rows().live.value).toEqual(["camera", "media", "clock"]);
    expect(rows().drag.value).toEqual({ index: 1, active: true });
    document.dispatchEvent(pointer("pointerup", { y: 35 }));
    expect(commit).toHaveBeenCalledWith(["camera", "media", "clock"]);
    expect(items.value).toEqual(["camera", "media", "clock"]);
    expect(rows().drag.value).toEqual({ index: -1, active: false });
  });

  it("keeps nothing of a cancelled drag, or of a press on a row's control", async () => {
    const { view, commit, rows } = list(["media", "camera", "clock"]);
    view.findAll(".row")[0].element.dispatchEvent(pointer("pointerdown", { y: 5 }));
    document.dispatchEvent(pointer("pointermove", { y: 50 }));
    document.dispatchEvent(pointer("pointercancel", { y: 50 }));
    expect(rows().live.value).toBeNull();
    view.find(".row button").element.dispatchEvent(pointer("pointerdown", { y: 5 }));
    document.dispatchEvent(pointer("pointermove", { y: 50 }));
    expect(rows().drag.value.active).toBe(false);
    expect(commit).not.toHaveBeenCalled();
  });

  it("drags at once by a finger on the grip, and asks the page for nothing when it can't be reordered", async () => {
    const enabled = ref(true);
    const { view, rows } = list(["a", "b"], { enabled: () => enabled.value });
    const press = pointer("pointerdown", { kind: "touch", y: 5 });
    view.find(".grip").element.dispatchEvent(press);
    expect(rows().drag.value.active).toBe(true);
    document.dispatchEvent(pointer("pointerup", { kind: "touch" }));
    enabled.value = false;
    view.findAll(".row")[1].element.dispatchEvent(pointer("pointerdown", { y: 25 }));
    expect(rows().drag.value.index).toBe(-1);
  });

  it("moves the focused row with the arrow keys, and the focus goes with it", async () => {
    const { view, items } = list(["media", "camera", "clock"]);
    const first = view.findAll(".row")[0].element as HTMLElement;
    first.focus();
    first.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    expect(items.value).toEqual(["camera", "media", "clock"]);
    await nextTick(); await nextTick();
    expect(document.activeElement?.textContent).toContain("media");
  });
});
