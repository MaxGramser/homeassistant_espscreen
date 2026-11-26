// A log that follows its last line (composables/useStickToBottom.ts).
import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { useStickToBottom } from "../../src/composables/useStickToBottom";
import { inScope } from "../helpers/with-setup";

// A box 100 px high holding `height` px, scrolled to `top`.
function box(height: number, top: number) {
  const element = document.createElement("pre");
  Object.defineProperty(element, "scrollHeight", { configurable: true, get: () => height });
  Object.defineProperty(element, "clientHeight", { configurable: true, value: 100 });
  element.scrollTop = top;
  return element;
}

describe("a log that follows its last line", () => {
  it("scrolls to the bottom once new lines are drawn", async () => {
    const element = box(500, 0), lines = ref(1);
    inScope(() => useStickToBottom(element, lines));
    lines.value = 2;
    await nextTick(); await nextTick();
    expect(element.scrollTop).toBe(500);
  });
  it("with `near`, only while the reader is at the bottom", async () => {
    const reading = box(500, 100), following = box(500, 380), lines = ref(1);
    inScope(() => { useStickToBottom(reading, lines, { near: 40 }); useStickToBottom(following, lines, { near: 40 }); });
    lines.value = 2;
    await nextTick(); await nextTick();
    expect([reading.scrollTop, following.scrollTop]).toEqual([100, 500]);
  });
  it("follows a log that keeps only its newest lines, whose number no longer grows", async () => {
    // The add-on's live log holds 300 lines (build_logs.Tee): past them every new answer has 300, with the newest last.
    const element = box(500, 400), lines = ref(Array.from({ length: 300 }, (_, i) => `line ${i}`));
    inScope(() => useStickToBottom(element, lines, { near: 40 }));
    lines.value = [...lines.value.slice(1), "line 300"];
    await nextTick(); await nextTick();
    expect(lines.value).toHaveLength(300);
    expect(element.scrollTop).toBe(500);
  });
});
