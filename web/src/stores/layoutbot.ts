// Layoutbot (docs/LAYOUTBOT.md): the editor's chat that arranges pages with the AI the person connected to Home
// Assistant. A question goes to the add-on with the draft as it is (api/screens/<id>/layoutbot); the add-on asks the AI
// Task and answers with a checked plan, which the editor places with its own edit functions (editor/layoutbot.ts,
// model/layoutbot.ts) and takes as one step of undo, so the person sees it on the real pages and keeps it or takes it
// back from the chat. While it thinks the pages wait: the editor shines and takes no edit (components/LayoutBot.vue), so
// the plan never lands on a draft that moved under it.
import { defineStore } from "pinia";
import { computed, nextTick, ref, watch } from "vue";
import { send } from "../api";
import { gridOf, placePlan } from "../editor/layoutbot";
import { t } from "../i18n";
import { label } from "../model/change-label";
import { summaryOf, type Plan, type PlanNote, type Restructure, type Summary } from "../model/layoutbot";
import { sameValue } from "../model/pages";
import type { PageLayout } from "../types";
import { useDocumentStore } from "./document";
import { useInventoryStore } from "./inventory";
import { useScreenStore } from "./screen";
import { useSessionStore } from "./session";
import { useUiStore } from "./ui";
import { usePreference } from "../composables/usePreference";

/** The answer the editor understands (the add-on's LAYOUTBOT_PLAN): a checked plan to place. */
export const PLAN_VERSION = 2;

export type BotMessage = {
  id: number;
  from: "you" | "bot";
  text: string;
  notes?: string[];
  /** The step of undo this answer made, while it is the last one; gone once anything else is done or it is undone. */
  step?: number;
  undone?: boolean;
  /** The first page the answer made or changed, to show it. */
  page?: string;
  error?: boolean;
  seconds?: number;
  /** Other screens this answer changes: proposals, saved only on yes. */
  elsewhere?: Elsewhere[];
  /** The draft held the person's own unsaved changes before this answer: yes sends them too, and the question says so. */
  own?: boolean;
  /** The question after every real change, asked by the editor and not the model: send it to the screens? */
  send?: "ask" | "sending" | "sent" | "declined" | "failed";
};
/** Another screen's proposal: its plan, placed on its saved document as it would be if it were open (layout, revision),
 * what that changes (summary), and how sending it went (`sent`). Nothing of it is saved before the person says yes. */
export type Elsewhere = { id: string; name: string; plan: Plan; layout?: PageLayout; revision?: string; error?: string; notes?: string[];
  summary?: Summary; sent?: "waiting" | "sending" | "sent" | "failed"; why?: string };
type Answer = { version: number; reply: string; plan: Plan; notes: string[]; agent: string; seconds: number;
  elsewhere?: { id: string; name: string; plan: Plan; notes: string[] }[] };

/** A note of the editor's own placing in the editor's words. */
export const noteText = (note: PlanNote) => t(`editor.layoutbot.notes.${note.key}`, note.named ?? {}, Number(note.named?.count ?? 1));

export const useLayoutbotStore = defineStore("layoutbot", () => {
  const inv = useInventoryStore();
  const scr = useScreenStore();
  const doc = useDocumentStore();
  const ui = useUiStore();
  const agents = computed(() => inv.inventory.layoutbot ?? []);
  /** The bot shows wherever there is a draft; it works where Home Assistant has an AI Task that makes data, and
   * elsewhere its chat says how to connect one. */
  const shown = computed(() => Boolean(doc.document) && Boolean(scr.selected));
  const ready = computed(() => agents.value.length > 0);
  const available = computed(() => shown.value && ready.value);
  /** Look again after the person added an AI integration in Home Assistant (the full inventory lists the AI Tasks). */
  async function recheck() { await inv.refresh(true); }
  // Whether the chat is open is the address's (ui.chatOpen, `?chat=layoutbot`), never this store's.
  const open = computed({ get: () => ui.chatOpen, set: (value: boolean) => { void ui.openChat(value); } });
  const busy = ref(false);
  const started = ref(0);
  // The AI Task the person picked in the chat's head, kept in this browser: an AI Task of its own with a larger model,
  // made for Layoutbot in Home Assistant, stays chosen (docs/LAYOUTBOT.md, "Which model").
  const picked = usePreference<string>("esp-screens.layoutbot-agent", "");
  const agent = computed<string | null>({ get: () => picked.value || null, set: (id) => { picked.value = id ?? ""; } });
  const messages = ref<BotMessage[]>([]);
  let next = 1, asking = 0;
  const agentName = computed(() => agents.value.find((a) => a.id === agent.value)?.name ?? agents.value[0]?.name ?? "");
  /** The person's choice in the chat: this screen only, or all screens. Only then does the add-on describe the other
   * screens to the AI and answer with their plans (layoutbot.answered). */
  const allScreens = ref(false);
  /** Sending to several screens opens each in turn: the conversation stays while it does. */
  const delivering = ref<string | null>(null);
  // Each screen has its own conversation: a plan speaks of that screen's pages.
  watch(() => scr.selected, () => { if (delivering.value) return; messages.value = []; stop(); });
  watch(agents, (list) => { if (!list.some((a) => a.id === agent.value)) agent.value = list[0]?.id ?? null; }, { immediate: true });

  function say(message: Omit<BotMessage, "id">) {
    messages.value.push({ id: next++, ...message });
    return messages.value[messages.value.length - 1];
  }

  /** Stop waiting: the answer, when it comes, is left unused. */
  function stop() {
    if (!busy.value) return;
    asking++;
    busy.value = false;
    say({ from: "bot", text: t("editor.layoutbot.stopped") });
  }

  /** The page shown, by its number (from 1), for "Restructure this page". */
  const shownPage = () => Math.max(0, doc.document?.pages.findIndex((page) => page.id === doc.selectedPageId) ?? 0) + 1;
  /** Whether there is anything of the person's to restructure: tiles of devices on the page shown, or on the screen. */
  function canRestructure(scope: "page" | "screen") {
    const all = doc.document?.pages ?? [], list = scope === "page" ? all.slice(shownPage() - 1, shownPage()) : all;
    return list.some((page) => page.tiles.some((tile) => tile.content.kind === "entity"));
  }
  /** Restructure this page or the whole screen (docs/LAYOUTBOT.md, "Restructuring"): the AI groups the person's own tiles,
   * the editor places them again; `words` of the person's steer the grouping. */
  function restructure(scope: "page" | "screen", words = "") {
    const said = [t(`editor.layoutbot.restructure.${scope}`), words.trim()].filter(Boolean).join(": ");
    return ask(words, scope === "page" ? { scope, page: shownPage() } : { scope }, said);
  }

  async function ask(prompt: string, restructuring?: Restructure, said?: string) {
    const text = prompt.trim();
    if ((!text && !restructuring) || busy.value || !available.value || !doc.document || !doc.documentGrid || !scr.currentScreen) return;
    say({ from: "you", text: said ?? text });
    const sent = doc.document, screen = scr.currentScreen, grid = doc.screenGridOf(doc.documentGrid), mine = ++asking;
    busy.value = true;
    started.value = Date.now();
    try {
      const answer = await send<Answer>(`screens/${encodeURIComponent(screen.id)}/layoutbot`, "POST",
        { version: PLAN_VERSION, prompt: text, layout: sent, ...(agent.value ? { agent: agent.value } : {}),
          ...(restructuring ? { restructure: restructuring } : allScreens.value ? { all_screens: true } : {}) });
      if (mine !== asking) return;
      // An add-on from before plans answers with a whole document this editor no longer applies.
      if (answer.version !== PLAN_VERSION || !answer.plan) throw new Error(t("editor.layoutbot.update_app"));
      const placed = await placePlan(screen, sent, grid, answer.plan, scr.coversByDefault);
      if (mine !== asking) return;
      const elsewhere = await proposals(answer.elsewhere ?? []);
      if (mine !== asking) return;
      busy.value = false;
      const notes = [...(answer.notes ?? []), ...placed.notes.map(noteText)];
      const reply = answer.reply || t("editor.layoutbot.nothing");
      const others = elsewhere.length ? { elsewhere } : {}, proposed = elsewhere.some((other) => other.layout);
      if (sameValue(placed.layout, sent)) {
        say({ from: "bot", text: reply, notes, seconds: answer.seconds, ...others, ...(proposed ? { send: "ask" as const } : {}) });
        return;
      }
      if (scr.selected !== screen.id || !doc.document || !sameValue(doc.document, sent)) {
        say({ from: "bot", text: t("editor.layoutbot.stale"), error: true });
        return;
      }
      const before = new Set(sent.pages.map((p) => JSON.stringify(p)));
      const page = placed.layout.pages.find((p) => !before.has(JSON.stringify(p)))?.id;
      // Edits the person made by hand before asking go out with the bot's on yes: the question says so (`own`).
      const own = doc.dirty;
      const applied = doc.applyDocument(placed.layout, true, undefined, label("layoutbot"));
      const message = say({ from: "bot", text: reply, notes, seconds: answer.seconds, ...others,
        ...(applied ? { step: doc.undoCount, page, ...(own ? { own: true } : {}) } : {}), ...(applied || proposed ? { send: "ask" as const } : {}) });
      // The page it made or changed comes into view once it is drawn.
      if (applied && page) { doc.selectedPageId = page; void nextTick(() => show(message)); }
    } catch (error: any) {
      if (mine !== asking) return;
      busy.value = false;
      say({ from: "bot", text: error?.message || t("editor.api.failed"), error: true });
    }
  }

  /** Whether a message's change is still the last step of undo, so the chat can take it back. */
  const undoable = (message: BotMessage) => message.step !== undefined && !message.undone && doc.undoCount === message.step;
  function undo(message: BotMessage) {
    if (!undoable(message)) return;
    doc.undo();
    message.undone = true;
  }
  function show(message: BotMessage) {
    if (!message.page) return;
    doc.selectedPageId = message.page;
    document.querySelector(`[data-page-id="${message.page}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }

  /** Each other screen's plan placed on its saved document, as it would be placed if it were open: what it changes, for
   * the chat to show before anything is saved. A screen whose plan changes nothing keeps only its notes. */
  async function proposals(list: NonNullable<Answer["elsewhere"]>): Promise<Elsewhere[]> {
    const out: Elsewhere[] = [];
    for (const other of list) {
      const screen = inv.inventory.screens.find((item) => item.id === other.id), record = screen?.page_document;
      if (!screen || record?.format !== "pages-v2") { out.push({ ...other, error: t("editor.layoutbot.send.not_opened") }); continue; }
      try {
        const placed = await placePlan(screen, record.layout, gridOf(screen, record.sourceGrid), other.plan);
        const notes = [...other.notes, ...placed.notes.map(noteText)];
        out.push(sameValue(placed.layout, record.layout) ? { ...other, notes }
          : { ...other, notes, layout: placed.layout, revision: record.revision, summary: summaryOf(record.layout, placed.layout) });
      } catch (error: any) { out.push({ ...other, error: error?.message ?? t("editor.api.failed") }); }
    }
    return out;
  }

  /** Opens another screen to look at its proposal: the plan placed in its draft as one step of undo, nothing saved. */
  async function preview(other: Elsewhere) {
    if (!other.layout) return;
    await useSessionStore().select(other.id);
    if (scr.selected !== other.id || !doc.document) return;
    const placed = doc.documentRevision === other.revision ? other.layout : (await placePlan(scr.currentScreen!, doc.document, doc.screenGridOf(doc.documentGrid!), other.plan)).layout;
    doc.applyDocument(placed, true, undefined, label("layoutbot"));
  }

  /** Yes: this screen's draft is saved and sent (as Save & send does) unless it was undone; then each other screen in
   * turn is opened, its plan placed in its draft (again, where its saved document changed since) and saved through the
   * same Save & send, with its own validation and undo. A screen that fails keeps nothing of it (its step is undone) and
   * the others still go; the chat says which failed and why, and the screen the person was on opens again. The screens it
   * passes through take the browser's entry in place (select's `replace`), so Back afterwards goes where the person was
   * before, never to one of them. */
  async function deliver(message: BotMessage) {
    if (message.send !== "ask") return;
    message.send = "sending";
    const failures: string[] = [], session = useSessionStore(), home = scr.selected;
    const others = (message.elsewhere ?? []).filter((other) => other.layout);
    others.forEach((other) => { other.sent = "waiting"; });
    try {
      if (!message.undone && message.step !== undefined && doc.dirty && scr.selected) {
        await doc.save();
        if (doc.dirty) failures.push(scr.currentScreen?.name ?? "");
      }
      for (const other of others) {
        other.sent = "sending";
        delivering.value = other.name;
        try {
          if (doc.dirty) throw new Error(t("editor.layoutbot.send.unsaved"));
          await session.select(other.id, { replace: true });
          if (scr.selected !== other.id || !doc.document || !doc.documentGrid) throw new Error(t("editor.layoutbot.send.not_opened"));
          const layout = doc.documentRevision === other.revision ? other.layout!
            : (await placePlan(scr.currentScreen!, doc.document, doc.screenGridOf(doc.documentGrid), other.plan)).layout;
          if (!doc.applyDocument(layout, true, undefined, label("layoutbot"))) { other.sent = "sent"; continue; }
          await doc.save();
          if (doc.dirty) { doc.undo(); throw new Error(t("editor.layoutbot.send.not_saved")); }
          other.sent = "sent";
        } catch (error: any) {
          other.sent = "failed";
          other.why = error?.message ?? "";
          failures.push(`${other.name}: ${other.why}`);
        }
      }
    } finally {
      if (home && scr.selected !== home && !doc.dirty) await session.select(home, { replace: true });
      delivering.value = null;
      await inv.refresh(false);
      message.send = failures.length ? "failed" : "sent";
      if (failures.length) say({ from: "bot", text: t("editor.layoutbot.send.failed", { which: failures.join("; ") }), error: true });
    }
  }
  function decline(message: BotMessage) { if (message.send === "ask") message.send = "declined"; }
  /** Every screen a message would go to, by name: this one when its draft changed, then the others. */
  function targets(message: BotMessage) {
    const here = message.step !== undefined && !message.undone ? [scr.currentScreen?.name ?? ""] : [];
    return [...here, ...(message.elsewhere ?? []).filter((other) => other.layout).map((other) => other.name)].filter(Boolean);
  }

  return { agents, shown, ready, available, recheck, open, busy, started, agent, agentName, messages, allScreens, delivering,
    ask, restructure, canRestructure, stop, undo, undoable, show, preview, deliver, decline, targets };
});
