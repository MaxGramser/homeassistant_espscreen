// Pages of parts (model/parts.ts, docs/PAGES.md "Pages of parts"): Settings, a screen's Settings tab and Events share one
// list of parts, in cards like Home Assistant's own Settings.
import { describe, expect, it } from "vitest";
import { cardsOf } from "../src/model/parts";
import { EVENT_PARTS, PART_LOOK } from "../src/model/settings-parts";

describe("a page of parts", () => {
  it("puts its rows in their cards, in order, and leaves out a card with none", () => {
    const rows = [{ id: "a", card: 2 }, { id: "b", card: 0 }, { id: "c", card: 2 }];
    expect(cardsOf(rows).map((card) => card.map((row) => row.id))).toEqual([["b"], ["a", "c"]]);
  });

  it("gives every part of Events a colour and a card: what automations fire, then what the screens follow", () => {
    expect(cardsOf(EVENT_PARTS.map((id) => ({ id, ...PART_LOOK[id] }))).map((card) => card.map((row) => row.id)))
      .toEqual([["alerts", "doorbell"], ["alarm", "calls"]]);
    for (const id of EVENT_PARTS) expect(PART_LOOK[id].tone && PART_LOOK[id].icon).toBeTruthy();
  });
});
