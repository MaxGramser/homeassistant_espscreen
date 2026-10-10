// What this browser keeps of unsaved work on the screens (app 0.4.x): the draft of each screen, kept as it changes so it
// survives a reload, a closed tab or a crash (model/kept-draft.ts). Opening a screen whose kept draft differs from its
// saved layout offers it ("Unsaved changes from 10:42", Restore or Discard); restoring it is one step of undo, and a draft
// that started from an older save goes through the conflict (stores/document.ts takeDraft). A draft goes when it is
// saved, discarded, or left behind on purpose (Discard and open); a preview screen's never is kept, since its layout
// lives in this browser already. Each tab keeps the drafts it writes and never takes away another tab's.
//
// Tabs of this browser that edit the same screen know of each other before anyone saves (a BroadcastChannel): each says
// which screen it has open, whether its draft is unsaved and when it last changed, and the tab whose change is older
// says "This screen is being edited in another tab", with Take over here (the other tab's draft becomes this one, as one
// step of undo) and Keep mine. A tab that closes says so; a tab shown again asks who is still there, so one that
// crashed stops counting too. A save in either tab reaches the other as a newer saved layout (the conflict, as before).
import { useEventListener } from "@vueuse/core";
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
  const waiting = shallowRef<KeptDraft | null>(null);
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
    } else if (!waiting.value && keptNow()?.tab === tab) forget(scr.selected);
  }

  // ---- Opening a screen (stores/session.ts open) ----
  // Its kept draft is offered when it differs from what was saved; one that says the same, or is too old, goes quietly.
  function opened() {
    waiting.value = null;
    const draft = keptNow();
    if (!draft || !keeps() || !doc.document || !doc.documentGrid) return;
    if (staleKept(draft, Date.now()) || (pages.sameValue(draft.layout, doc.document) && pages.sameGrid(draft.grid, doc.documentGrid)
      && draft.upright === doc.documentUpright)) { forget(scr.selected); return; }
    waiting.value = draft;
  }
  /** The kept draft becomes the draft, as one step of undo. */
  function restore() {
    const draft = waiting.value;
    if (!draft) return;
    waiting.value = null;
    doc.takeDraft(draft, label("restored"));
    persist();
  }
  /** The kept draft goes; what is unsaved now is kept in its place. */
  function discard() {
    waiting.value = null;
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

  // ---- Other tabs editing the same screen ----
  type Other = { screen: string | null; dirty: boolean; at: number };
  type Message = { tab: string; to?: string } & (
    | { type: "hello" } | { type: "bye" } | ({ type: "state" } & Other)
    | { type: "want"; screen: string } | { type: "draft"; screen: string; draft: Pick<KeptDraft, "layout" | "grid" | "upright" | "revision"> });
  const others = shallowRef(new Map<string, Other>());
  // An answer of Keep mine holds until that tab saves or leaves; a take-over that changed nothing until its next change.
  const dismissed = shallowRef(new Map<string, number>());
  let post: (message: Message) => void = () => {};
  const setOther = (tab: string, other: Other | null) => {
    const next = new Map(others.value);
    if (other) next.set(tab, other); else next.delete(tab);
    others.value = next;
    if (!other || !other.dirty) { const left = new Map(dismissed.value); left.delete(tab); dismissed.value = left; }
  };
  /** The other tab with unsaved changes to the open screen made after this tab's last one, if any. */
  const elsewhere = computed(() => {
    const screen = scr.selected;
    if (!screen || !keeps()) return null;
    for (const [tab, other] of others.value)
      if (other.screen === screen && other.dirty && other.at > (doc.dirty ? doc.editedAt : 0) && other.at > (dismissed.value.get(tab) ?? -1)) return { tab, ...other };
    return null;
  });
  // What this tab has open, said to the others.
  const state = (): Other => ({ screen: keeps() ? scr.selected : null, dirty: keeps() && doc.dirty, at: doc.editedAt });
  function receive(message: Message) {
    if (!message || message.tab === tab || (message.to && message.to !== tab)) return;
    if (message.type === "hello") post({ type: "state", tab, ...state() });
    else if (message.type === "bye") setOther(message.tab, null);
    else if (message.type === "state") setOther(message.tab, { screen: message.screen, dirty: message.dirty, at: message.at });
    else if (message.type === "want" && message.screen === scr.selected && doc.document && doc.documentGrid) post({ type: "draft", tab, to: message.tab, screen: message.screen,
      draft: { layout: pages.clone(doc.document), grid: { columns: doc.documentGrid.columns, rows: doc.documentGrid.rows }, upright: doc.documentUpright, revision: doc.documentRevision } });
    else if (message.type === "draft" && message.screen === scr.selected) {
      const before = doc.editedAt, theirs = others.value.get(message.tab)?.at ?? Date.now();
      doc.takeDraft(message.draft, label("taken_over"));
      // Nothing to take (the same draft): the bar goes until that tab changes something again.
      if (doc.editedAt === before) dismissed.value = new Map(dismissed.value).set(message.tab, theirs);
    }
  }
  /** The kept draft as the bar offers it: not while the tab that wrote it still has the screen open, which the bar of
   * the other tab speaks for (it is offered once that tab closes). */
  const offer = computed(() => {
    const draft = waiting.value;
    return draft && others.value.get(draft.tab)?.screen !== scr.selected ? draft : null;
  });
  /** The other tab's draft becomes this one's. */
  function takeOver() {
    const other = elsewhere.value;
    if (other) post({ type: "want", tab, to: other.tab, screen: other.screen! });
  }
  /** This tab keeps its own draft; the other tab is not mentioned again until it saves or closes. */
  function keepMine() {
    const other = elsewhere.value;
    if (other) dismissed.value = new Map(dismissed.value).set(other.tab, Infinity);
  }

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
      watch(() => doc.saved, (saved) => { if (saved) { waiting.value = null; persist(); } });
      // The other tabs, where the browser has a channel between them.
      const Channel = (globalThis as { BroadcastChannel?: typeof BroadcastChannel }).BroadcastChannel;
      if (!Channel) return;
      const channel = new Channel("esp-screens.editor");
      post = (message) => { try { channel.postMessage(message); } catch { /* a closed channel says nothing */ } };
      channel.onmessage = (event: MessageEvent<Message>) => receive(event.data);
      const greet = () => { others.value = new Map(); post({ type: "hello", tab }); post({ type: "state", tab, ...state() }); };
      greet();
      watch(() => [scr.selected, doc.dirty, doc.editedAt, keeps()], () => post({ type: "state", tab, ...state() }), { flush: "post" });
      // A tab shown again asks who is still there (one that crashed never said bye); a tab that closes says so.
      useEventListener(document, "visibilitychange", () => { if (!document.hidden) greet(); });
      useEventListener(window, "pageshow", (event: PageTransitionEvent) => { if (event.persisted) greet(); });
      useEventListener(window, "pagehide", () => post({ type: "bye", tab }));
      onScopeDispose(() => { post({ type: "bye", tab }); post = () => {}; channel.close(); others.value = new Map(); });
    });
    running = () => { running = null; scope.stop(); };
    return running;
  }
  onScopeDispose(() => running?.());

  return { tab, offer, offerText, opened, restore, discard, forget, persist, others, elsewhere, takeOver, keepMine, start };
});
