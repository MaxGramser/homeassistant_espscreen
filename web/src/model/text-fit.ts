// A line as the glass cuts it (app 0.4.90): the whole text where it fits its box, else as much of it as fits before
// "...", the three dots LVGL writes into a label that is too short (LV_LABEL_LONG_DOT), measured in the screens' Roboto
// at the glass's size. The browser's own ellipsis is one narrower glyph at another place. Without a canvas (the tests)
// the text stays whole and the box cuts it.
import { ref } from "vue";
import { textWidth } from "./ui-scale";

// The page's Roboto (styles/tokens.css "Bar Roboto"): measured once it has arrived, and again when it does.
const arrived = ref(0);
let context: CanvasRenderingContext2D | null | undefined;
function measurer() {
  if (context !== undefined) return context;
  try { context = typeof document === "undefined" ? null : document.createElement("canvas").getContext("2d"); } catch { context = null; }
  if (context && document.fonts) for (const weight of [400, 500, 700])
    document.fonts.load(`${weight} 20px "Bar Roboto"`).then(() => { cache.clear(); arrived.value++; }).catch(() => {});
  return context;
}
const cache = new Map<string, string>();

/** `text` in Roboto `weight` at `size` glass pixels within `width` of them, cut with "..." as the glass cuts it. */
export function dotted(text: string, size: number, weight: number, width: number) {
  void arrived.value;
  const c = measurer();
  if (!c || !text || width <= 0 || size <= 0) return text;
  const key = `${weight}:${size}:${width}:${text}`, known = cache.get(key);
  if (known !== undefined) return known;
  c.font = `${weight} ${size}px "Bar Roboto"`;
  // LVGL lays glyphs side by side without kerning (ESPHome's fonts carry none).
  if ("fontKerning" in c) c.fontKerning = "none";
  const fits = (s: string) => c.measureText(s).width <= width + 0.01;
  let result = text;
  if (!fits(text)) {
    const letters = [...text];
    let low = 0, high = letters.length;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      if (fits(`${letters.slice(0, mid).join("")}...`)) low = mid; else high = mid - 1;
    }
    result = `${letters.slice(0, low).join("")}...`;
  }
  if (cache.size > 2000) cache.clear();
  cache.set(key, result);
  return result;
}

/** `text`'s width in glass pixels in Roboto `weight` at `size` (text_width): measured, or estimated without a canvas. */
export function textPx(text: string, size: number, weight: number) {
  void arrived.value;
  const c = measurer();
  if (!c) return textWidth(text, size);
  c.font = `${weight} ${size}px "Bar Roboto"`;
  if ("fontKerning" in c) c.fontKerning = "none";
  return c.measureText(text).width;
}
