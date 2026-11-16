// Editing the draft's sections (docs/PAGES.md "Sections"): making one of the chosen tiles, its title, icon and summary,
// its size, taking it away, and the loose tiles as a row of their own. Plain functions over the stores, as the draft's
// tiles are (editor/tiles.ts); the rules are model/sections.ts and model/pages.ts. Every change is one step of undo.
import { t } from "../i18n";
import * as pages from "../model/pages";
import * as sections from "../model/sections";
import { useDocumentStore } from "../stores/document";
import { useDragStore } from "../stores/drag";
import { useInspectorStore } from "../stores/inspector";
import { useScreenStore } from "../stores/screen";
import { useUiStore } from "../stores/ui";
import type { Section } from "../types";
import { commitArrangement } from "./tiles";

const toast = (message: string) => useUiStore().toast(message);
const gridOf = () => {
  const doc = useDocumentStore();
  return doc.documentGrid ? doc.screenGridOf(doc.documentGrid) : null;
};

/** Whether this screen draws sections: a board of the full tier (docs/MODULES.md). The 4 MB boards get none. */
export const sectionsOffered = () => useScreenStore().currentScreen?.sections === true;

/** What an edit would give, drawn on the mockup until it is applied or left (the drag store's preview). */
export function showEdit(edit: sections.SectionEdit | null) {
  const dragging = useDragStore();
  if (dragging.active) return;
  if (!edit || "refused" in edit) { dragging.preview = null; dragging.previewBlocks = null; return; }
  dragging.preview = edit.entries;
  dragging.previewBlocks = edit.blocks;
}
export function apply(edit: sections.SectionEdit, then?: (done: Exclude<sections.SectionEdit, { refused: string }>) => void) {
  showEdit(null);
  if ("refused" in edit) { toast(t(edit.refused)); return false; }
  const done = commitArrangement(edit.entries, undefined, edit.blocks);
  if (done && then) then(edit);
  return done;
}

/** The section the chosen tiles would make, for the preview while its name is typed. */
export function proposedSection(title = "") {
  const doc = useDocumentStore(), insp = useInspectorStore(), grid = gridOf();
  if (!doc.layout || !grid) return null;
  return sections.makeSection(doc.layout, grid, insp.chosenTiles, title || t("editor.sections.untitled"));
}
/** Whether the chosen tiles can make a section: loose tiles of one page on a screen that draws sections. */
export function canMakeSection() {
  const edit = sectionsOffered() ? proposedSection() : null;
  return Boolean(edit && !("refused" in edit));
}
/** The chosen tiles become a section named `title`; its drawer opens. */
export function makeSection(title: string) {
  const edit = proposedSection(title.trim() || t("editor.sections.untitled"));
  if (!edit) return false;
  const insp = useInspectorStore(), before = new Set((useDocumentStore().layout?.sections ?? []).map((b) => b.id));
  return apply(edit, (done) => {
    insp.makingSection = false;
    const made = done.blocks.find((b) => !before.has(b.id));
    if (made) insp.openSection(made.id);
  });
}
/** A new, empty section on `page`, at the empty cell `slot` when one was chosen (its menu, the library while a cell is
 * marked), else on the first free cells of the page. Its drawer opens with the name selected, ready to be typed over;
 * its cells then take tiles as any cell does. */
export function addSection(page: number, slot = -1) {
  const doc = useDocumentStore(), insp = useInspectorStore(), grid = gridOf();
  if (!doc.layout || !grid || !sectionsOffered()) return false;
  const local = slot >= 0 ? slot % (grid.columns * grid.rows) : -1;
  const at = local >= 0 ? { row: Math.floor(local / grid.columns), column: local % grid.columns } : null;
  const edit = sections.emptySection(doc.layout, grid, page, at, t("editor.sections.untitled"));
  const before = new Set((doc.layout.sections ?? []).map((b) => b.id));
  return apply(edit, (done) => {
    insp.insert = null;
    const made = done.blocks.find((b) => !before.has(b.id));
    if (made) { insp.openSection(made.id); insp.renameSection(made.id); }
  });
}
export function resizeSection(id: string, columns: number, rows: number) {
  const doc = useDocumentStore(), grid = gridOf();
  if (!doc.layout || !grid) return false;
  return apply(sections.resizeSection(doc.layout, grid, id, columns, rows));
}
export function removeSection(id: string, withTiles = false) {
  const doc = useDocumentStore(), grid = gridOf();
  if (!doc.document || !grid) return false;
  let done = false;
  try { done = doc.applyEdit(pages.removeSection(doc.document, grid, id, withTiles)); }
  catch (error: any) { toast(error.message); }
  if (done) doc.undoToast(t(withTiles ? "editor.sections.removed_with_tiles" : "editor.sections.removed"));
  return done;
}
export function looseRowAbove(page: number) {
  const doc = useDocumentStore(), grid = gridOf();
  if (!doc.layout || !grid) return false;
  return apply(sections.looseRowAbove(doc.layout, grid, page));
}
/** A section's own fields: its title, its icon, the entity its band sums up. Undefined takes one away. */
export function setSectionFields(id: string, fields: Partial<Pick<Section, "title" | "icon" | "summary" | "contrast" | "contrastTiles">>, field?: string) {
  return useDocumentStore().editDocument((draft) => {
    const section = draft.pages.flatMap((page) => page.sections ?? []).find((item) => item.id === id);
    if (!section) throw new Error(t("addon.errors.pages.fields"));
    for (const [key, value] of Object.entries(fields) as [keyof typeof fields, string | boolean | undefined][]) {
      // Left out, a choice is off (contrast) or none (icon, summary); a title is never taken away.
      if (value === undefined || value === "" || value === false) { if (key !== "title") delete section[key]; }
      else Object.assign(section, { [key]: value });
    }
  }, field);
}
