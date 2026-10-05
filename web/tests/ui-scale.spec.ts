import { describe, expect, it } from "vitest";
import boardShapes from "../../screen_manager/app/boards.json";
import { energyFits, pillMetrics, textEms, uiScale, widestSetpoint, cardContent, cardHeight, cellContent, modeBar, watchCard, watchPadding, wideChip } from "../src/model/ui-scale";

describe("the firmware's sizes in the mockup (app 0.4.32)", () => {
  it("scales as ui::px does, from the board's density and look", () => {
    expect(uiScale({ dpi: 170, look: "standard" }).px(46)).toBe(46);
    expect(uiScale({ dpi: 143, look: "compact" }).px(34)).toBe(34);
    // A 7-inch at 133 dpi draws the standard look at 78 %: (46 x 78 + 50) / 100.
    expect(uiScale({ dpi: 133, look: "standard" }).px(46)).toBe(36);
    expect(pillMetrics({ dpi: 170, look: "standard", fonts: { watch_value: 38, sublabel_big: 21 } })).toEqual({ height: 48, inset: 4, key: 40, faces: [38, 21] });
  });
  it("measures a thermostat's -/+ by the widest temperature it can show, as tile_controls::widest_setpoint", () => {
    expect(widestSetpoint({ min_temp: 7, max_temp: 35, target_temp_step: 0.5 })).toBe("88.8°");
    expect(widestSetpoint({ min_temp: 45, max_temp: 95, target_temp_step: 1 })).toBe("88°");
    expect(widestSetpoint({ min_temp: 45, max_temp: 110, target_temp_step: 1 })).toBe("888°");
    expect(widestSetpoint({ min_temp: -20, max_temp: 30, target_temp_step: 1 })).toBe("-88°");
    expect(widestSetpoint({})).toBe("88.8°");   // 7 to 35 in halves when Home Assistant says nothing, as the firmware
    expect(textEms("88.8°")).toBeCloseTo(0.56 * 3 + 0.27 + 0.37);
  });
});

describe("a card's room as the glass works it out (app 0.4.32)", () => {
  const guition = { width: 480, dpi: 170, look: "standard", fonts: { watch_value: 38, sublabel_big: 21, sublabel: 16, icon_mini: 26 }, spacing: { margin: 16, gap: 12, tile_pad: 12 } };
  const cyd = { width: 320, dpi: 143, look: "compact", fonts: { watch_value: 22, sublabel_big: 14, sublabel: 11, icon_mini: 18 }, spacing: { margin: 9, gap: 6, tile_pad: 8 } };
  it("gives a wide card's controls one cell and a taller card its whole content (runtime_tiles cell_content_width)", () => {
    expect(cardContent(guition, 2, 1)).toBe(192);
    expect(cardContent(guition, 2, 2)).toBe(422);
    expect(cardContent(cyd, 2, 1)).toBe(130);
  });
  it("fits as many modes as climate_tile::bar_room does", () => {
    expect(modeBar(guition, "row", 192, 5)).toMatchObject({ room: 4, width: 4 * 46 + 8 });
    expect(modeBar(guition, "tall", 422, 5)).toMatchObject({ room: 5, width: 422 });
    expect(modeBar(guition, "row", 192, 1).room).toBe(0);
  });
  it("draws a wide chip's number as large as it fits alone, and its icon only where that fits too (range_chip)", () => {
    expect(wideChip(guition, 2, "88°")).toEqual({ face: 38, icon: true });
    expect(wideChip(cyd, 2, "88°")).toEqual({ face: 22, icon: false });
  });
  it("shares the page between its columns as LVGL's grid does, and a wide card's controls the cell rounded down", () => {
    // 1280 wide in five columns: LVGL gives 242, 242, 241, 242 and 241 pixels; cell_content_width 241 for each.
    const big = { width: 1280, dpi: 149, look: "standard", spacing: { margin: 14, gap: 11, tile_pad: 11 } };
    expect([0, 1, 2, 3, 4].map((start) => cardContent(big, 5, 1, start))).toEqual([218, 218, 217, 218, 217]);
    expect(cardContent(big, 5, 5)).toBe(1280 - 28 - 24);
    expect(cellContent(big, 5)).toBe(217);
    expect(cellContent(guition, 2)).toBe(cardContent(guition, 2, 1));
  });
});

describe("a Big number card as the glass lays it out (app 0.4.74)", () => {
  const guition = { width: 480, height: 480, dpi: 170, look: "standard",
    fonts: { watch_value: 38, sublabel_big: 21, sublabel: 16, label: 18, headline: 27, watch_icon: 18, setpoint: 64 },
    spacing: { margin: 16, gap: 12, gap_y: 12, tile_pad: 12, top: 56, page_bar: 47, circle: 54 } };
  it("gives a card the height LVGL's grid gives its row, with and without the page bar", () => {
    expect([0, 1, 2].map((row) => cardHeight(guition, 3, 1, row, true))).toEqual([118, 118, 117]);
    expect(cardHeight(guition, 3, 1, 0, false)).toBe(128);
    expect(watchPadding(guition, 3)).toBe(12);
  });
  it("keeps the number inside a card of three rows and three pages on a 4-inch Guition (GitHub #167)", () => {
    const content = cardHeight(guition, 3, 1, 2, true) - 2 * (12 + 1);
    const card = watchCard(guition, cardContent(guition, 2, 1), content, "217", "mg/dl");
    expect(card).toMatchObject({ stacked: true, circle: { y: 7, size: 26 }, value: { y: 39, size: 38, line: 45 } });
    expect(card.value.y + card.value.line).toBeLessThanOrEqual(content);
  });
  it("puts the name small in the corner and the number under it where four rows leave no room for the head", () => {
    const content = cardHeight(guition, 4, 1, 3, true) - 2 * (watchPadding(guition, 4) + 1);
    const card = watchCard(guition, cardContent(guition, 2, 1), content, "217", "mg/dl");
    expect(card).toMatchObject({ stacked: false, title: { y: 0, size: 16 }, value: { size: 38 } });
  });
});

describe("the sizes the energy card is offered (app 0.4.77)", () => {
  // The boards' own shapes, as the editor gets them: energy_card::offered on the glass with a page bar.
  const boards = boardShapes as Record<string, any>;
  const shape = (board: string, side = "landscape") => {
    const entry = Object.values(boards).find((b) => b.board === board)!, o = entry.orientations[side];
    return { shape: { ...entry, width: o.width, height: o.height }, across: o.columns, down: o.rows };
  };
  const fits = (board: string, columns: number, rows: number, side = "landscape") => {
    const { shape: s, across, down } = shape(board, side);
    return energyFits(s, across, down, columns, rows);
  };
  it("takes 2 x 2 where the diagram fits it, and a page of its own on a small glass", () => {
    expect(fits("guition", 2, 2)).toBe(true);
    expect(fits("waveshare7", 2, 2)).toBe(true);
    expect(fits("cyd", 2, 2)).toBe(false);
    expect(fits("cyd", 2, 3)).toBe(true);
    expect(fits("waveshare43", 2, 2)).toBe(false);
    expect(fits("cyd", 1, 3, "portrait")).toBe(true);
    expect(fits("cyd", 1, 2, "portrait")).toBe(false);
  });
});
