// The right mouse button on the mockup (docs/PAGES.md, "Menus"): a tile, the tiles chosen together, an empty cell and
// the page each have one menu, the same as their ···, and the button chooses the thing first. A finger's long press
// opens nothing: on a touch screen a held tile drags.
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import DevicePage from "../src/components/DevicePage.vue";
import { forgetCopied, shortcut } from "../src/editor/clipboard";
import { loadLayout } from "./helpers/fixtures";
import { useDocumentStore } from "../src/stores/document";
import { useInspectorStore } from "../src/stores/inspector";

let doc: ReturnType<typeof useDocumentStore>;
let insp: ReturnType<typeof useInspectorStore>;
beforeEach(() => {
  doc = useDocumentStore();
  insp = useInspectorStore();
  forgetCopied();
  document.body.innerHTML = "";
});

function page() {
  loadLayout({ title: "Living", tiles: [{ entity: "light.a", name: "", slot: 0 }, { entity: "light.b", name: "", slot: 1 }] } as any);
  return mount(DevicePage, { props: { page: 0, entries: doc.layout!.tiles.map((tile) => ({ tile, slot: tile.slot })), pages: 1, moving: null }, attachTo: document.body });
}
async function rightClick(element: Element, pointerType = "mouse") {
  element.dispatchEvent(Object.assign(new Event("pointerdown", { bubbles: true, cancelable: true }), { pointerType, button: 2 }));
  // The menu event comes after the press: at once for a mouse, after a long press for a finger.
  await nextTick();
  element.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 10, clientY: 10 }));
    // Reka opens it a tick after the event.
  await nextTick();
  await nextTick();
}
async function close() {
  document.querySelector("[role='menu']")?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await nextTick();
}
const items = () => [...document.querySelectorAll("[role='menu'] [role='menuitem']")].map((item) => [...item.children].filter((part) => !part.classList.contains("ui-menu-icon")).map((part) => part.textContent!.trim()).join(" "));

describe("the right mouse button on the mockup", () => {
  it("opens a tile and offers its own menu, the one behind its inspector's ···", async () => {
    const view = page();
    await rightClick(view.find(".tile[data-slot='0']").element);
    expect(insp.inspector).toEqual({ kind: "tile" });
    expect(doc.currentTile?.entity).toBe("light.a");
    expect(items()).toEqual(["Rename", "Show another entity", "Read current data", `Copy ${shortcut("C")}`, `Cut ${shortcut("X")}`, "Remove ⌫"]);
    await close();
    view.unmount();
  });

  it("keeps the tiles chosen together and offers what goes for all of them", async () => {
    const view = page();
    insp.selectTiles(doc.layout!.tiles.map((tile) => tile.id!));
    await rightClick(view.find(".tile[data-slot='1']").element);
    expect(insp.inspector?.kind).toBe("tiles");
    expect(items()).toEqual([`Copy ${shortcut("C")}`, `Cut ${shortcut("X")}`, "Remove 2 tiles ⌫"]);
    await close();
    view.unmount();
  });

  it("offers to fill an empty cell, and marks it only for what is chosen", async () => {
    const view = page();
    const cell = view.find(".cell").element as HTMLElement;
    await rightClick(cell);
    expect(items()).toEqual(["Add a tile here", `Paste here ${shortcut("V")}`]);
    // Nothing copied yet, so nothing to paste; the cell shows as marked while its menu is open, and is not marked yet.
    expect(document.querySelector(".cell-paste")!.hasAttribute("data-disabled")).toBe(true);
    expect(cell.classList.contains("insert-here")).toBe(true);
    expect(insp.insertAt).toBe(-1);
    (document.querySelector(".cell-add") as HTMLElement).click();
    await nextTick();
    expect(insp.insertAt).toBe(Number(cell.dataset.slot));
    view.unmount();
  });

  it("offers the page's menu anywhere else on the page, and opens its settings", async () => {
    const view = page();
    await rightClick(view.find(".bar-wrap").element);
    expect(insp.inspector).toEqual({ kind: "page", id: doc.document!.pages[0].id });
    expect(items()[0]).toBe("Page settings");
    expect(items().at(-1)).toContain("Remove page");
    await close();
    view.unmount();
  });

  it("opens nothing on a finger's long press", async () => {
    const view = page();
    await rightClick(view.find(".tile[data-slot='0']").element, "touch");
    expect(document.querySelector("[role='menu']")).toBeNull();
    view.unmount();
  });
});
