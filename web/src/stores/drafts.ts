// What this browser keeps of unsaved work on the screens (app 0.4.x): the draft of each screen, kept as it changes so it
// survives a reload, a closed tab or a crash (model/kept-draft.ts). Opening a screen whose kept draft differs from its
// saved layout offers it ("Unsaved changes from 10:42", Restore or Discard); restoring it is one step of undo, and a draft
// that started from an older save goes through the conflict (stores/document.ts takeDraft). A draft goes when it is
// saved, discarded, or left behind on purpose (Discard and open); a preview screen's never is kept, since its layout
// lives in this browser already. Each tab keeps the drafts it writes and never takes away another tab's.
import { defineStore } from "pinia";
import { computed, effectScope, onScopeDispose, shallowRef, watch } from "vue";
import { editorLanguage, languageMeta, t } from "../i18n";
import { usePreference } from "../composables/usePreference";
import { label } from "../model/change-label";
import { KEPT_PREFIX, keptKey, keptToForget, keptWhen, readKept, staleKept, writeKept, type KeptDraft } from "../model/kept-draft";
import * as pages from "../model/pages";
import { readStored } from "../storage";
import { useDocumentStore } from "./document";
import { useScreenStore } from "./screen";

export const useDraftsStore = defineStore("drafts", () => {
  const doc = useDocumentStore();
  const scr = useScreenStore();

  // This tab, for as long as the page is open: a reload is another tab.
  const tab = pages.instanceId();
  // The open screen's kept draft, written as it changes (no screen: a key nothing is written to). Another tab may write
  // the same key, so what is there is read from the storage itself (keptNow) rather than from this ref.
  const kept = usePreference<KeptDraft | null>(() => keptKey(scr.selected ?? ""), null,
    { serializer: { read: readKept, write: (draft) => (draft ? writeKept(draft) : "") } });
  const keptNow = (screen = scr.selected) => (screen ? readKept(readStored(keptKey(screen))) : null);
  // The kept draft offered for the open screen, until it is restored or discarded.
  const offer = shallowRef<KeptDraft | null>(null);
  const keeps = () => Boolean(scr.currentScreen && !scr.currentScreen.virtual);

  // ---- The drafts of every screen, in this browser's storage ----
  function storedKeys(): string[] {
    try { return Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i)).filter((key): key is string => Boolean(key?.startsWith(KEPT_PREFIX))); }
    catch { return []; }
  }
  // The stale drafts go, and past the most screens kept the oldest, leaving `room` for new ones.
  function prune(room = 0) {
    const kept = storedKeys().map((key) => ({ key, at: readKept(readStored(key))?.at ?? null }));
    for (const key of keptToForget(kept, Date.now(), room)) try { localStorage.removeItem(key); } catch { /* nothing kept anyway */ }
  }
  /** A screen's kept draft forgotten: discarded on purpose, or the screen removed. */
  function forget(screen: string | null) {
    if (!screen) return;
    if (screen === scr.selected) kept.value = null;
    try { localStorage.removeItem(keptKey(screen)); } catch { /* nothing kept anyway */ }
  }
  // The draft of the open screen as it is now: kept while it is unsaved, gone once it is not, unless the draft kept from
  // before waits for an answer. Only what this tab wrote is taken away.
  function persist() {
    if (!keeps() || !doc.document || !doc.documentGrid) return;
    if (doc.dirty) {
      if (!readStored(keptKey(scr.selected!))) prune(1);
      kept.value = { v: 1, tab, revision: doc.documentRevision, at: doc.editedAt || Date.now(), layout: pages.clone(doc.document),
        grid: { columns: doc.documentGrid.columns, rows: doc.documentGrid.rows }, upright: doc.documentUpright };
    } else if (!offer.value && keptNow()?.tab === tab) forget(scr.selected);
  }

  // ---- Opening a screen (stores/session.ts open) ----
  // Its kept draft is offered when it differs from what was saved; one that says the same, or is too old, goes quietly.
  function opened() {
    offer.value = null;
    const draft = keptNow();
    if (!draft || !keeps() || !doc.document || !doc.documentGrid) return;
    if (staleKept(draft, Date.now()) || (pages.sameValue(draft.layout, doc.document) && pages.sameGrid(draft.grid, doc.documentGrid)
      && draft.upright === doc.documentUpright)) { forget(scr.selected); return; }
    offer.value = draft;
  }
  /** The kept draft becomes the draft, as one step of undo. */
  function restore() {
    const draft = offer.value;
    if (!draft) return;
    offer.value = null;
    doc.takeDraft(draft, label("restored"));
    persist();
  }
  /** The kept draft goes; what is unsaved now is kept in its place. */
  function discard() {
    offer.value = null;
    forget(scr.selected);
    persist();
  }
  // "Unsaved changes from 10:42", in the editor's language and its clock.
  const offerText = computed(() => {
    const draft = offer.value;
    if (!draft) return "";
    const locale = editorLanguage();
    return t("editor.draft.kept", { time: keptWhen(draft.at, Date.now(), languageMeta(locale)?.clock !== "12", locale) });
  });

  // ---- Started once the page is on the screen (stores/session.ts start); the returned function stops it ----
  // Every change of the open screen's draft is kept as it happens (after the page has drawn it), a save takes it away,
  // and what is too old or too much goes when the page starts.
  let running: (() => void) | null = null;
  function start() {
    if (running) return running;
    const scope = effectScope(true);
    scope.run(() => {
      prune();
      watch(() => [doc.document, doc.documentGrid, doc.documentUpright, doc.dirty], persist, { flush: "post" });
      watch(() => doc.saved, (saved) => { if (saved) { offer.value = null; persist(); } });
    });
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => running?.());

  return { tab, offer, offerText, opened, restore, discard, forget, persist, start };
});
