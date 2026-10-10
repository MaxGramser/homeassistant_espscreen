// Whether a key went to a field that takes text (composables/isEditableTarget.ts).
import { describe, expect, it } from "vitest";
import { isEditableTarget } from "../../src/composables/isEditableTarget";

describe("a field that takes text", () => {
  it("is an input, a text area or something editable, and what is inside one", () => {
    document.body.innerHTML = `<input id="a"><textarea id="b"></textarea><div contenteditable="true"><span id="c"></span></div><button id="d"></button><select id="e"></select>`;
    expect(["a", "b", "c", "d", "e"].map((id) => isEditableTarget(document.getElementById(id)))).toEqual([true, true, true, false, false]);
    expect([isEditableTarget(null), isEditableTarget(document), isEditableTarget(window)]).toEqual([false, false, false]);
  });
});
