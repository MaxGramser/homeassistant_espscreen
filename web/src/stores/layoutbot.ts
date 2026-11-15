// Layoutbot (docs/LAYOUTBOT.md): the editor's chat that arranges pages with the LLM the person connected to Home
// Assistant. A question goes to the add-on with the draft as it is (api/screens/<id>/layoutbot); the add-on asks the AI
// Task for a plan, makes and checks the draft that follows, and saves nothing. The answer becomes the draft at once, as
// one step of undo, so the person sees it on the real pages and keeps it or takes it back from the chat. While it
// thinks the pages wait: the editor shines and takes no edit (components/LayoutBot.vue), so the answer never lands on
// a draft that moved under it.
import { defineStore } from "pinia";
import { computed, nextTick, ref, watch } from "vue";
import { send } from "../api";
import { t } from "../i18n";
import { label } from "../model/change-label";
import { sameValue } from "../model/pages";
import type { PageLayout } from "../types";
import { useDocumentStore } from "./document";
import { useInventoryStore } from "./inventory";
import { useScreenStore } from "./screen";

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
  /** The question after every real change, asked by the editor and not the model: send it to the screens? */
  send?: "ask" | "sending" | "sent" | "declined" | "failed";
};
export type Elsewhere = { id: string; name: string; layout?: PageLayout; revision?: string; error?: string; notes?: string[];
  summary?: { pages: number; added: number; removed: number; changed: number[] } };
type Answer = { reply: string; layout: PageLayout; changed: boolean; notes: string[]; agent: string; seconds: number; elsewhere?: Elsewhere[] };

export const useLayoutbotStore = defineStore("layoutbot", () => {
  const inv = useInventoryStore();
  const scr = useScreenStore();
  const doc = useDocumentStore();
  const agents = computed(() => inv.inventory.layoutbot ?? []);
  /** The bot shows wherever there is a draft; it works where Home Assistant has an AI Task that makes data, and
   * elsewhere its chat says how to connect one. */
  const shown = computed(() => Boolean(doc.document) && Boolean(scr.selected));
  const ready = computed(() => agents.value.length > 0);
  const available = computed(() => shown.value && ready.value);
  /** Look again after the person added an AI integration in Home Assistant (the full inventory lists the AI Tasks). */
  async function recheck() { await inv.refresh(true); }
  const open = ref(false);
  const busy = ref(false);
  const started = ref(0);
  const agent = ref<string | null>(null);
  const messages = ref<BotMessage[]>([]);
  let next = 1, asking = 0;
  const agentName = computed(() => agents.value.find((a) => a.id === agent.value)?.name ?? agents.value[0]?.name ?? "");
  // Each screen has its own conversation: a plan speaks of that screen's pages.
  watch(() => scr.selected, () => { messages.value = []; stop(); });
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

  async function ask(prompt: string) {
    const text = prompt.trim();
    if (!text || busy.value || !available.value || !doc.document || !scr.selected) return;
    say({ from: "you", text });
    const sent = doc.document, screen = scr.selected, mine = ++asking;
    busy.value = true;
    started.value = Date.now();
    try {
      const answer = await send<Answer>(`screens/${encodeURIComponent(screen)}/layoutbot`, "POST",
        { prompt: text, layout: sent, ...(agent.value ? { agent: agent.value } : {}) });
      if (mine !== asking) return;
      busy.value = false;
      const notes = answer.notes ?? [];
      const elsewhere = answer.elsewhere ?? [];
      const proposed = elsewhere.filter((other) => other.layout);
      if (!answer.changed) {
        say({ from: "bot", text: answer.reply || t("editor.layoutbot.nothing"), notes, seconds: answer.seconds,
          ...(elsewhere.length ? { elsewhere } : {}), ...(proposed.length ? { send: "ask" as const } : {}) });
        return;
      }
      if (scr.selected !== screen || !doc.document || !sameValue(doc.document, sent)) {
        say({ from: "bot", text: t("editor.layoutbot.stale"), error: true });
        return;
      }
      const before = new Set(sent.pages.map((p) => JSON.stringify(p)));
      const page = answer.layout.pages.find((p) => !before.has(JSON.stringify(p)))?.id;
      const applied = doc.applyDocument(answer.layout, true, undefined, label("layoutbot"));
      const message = say({ from: "bot", text: answer.reply || t("editor.layoutbot.nothing"), notes, seconds: answer.seconds,
        ...(applied ? { step: doc.undoCount, page } : {}), ...(elsewhere.length ? { elsewhere } : {}),
        ...(applied || proposed.length ? { send: "ask" as const } : {}) });
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

  /** Yes: this screen's draft is saved and sent (as Save & send does) unless it was undone, and every other screen's
   * proposal is saved on the revision it was made from. */
  async function deliver(message: BotMessage) {
    if (message.send !== "ask") return;
    message.send = "sending";
    const failures: string[] = [];
    try {
      if (!message.undone && message.step !== undefined && doc.dirty && scr.selected) {
        await doc.save();
        if (doc.dirty) failures.push(scr.currentScreen?.name ?? "");
      }
      for (const other of message.elsewhere ?? []) {
        if (!other.layout) continue;
        try {
          await send(`screens/${encodeURIComponent(other.id)}`, "PUT", { format: "pages-v2", revision: other.revision, layout: other.layout });
        } catch (error: any) { failures.push(`${other.name}: ${error?.message ?? ""}`); }
      }
      await inv.refresh(false);
    } finally {
      message.send = failures.length ? "failed" : "sent";
      if (failures.length) say({ from: "bot", text: t("editor.layoutbot.send.failed", { which: failures.join(", ") }), error: true });
    }
  }
  function decline(message: BotMessage) { if (message.send === "ask") message.send = "declined"; }
  /** Every screen a message would go to, by name: this one when its draft changed, then the others. */
  function targets(message: BotMessage) {
    const here = message.step !== undefined && !message.undone ? [scr.currentScreen?.name ?? ""] : [];
    return [...here, ...(message.elsewhere ?? []).filter((other) => other.layout).map((other) => other.name)].filter(Boolean);
  }

  return { agents, shown, ready, available, recheck, open, busy, started, agent, agentName, messages, ask, stop, undo, undoable, show, deliver, decline, targets };
});
