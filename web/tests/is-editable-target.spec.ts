// The page's own keys leave a field alone (composables/isEditableTarget.ts), the template tile's code field in its
// shadow root too.
import { describe, expect, it } from "vitest";
import { isEditableTarget } from "../src/composables/isEditableTarget";

describe("isEditableTarget", () => {
  it("knows inputs and contenteditable", () => {
    const input = document.createElement("input");
    const div = document.createElement("div");
    expect(isEditableTarget(input)).toBe(true);
    expect(isEditableTarget(div)).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });
  it("looks into a shadow root, where the focused field decides", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const shadow = host.attachShadow({ mode: "open" });
    const field = document.createElement("div");
    field.setAttribute("contenteditable", "true");
    field.tabIndex = 0;
    shadow.append(field);
    expect(isEditableTarget(host)).toBe(false);
    field.focus();
    expect(isEditableTarget(host)).toBe(true);
    host.remove();
  });
});
