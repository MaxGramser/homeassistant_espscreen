// Names written into ids and file names (model/slug.ts): a preview screen's id, a layout's file, the start of a screen's
// entity ids as the add-on makes it (core.entity_slug), and an ESPHome node name.
import { describe, expect, it } from "vitest";
import { entitySlug, nodeName, slug } from "../src/model/slug";

describe("a name as an id", () => {
  it("is lower case letters and digits with one separator between them", () => {
    expect(slug("Living room")).toBe("living-room");
    expect(slug("  Hall (2) ")).toBe("hall-2");
    expect(slug("!!!")).toBe("");
    // A layout's file keeps the separator at its ends, as it always did.
    expect(slug("Hall (2)", { trim: false })).toBe("hall-2-");
  });
  it("starts the entity ids as Home Assistant gives them", () => {
    expect(entitySlug("Living Room screen")).toBe("living_room_screen");
    expect(entitySlug("__Kitchen!__")).toBe("kitchen");
  });
  it("follows ESPHome's rule for a node name", () => {
    expect(nodeName("Café Zürich")).toBe("cafe-zurich");
    expect(nodeName("2nd floor")).toBe("nd-floor");
    expect(nodeName("A very long name for a screen in the hall")).toBe("a-very-long-name-for-a-screen");
    expect(nodeName("123")).toBe("screen");
  });
});
