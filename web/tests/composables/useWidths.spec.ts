// The widths at which the editor lays itself out another way (composables/useWidths.ts): one table, read once as the page
// loads or followed while a component lives.
import { describe, expect, it } from "vitest";
import { atMost, useAtMost, WIDTHS } from "../../src/composables/useWidths";
import { mediaListeners, setMedia } from "../helpers/browser";
import { inScope } from "../helpers/with-setup";

describe("the editor's widths", () => {
  it("are a phone at 640 px and the narrow pages at 700 px, as the style sheets have them", () => {
    expect(WIDTHS).toEqual({ phone: 640, narrow: 700 });
  });
  it("are read once, or followed while a scope lives and let go of with it", () => {
    setMedia("(max-width: 640px)", true);
    expect([atMost("phone"), atMost("narrow")]).toEqual([true, false]);
    const { result: narrow, stop } = inScope(() => useAtMost("narrow"));
    expect(narrow.value).toBe(false);
    setMedia("(max-width: 700px)", true);
    expect(narrow.value).toBe(true);
    expect(mediaListeners("(max-width: 700px)")).toBe(1);
    stop();
    expect(mediaListeners("(max-width: 700px)")).toBe(0);
  });
});
