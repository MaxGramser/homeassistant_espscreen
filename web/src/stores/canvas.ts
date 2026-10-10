// The mockup's sizes (the canvas): the screen's glass drawn at the editor's scale, with the top bar, the margins and gaps
// of the grid and the page bar as the screen draws them (model/ui-scale.ts, model/topbar.ts), the compact look, and the
// larger names a roomy cell takes. Only getters, worked out from the draft's shape and grid (store.ts) and the
// screen's navigation settings; nothing here changes.
import { defineStore } from "pinia";
import { computed } from "vue";
import * as pages from "../model/pages";
import { barMetricsFor } from "../model/topbar";
import { frameOf, pillMetrics, uiScale } from "../model/ui-scale";
import { screenShape, state } from "../store";
import { useSettingsStore } from "./settings";

// The tile grid of a page, as CSS variables: the mockup is the screen's own shape, whatever board it is. Every mockup has
// the same shorter side (MOCKUP_SIDE), so a screen keeps its size against its neighbours: a 800 x 480 page lying down is
// wider than a square 480 x 480 one, and the same glass standing up is taller, not narrower. Drawn the same height
// instead, a 480 x 800 screen came out 180 px wide, smaller than the 480 x 480 Guition though it has more glass. Very wide
// glass is capped so it still fits beside a neighbour on a laptop.
const MOCKUP_SIDE = 300;

export const useCanvasStore = defineStore("canvas", () => {
  const settings = useSettingsStore();

  // The top bar of the mockup at the screen's own width and density (model/topbar.ts).
  const barMetrics = computed(() => barMetricsFor(screenShape.value));
  // Whether the screen keeps room for its page bar under the tiles: on every page, once the layout has more than one
  // (page_protocol.h footer), so a card is lower on all of them.
  const pageBarShown = computed(() => Boolean(state.document && pages.navigationFooter(state.document, settings.navigationSettings())));
  const deviceStyle = computed(() => {
    const shape = screenShape.value, grid = state.documentGrid;
    // To a tenth of a pixel, not a whole one: on a 1280 x 800 screen the nearest whole pixel of width would make the
    // mockup a pixel taller than the rest. Every board lying down lands on a whole number anyway.
    const width = shape.width >= shape.height ? Math.min(560, (MOCKUP_SIDE * shape.width) / shape.height) : MOCKUP_SIDE;
    const rounded = Math.round(width * 10) / 10;
    // The glass in editor pixels, and the -/+ pill at the size the screen draws it (model/ui-scale.ts).
    const glass = rounded / shape.width, pill = pillMetrics(shape);
    const [watch, text] = [pill.faces[0] ?? 22, pill.faces[1] ?? pill.faces[0] ?? 14];
    // The page in the glass's proportions (app 0.4.74): the top bar from the top of the glass down to where the tile area
    // starts, the margins and gaps of the grid, and the page bar where the layout has one, so a card is as high against
    // its page as on the screen (ui-scale cardHeight). Before, the mockup's own 10 px frame, 8 px gaps and 24 px page bar
    // left a card of a 4-inch Guition with three rows and three pages 65 px high where the glass's is 117 x 0.625.
    const frame = frameOf(shape), paged = pageBarShown.value;
    const g = (n: number) => `${(n * glass).toFixed(2)}px`;
    return {
      "--glass": String(glass),
      "--frame-top": g(frame.top),
      "--frame-side": g(frame.margin),
      "--frame-bottom": g(paged ? 0 : frame.margin),
      "--frame-bar": g(frame.page_bar),
      "--frame-gap-x": g(frame.gap),
      "--frame-gap-y": g(frame.gap_y),
      "--frame-pad": g(frame.tile_pad),
      "--pill-h": `${(pill.height * glass).toFixed(2)}px`,
      "--pill-in": `${(pill.inset * glass).toFixed(2)}px`,
      "--pill-key": `${(pill.key * glass).toFixed(2)}px`,
      "--face-watch": `${(watch * glass).toFixed(2)}px`,
      "--face-text": `${(text * glass).toFixed(2)}px`,
      // A range's chip (runtime_tiles range_chip): its icon is a key's icon, beside the number with the glass's gap.
      "--chip-icon": `${((("fonts" in shape ? shape.fonts?.icon_mini : undefined) ?? (uiScale(shape).large ? 26 : 18)) * glass).toFixed(2)}px`,
      "--chip-pad": `${(uiScale(shape).px(6) * glass).toFixed(2)}px`,
      "--screen-aspect": `${shape.width} / ${shape.height}`,
      "--screen-columns": String(grid?.columns ?? shape.columns),
      "--screen-rows": String(grid?.rows ?? shape.rows),
      // A wide tile is two cells, or the only one on a single-column screen (layout.ts: spanOf).
      "--screen-wide-span": String(Math.min(2, grid?.columns ?? shape.columns)),
      "--mockup-width": `${rounded}px`,
    };
  });
  // The compact look: the board declares it (LOOK in its board file, served with the shape); a shape from an add-on that
  // does not say it is taken by its shorter side, the CYD being the only compact board there was. The shorter side and not
  // the width, because a screen keeps its look when it is built standing up: a 480 x 800 Waveshare is still the standard
  // look, and on its width alone it would have read as a CYD.
  const isCompact = computed(() => {
    const shape = screenShape.value;
    return shape.look ? shape.look === "compact" : Math.min(shape.width, shape.height) < 300;
  });
  // A plain card's name gets larger letters on the compact look where its cell has 30 mm of room
  // (runtime_tiles::name_font): one column standing up, a 4-inch glass. The cell's width as the screen lays it out: its
  // 9 px margins and 8 px gaps, then the card's padding (8 px of the look) and border.
  const roomyNames = computed(() => {
    const shape = screenShape.value;
    if (!isCompact.value || !shape.dpi) return false;
    const columns = state.documentGrid?.columns ?? shape.columns;
    const pad = Math.round((8 * shape.dpi) / 143);
    const cell = (shape.width - 18 - (columns - 1) * 8) / columns - 2 * pad - 2;
    return cell >= Math.floor((shape.dpi * 30 + 12) / 25);
  });

  return { barMetrics, pageBarShown, deviceStyle, isCompact, roomyNames };
});
