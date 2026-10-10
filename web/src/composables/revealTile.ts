// A tile brought into sight on the mockup once it is drawn: a tile opened from elsewhere (the overview's broken tiles, the
// sidebar, ⌘K) may stand on a page far to the side of the row of pages. Only the boxes around it that scroll move (the
// row of pages across, the canvas down), never the window: a phone's page would otherwise slide sideways under its sheet.
// Quiet motion unless the person asked for none. The id is a tile's instance id (hex digits), safe in a selector as it is.
import { nextTick } from "vue";

const scrolls = (element: HTMLElement, axis: "x" | "y") => {
  const style = getComputedStyle(element), overflow = axis === "x" ? style.overflowX : style.overflowY;
  return ["auto", "scroll"].includes(overflow) && (axis === "x" ? element.scrollWidth > element.clientWidth : element.scrollHeight > element.clientHeight);
};

export async function revealTile(id: string) {
  await nextTick();
  const tile = document.querySelector<HTMLElement>(`.pages [data-tile-id="${id}"]`);
  if (!tile) return;
  const behavior: ScrollBehavior = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  let across: HTMLElement | null = null, down: HTMLElement | null = null;
  for (let box = tile.parentElement; box && box !== document.body && (!across || !down); box = box.parentElement) {
    if (!across && scrolls(box, "x")) across = box;
    if (!down && scrolls(box, "y")) down = box;
  }
  const at = tile.getBoundingClientRect();
  if (across) {
    const room = across.getBoundingClientRect();
    across.scrollBy({ left: at.left + at.width / 2 - (room.left + room.width / 2), behavior });
  }
  if (down) {
    const room = down.getBoundingClientRect();
    const by = at.top < room.top ? at.top - room.top - 16 : at.bottom > room.bottom ? at.bottom - room.bottom + 16 : 0;
    if (by) down.scrollBy({ top: by, behavior });
  }
}
