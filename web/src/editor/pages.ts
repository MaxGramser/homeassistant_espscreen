// Editing the draft's pages (stores/document.ts): adding, moving, copying and removing a page, the home page, a page left
// out of the page buttons, its home key, the titles of the screen and of each page, a Go to page tile's link, how many
// pages the row shows, and what the screen's navigation settings leave out of reach. Plain functions over the stores, as
// the draft's tiles are (editor/tiles.ts): each asks for the stores when it is called.
import { andList, t } from "../i18n";
import { entriesOf } from "../model/layout";
import pageRules from "../model/page-rules.json";
import * as pages from "../model/pages";
import { useDocumentStore } from "../stores/document";
import { useDragStore } from "../stores/drag";
import { useScreenStore } from "../stores/screen";
import { useSettingsStore } from "../stores/settings";
import { useUiStore } from "../stores/ui";
import type { PageLayout, PageTile } from "../types";

const toast = (message: string) => useUiStore().toast(message);

export function addPage(bar?: PageLayout["pages"][number]["topbar"]) {
  const doc = useDocumentStore();
  if (doc.document && doc.document.pages.length >= doc.editorLayout.grid.pages) { toast(t("addon.errors.pages.pages_full")); return false; }
  let created = "";
  if (doc.editDocument((draft) => {
    const selected = draft.pages.find((page) => page.id === doc.selectedPageId) || draft.pages.at(-1)!;
    const page = pages.emptyPage(bar || selected.topbar); created = page.id; draft.pages.push(page);
  })) { doc.selectedPageId = created; return true; }
  return false;
}
export function movePage(from: number, to: number) {
  const doc = useDocumentStore(), document = doc.document, grid = doc.documentGrid;
  if (!document || !grid || from === to || !Number.isInteger(from) || !Number.isInteger(to) ||
      from < 0 || to < 0 || from >= document.pages.length || to >= document.pages.length) return false;
  // Older firmware knows no home page of its own: it starts on the first page, so there the home page stays first (app
  // 0.4.1). Before, the move was taken and the save refused it later with no clue why.
  if (!useScreenStore().pageReady && (from === 0 || to === 0)) { toast(t("editor.pages.update_notice")); return false; }
  try { return doc.applyDocument(pages.reorderPage(document, doc.heldTo(grid), document.pages[from]?.id, to)); }
  catch (error: any) { toast(error.message); return false; }
}
export function removePage(page: number) {
  const doc = useDocumentStore(), document = doc.document, grid = doc.documentGrid;
  if (!document || !grid || !document.pages[page] || document.pages.length === 1) return;
  const id = document.pages[page].id;
  try {
    const next = pages.deletePage(document, doc.heldTo(grid), id);
    const removed = doc.layout!.tiles.length - pages.projectLayout(next, grid).tiles.length;
    if (doc.applyDocument(next)) doc.undoToast(removed ? t("editor.layout.page_removed_tiles", { page: page + 1 }, removed)
      : t("editor.layout.page_removed", { page: page + 1 }));
  } catch (error: any) { toast(error.message); }
}
export function setHomePage(id: string) { return useDocumentStore().editDocument((draft) => { draft.homePageId = id; }); }
export function connectTile(tileId: string, target: string | "home") {
  return useDocumentStore().editDocument((draft) => {
    const tile = draft.pages.flatMap((page) => page.tiles).find((item) => item.id === tileId);
    if (tile?.content.kind !== "navigation") throw new Error(t("addon.errors.pages.select_link"));
    tile.content.target = target === "home" ? { kind: "home" } : { kind: "page", pageId: target };
  });
}
export function setPageExcluded(id: string, excluded: boolean) {
  return useDocumentStore().editDocument((draft) => { const page = draft.pages.find((item) => item.id === id); if (page) page.navigation.excludeFromPagination = excluded; });
}
// A full copy of a page puts its tiles on the screen twice: a page tile when the firmware takes that (0.2.65), any other
// entity from 0.16.0, but never a clock with keys, which is on a screen once.
export function pageCopyable(page: PageTile[] | undefined) {
  const scr = useScreenStore();
  return Boolean(page?.every((tile) => tile.content.kind === "navigation" ? scr.pageTilesRepeat :
    scr.entityTilesRepeat && !(tile.content.kind === "builtin" && `screen.${tile.content.name}` in pageRules.keyHolders)));
}
export function duplicateEditorPage(id: string, empty: boolean) {
  const doc = useDocumentStore(), document = doc.document, grid = doc.documentGrid;
  if (!document || !grid) return false;
  if (document.pages.length >= doc.editorLayout.grid.pages) { toast(t("addon.errors.pages.pages_full")); return false; }
  const copied = empty ? 0 : (document.pages.find((page) => page.id === id)?.tiles.length || 0);
  if ((doc.layout?.tiles.length || 0) + copied > doc.tileLimit) { toast(t("addon.errors.layout.tiles_max", doc.tileLimit)); return false; }
  try { return doc.applyDocument(pages.duplicatePage(document, doc.screenGridOf(grid), id, empty)); }
  catch (error: any) { toast(error.message); return false; }
}
export function setPageHomeControl(id: string, visible: boolean) {
  return useDocumentStore().editDocument((draft) => { const page = draft.pages.find((item) => item.id === id); if (page)
    page.topbar.leading = visible ? page.topbar.leading.length ? page.topbar.leading : [{ id: pages.instanceId(), kind: "home" }] : []; });
}

// ---- Titles ----
// The screen's own title: what the top bar says on every page that has no title of its own, and what the editor asks for
// first. Nothing is named after it - a screen's actions and sensors carry its device name - so renaming it breaks no
// automation.
export const screenTitle = () => useDocumentStore().layout?.title ?? "";
export function setScreenTitle(value: string) {
  const doc = useDocumentStore();
  if (!doc.layout) return;
  doc.editDocument((draft) => { draft.title = value; }, "screen-title");
}
// The title of one page (app 0.2.105), the one thing the top bar's inspector asks per page. A title belongs to the page
// and travels with it, page 1 included (app 0.2.123), so reordering the row never costs a name. Stored as one entry per
// page, empty meaning the screen's own title, trailing empty ones dropped, so a screen where nobody set one carries nothing.
export const pageTitle = (page: number) => useDocumentStore().layout?.page_titles?.[page] ?? "";
// What stands above a position in the row: the title of the page drawn there, which while a page is being moved is not
// the page that started there, and the screen's own title for a page that has none.
export const pageTitleShown = (page: number) => {
  const order = useDragStore().page?.order;
  return pageTitle(order ? order[page] ?? page : page) || useDocumentStore().layout?.title || "";
};
export function setPageTitle(page: number, value: string) {
  const doc = useDocumentStore();
  doc.editDocument((draft) => { if (draft.pages[page]) draft.pages[page].topbar.title = value.trim() ? { source: "text", text: value } : { source: "screen" }; },
    `page:${doc.document?.pages[page]?.id}`);
}

// ---- The row of pages ----
export function pagesShown() {
  const doc = useDocumentStore(), dragging = useDragStore(), layout = doc.layout, { grid } = doc.editorLayout;
  if (!layout) return 1;
  const shown = doc.editorLayout.pageCount(dragging.preview || entriesOf(layout), layout.pages);
  // While a tile is being dragged, one more page waits after the last one. A page on the move is looking for a place in
  // the row it is already in, so the row stays as long as it is.
  return dragging.active && !dragging.page && shown < grid.pages ? shown + 1 : shown;
}
// What the screen's navigation settings (stores/settings.ts) leave out of reach: a page no button, swipe or Go to page
// tile leads to, and one with no way back home.
export function pageReachWarning() {
  const document = useDocumentStore().document;
  if (!document) return "";
  const result = pages.reachability(document, useSettingsStore().navigationSettings());
  const named = (ids: string[]) => t("editor.screen_settings.reach.pages", {
    list: andList(ids.map((id) => document.pages.findIndex((page) => page.id === id) + 1)),
  }, ids.length);
  const messages: string[] = [];
  if (result.unreachable.length) messages.push(t("editor.pages.unreachable", { pages: named(result.unreachable) }));
  if (result.noWayHome.length) messages.push(t("editor.pages.no_way_home", { pages: named(result.noWayHome) }));
  return messages.join(" ");
}
