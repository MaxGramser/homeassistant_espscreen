// The top bar rules: the same wording and arithmetic as header_bar.h in the firmware.
import { describe, expect, it } from "vitest";
import { agoText, LOOK_BARS, barGaps, barLayout, clockText, dateText, dotted, itemKey } from "../src/model/topbar";
import type { HeaderItem } from "../src/types";

describe("words for the time since a change", () => {
  const now = 1_000_000;
  it("uses the firmware's thresholds and wording", () => {
    expect(agoText(now - 10, now)).toBe("Just now");
    expect(agoText(now - 300, now)).toBe("5 min ago");
    expect(agoText(now - 3600, now)).toBe("1 hour ago");
    expect(agoText(now - 7200, now)).toBe("2 hours ago");
    expect(agoText(now - 90000, now)).toBe("Yesterday");
    expect(agoText(now - 3 * 86400, now)).toBe("3 days ago");
    expect(agoText(now - 8 * 86400, now)).toBe("1 week ago");
    expect(agoText(now - 40 * 86400, now)).toBe("1 month ago");
    expect(agoText(now - 400 * 86400, now)).toBe("1 year ago");
  });
  it("looks ahead too", () => {
    expect(agoText(now + 120, now)).toBe("In 2 min");
    expect(agoText(now + 3600, now)).toBe("In 1 hour");
    expect(agoText(now + 100000, now)).toBe("Tomorrow");
    expect(agoText(now + 5 * 86400, now)).toBe("In 5 days");
  });
});

describe("clock and date", () => {
  const evening = new Date(2026, 8, 15, 19, 5);
  it("formats the clock the way the screen does", () => {
    expect(clockText(true, evening)).toBe("19:05");
    // The clock card's big digits: no leading zero, no day period (its font has no letters).
    expect(clockText(false, evening)).toBe("7:05");
    expect(clockText(false, new Date(2026, 8, 15, 0, 30))).toBe("12:30");
    // The top bar: with the language's day period, as screen_text::clock_text writes it.
    expect(clockText(false, evening, "en")).toBe("7:05 PM");
    expect(clockText(false, new Date(2026, 8, 15, 0, 30), "en")).toBe("12:30 AM");
    expect(clockText(true, evening, "en")).toBe("19:05");
  });
  it("writes the date short", () => {
    expect(dateText(evening)).toBe("Tu 15 Sep");
  });
});

describe("the bar's geometry", () => {
  it("uses the firmware's integer gaps", () => {
    expect(barGaps(15)).toEqual({ icon: 6, item: 19, name: 24 });
    expect(barGaps(1)).toEqual({ icon: 2, item: 6, name: 8 });
  });
  it("drops items from the left when the name needs its room", () => {
    const items: HeaderItem[] = Array.from({ length: 6 }, (_, i) => ({ type: "entity", entity: `sensor.s${i}` }));
    const view = () => ({ icon: "F050F", text: "1234.5 °C", shown: true });
    const lay = barLayout(items, LOOK_BARS.compact, "Living room", view);
    expect(lay.parts).toHaveLength(6);
    expect(lay.placed.length).toBeLessThan(6);
    expect(lay.dropped.size).toBe(6 - lay.placed.length);
    // The dropped ones are the first ones; the placed ones sit left to right and end at the right edge.
    expect([...lay.dropped].every((i) => i < lay.placed[0].index)).toBe(true);
    for (let i = 1; i < lay.placed.length; i++) expect(lay.placed[i].x!).toBeGreaterThan(lay.placed[i - 1].x!);
    expect(lay.nameRoom).toBeGreaterThan(0);
  });
  it("keeps a hidden item out of the bar and gives the dial its own width", () => {
    const items: HeaderItem[] = [{ type: "entity", entity: "binary_sensor.door" }, { type: "analog" }];
    const view = (item: HeaderItem) => (item.type === "analog" ? { analog: true, shown: true } : { icon: "F050F", text: "Open", shown: false });
    const lay = barLayout(items, LOOK_BARS.standard, "Home", view);
    expect(lay.placed.map((p) => p.index)).toEqual([1]);
    expect(lay.placed[0].dial).toBeGreaterThan(0);
  });
  it("shortens a long name with an ellipsis, like LVGL", () => {
    const font = '500 27px "Bar Roboto"';
    expect(dotted("Living room", font, 10000)).toBe("Living room");
    const short = dotted("A very long living room name", font, 120);
    expect(short.endsWith("...")).toBe(true);
    expect(short.length).toBeLessThan("A very long living room name".length);
  });
  it("keys an item by what it shows, never by its id (app 0.4.1)", () => {
    expect(itemKey({ id: "x", type: "entity", entity: "a", content: "state" })).toBe(itemKey({ type: "entity", entity: "a" }));
    expect(itemKey({ type: "entity", entity: "a", show: "active" })).not.toBe(itemKey({ type: "entity", entity: "a" }));
  });
});
