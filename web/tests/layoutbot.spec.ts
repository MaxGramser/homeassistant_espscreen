// Layoutbot (docs/LAYOUTBOT.md, stores/layoutbot.ts, components/LayoutBot.vue): shown only where Home Assistant has an
// AI Task that makes data; a question sends the draft as it is, the answer becomes the draft as one step of undo that the
// chat can take back, and while it thinks the pages take no edit.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LayoutBot from "../src/components/LayoutBot.vue";
import { send } from "../src/api";
import { clone, emptyPage, instanceId } from "../src/model/pages";
import { useDocumentStore } from "../src/stores/document";
import { useInventoryStore } from "../src/stores/inventory";
import { useLayoutbotStore } from "../src/stores/layoutbot";
import type { PageLayout } from "../src/types";
import { openScreen, screenFixture } from "./helpers/fixtures";

vi.mock("../src/api", async (original) => ({ ...(await original<typeof import("../src/api")>()), send: vi.fn() }));

const hall = () => screenFixture({ id: "hall", name: "Hall", online: true,
  layout: { title: "Hall", tiles: [{ entity: "light.a", name: "", slot: 0 }] } } as any);
const AGENTS = [{ id: "ai_task.cloud", name: "Cloud" }];

function withNewPage(layout: PageLayout): PageLayout {
  const next = clone(layout), page = emptyPage();
  page.topbar.title = { source: "text", text: "Covers" };
  page.tiles = [{ id: instanceId(), content: { kind: "entity", entityId: "cover.blind" }, placement: { row: 0, column: 0, columns: 1, rows: 1 },
    appearance: { label: "" }, interaction: {} }];
  next.pages.push(page);
  return next;
}

beforeEach(async () => {
  await openScreen(hall());
  useInventoryStore().inventory.layoutbot = AGENTS;
});
afterEach(() => { document.body.replaceChildren(); });

describe("Layoutbot", () => {
  it("is there only where Home Assistant has an AI Task that makes data", () => {
    const bot = useLayoutbotStore();
    expect(bot.available).toBe(true);
    useInventoryStore().inventory.layoutbot = [];
    expect(bot.available).toBe(false);
  });

  it("sends the draft, takes the answer as one step of undo and can take it back", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore(), before = clone(doc.document!);
    vi.mocked(send).mockImplementation(async (_path, _method, body: any) =>
      ({ reply: "Made a page for your covers.", layout: withNewPage(body.layout), changed: true, notes: [], agent: "ai_task.cloud", seconds: 3 }));
    await bot.ask("A page with the covers");
    expect(vi.mocked(send).mock.calls[0].slice(0, 2)).toEqual(["screens/hall/layoutbot", "POST"]);
    expect((vi.mocked(send).mock.calls[0][2] as any)).toMatchObject({ prompt: "A page with the covers", layout: before, agent: "ai_task.cloud" });
    expect(doc.document!.pages).toHaveLength(2);
    expect(doc.selectedPageId).toBe(doc.document!.pages[1].id);
    const answer = bot.messages.at(-1)!;
    expect(answer.text).toBe("Made a page for your covers.");
    expect(bot.undoable(answer)).toBe(true);
    bot.undo(answer);
    expect(doc.document).toEqual(before);
    expect(answer.undone).toBe(true);
    expect(bot.undoable(answer)).toBe(false);
  });

  it("leaves a draft that moved while it thought as it is", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore();
    let answer!: (value: unknown) => void;
    vi.mocked(send).mockImplementation((_path, _method, body: any) => new Promise((resolve) => {
      answer = () => resolve({ reply: "Done", layout: withNewPage(body.layout), changed: true, notes: [], agent: "a", seconds: 1 });
    }));
    const asked = bot.ask("Covers");
    expect(bot.busy).toBe(true);
    doc.applyDocument(withNewPage(doc.document!));  // another tab's save, say
    const moved = clone(doc.document!);
    answer(null);
    await asked;
    expect(doc.document).toEqual(moved);
    expect(bot.messages.at(-1)!.error).toBe(true);
  });

  it("shines over the pages and lets no key through while it thinks; Escape stops waiting", async () => {
    document.body.innerHTML = '<div id="canvas"></div>';
    const bot = useLayoutbotStore();
    vi.mocked(send).mockImplementation(() => new Promise(() => {}));
    const wrapper = mount(LayoutBot, { attachTo: document.body });
    await flushPromises();
    expect(document.querySelector(".bot-fab")).not.toBeNull();
    void bot.ask("Lights");
    await flushPromises();
    expect(document.querySelector(".bot-shine")).not.toBeNull();
    const undo = new KeyboardEvent("keydown", { key: "z", metaKey: true, cancelable: true, bubbles: true });
    document.getElementById("canvas")!.dispatchEvent(undo);
    expect(undo.defaultPrevented).toBe(true);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true }));
    await flushPromises();
    expect(bot.busy).toBe(false);
    expect(bot.messages.at(-1)!.text).toBe("Stopped. Nothing changed.");
    wrapper.unmount();
  });

  it("offers ready-made questions, with sections where the screen draws them", async () => {
    document.body.innerHTML = '<div id="canvas"></div>';
    const bot = useLayoutbotStore();
    bot.open = true;
    const wrapper = mount(LayoutBot, { attachTo: document.body });
    await flushPromises();
    const offered = [...document.querySelectorAll(".bot-suggest button")].map((button) => button.textContent);
    expect(offered).toEqual(["Put all the lights on one page", "A page with all the blinds and curtains",
      "A music page with all the speakers", "A climate page with the heating and the temperatures"]);
    wrapper.unmount();
  });
});
