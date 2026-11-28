// The screen's own colours where the editor draws its glass (model/glass-colours.ts): the firmware's roles, in the light
// look the mockup draws, set once on the page's root. The stylesheet takes them from there (.device, the library's strip).
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { applyGlassColours, glassColours } from "../src/model/glass-colours";
import UiSegmented from "../src/components/ui/UiSegmented.vue";

const theme = readFileSync("../components/smart_display/theme.h", "utf8");
const role = (name: string) => `#${theme.match(new RegExp(`/\\* ${name} \\*/\\s+\\{0x([0-9A-F]{6})`))![1].toLowerCase()}`;

describe("the glass's colours", () => {
  it("are the firmware's page and word roles, light", () => {
    expect(glassColours()).toEqual({ "--glass-page": role("PAGE"), "--glass-ink": role("INK"), "--glass-ink-soft": role("INK_SOFT"), "--glass-muted": role("MUTED") });
  });
  it("are set on the root, and the stylesheet writes no colour of its own for the page mockup", () => {
    applyGlassColours();
    expect(document.documentElement.style.getPropertyValue("--glass-page")).toBe(role("PAGE"));
    const css = readFileSync("src/styles/app.css", "utf8");
    expect(css).toMatch(/\.device \{ background: var\(--glass-page\);[^}]*color: var\(--glass-ink\);/);
    // The glass has one colour in the stylesheet: no rule writes the page's own number.
    const page = role("PAGE"), ink = role("INK");
    expect(css.toLowerCase()).not.toContain(`background: ${page}`);
    expect(css.toLowerCase()).not.toContain(`${page};`);
    expect(css.toLowerCase()).not.toMatch(new RegExp(`\\.(bar-strip|mini-page|live|orient-glass|strip-slot)[^{]*\\{[^}]*${ink}`));
  });
});

describe("a segmented choice (UiSegmented)", () => {
  const segments = [{ value: "tiles", label: "Tiles" }, { value: "list", label: "List" }];
  it("takes another choice, and never goes off on a second press", async () => {
    const view = mount(UiSegmented, { props: { modelValue: "tiles", segments, label: "View" } });
    const [tiles, list] = view.findAll("button");
    expect(tiles.attributes("data-state")).toBe("on");
    await list.trigger("click");
    expect(view.emitted("update:modelValue")).toEqual([["list"]]);
    await tiles.trigger("click");
    expect(view.emitted("update:modelValue")).toEqual([["list"]]);
  });
});
