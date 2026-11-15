// Layoutbot (docs/LAYOUTBOT.md, stores/layoutbot.ts, components/LayoutBot.vue): shown only where Home Assistant has an
// AI Task that makes data; a question sends the draft as it is, the answer becomes the draft as one step of undo that the
// chat can take back, and while it thinks the pages take no edit.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import LayoutBot from "../src/components/LayoutBot.vue";
import { clone, emptyPage, instanceId } from "../src/model/pages";
import { useDocumentStore } from "../src/stores/document";
import { useInventoryStore } from "../src/stores/inventory";
import { useLayoutbotStore } from "../src/stores/layoutbot";
import type { PageLayout } from "../src/types";
import { fakeApi, type FakeApi } from "./helpers/fake-api";
import { openScreen, screenFixture } from "./helpers/fixtures";

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

let api: FakeApi;
const answering = (body: Record<string, unknown>) => (request: any) => ({ reply: "Done", changed: true, notes: [], agent: "a", seconds: 1,
  layout: withNewPage(request.body.layout), ...body });
beforeEach(async () => {
  api = fakeApi({ "inventory": { screens: [], entities: [] }, "PUT screens/:id": (request: any) =>
    ({ saved: true, document: { format: "pages-v2", revision: "r2", layout: request.body.layout, sourceGrid: { columns: 2, rows: 3 } } }) });
  await openScreen(hall());
  useInventoryStore().inventory.layoutbot = AGENTS;
});
afterEach(() => { document.body.replaceChildren(); });

describe("Layoutbot", () => {
  it("works where Home Assistant has an AI Task that makes data, and elsewhere says how to connect one", async () => {
    const bot = useLayoutbotStore();
    expect(bot.available).toBe(true);
    useInventoryStore().inventory.layoutbot = [];
    expect([bot.shown, bot.available]).toEqual([true, false]);
    document.body.innerHTML = '<div id="canvas"></div>';
    bot.open = true;
    const wrapper = mount(LayoutBot, { attachTo: document.body });
    await flushPromises();
    expect(document.querySelector(".bot-fab")!.classList.contains("asleep")).toBe(true);
    expect(document.querySelector(".bot-compose")).toBeNull();
    expect([...document.querySelectorAll<HTMLAnchorElement>(".provider")].map((link) => link.getAttribute("href"))).toEqual([
      "/_my_redirect/config_flow_start?domain=openai_conversation", "/_my_redirect/config_flow_start?domain=anthropic",
      "/_my_redirect/config_flow_start?domain=google_generative_ai_conversation", "/_my_redirect/config_flow_start?domain=ollama"]);
    await bot.ask("Lights");
    expect(api.count("POST screens/:id/layoutbot")).toBe(0);
    wrapper.unmount();
  });

  it("sends the draft, takes the answer as one step of undo and can take it back", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore(), before = clone(doc.document!);
    api.on("POST screens/:id/layoutbot", answering({ reply: "Made a page for your covers." }));
    await bot.ask("A page with the covers");
    const [asked] = api.asked("POST screens/:id/layoutbot");
    expect(asked.params.id).toBe("hall");
    expect(asked.body).toMatchObject({ prompt: "A page with the covers", layout: before, agent: "ai_task.cloud" });
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

  it("asks to send after a real change, and yes saves this screen and the others it changed", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore();
    const wall = withNewPage(doc.document!);
    api.on("POST screens/:id/layoutbot", answering({
      elsewhere: [{ id: "wall", name: "Wallbox", layout: wall, revision: "r7", summary: { pages: 1, added: 1, removed: 0, changed: [] } }] }));
    await bot.ask("The alarm on every screen");
    const message = bot.messages.at(-1)!;
    expect(message.send).toBe("ask");
    expect(bot.targets(message)).toEqual(["Hall", "Wallbox"]);
    expect(api.count("PUT screens/:id")).toBe(0);  // nothing saved before yes
    await bot.deliver(message);
    const puts = api.asked("PUT screens/:id");
    expect(puts.map((put) => put.params.id)).toEqual(["hall", "wall"]);
    expect(puts[1].body).toEqual({ format: "pages-v2", revision: "r7", layout: wall });
    expect(message.send).toBe("sent");
    expect(doc.dirty).toBe(false);
  });

  it("asks nothing when nothing changed, and an undone change only sends the other screens", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore();
    api.on("POST screens/:id/layoutbot", answering({ reply: "I only arrange pages.", changed: false, layout: doc.document }));
    await bot.ask("Turn the lights on");
    expect(bot.messages.at(-1)!.send).toBeUndefined();
    api.on("POST screens/:id/layoutbot", (request: any) => answering({ elsewhere: [{ id: "wall", name: "Wallbox", layout: withNewPage(request.body.layout), revision: "r1" }] })(request));
    await bot.ask("Covers everywhere");
    const message = bot.messages.at(-1)!;
    bot.undo(message);
    expect(bot.targets(message)).toEqual(["Wallbox"]);
    await bot.deliver(message);
    expect(api.asked("PUT screens/:id").map((put) => put.params.id)).toEqual(["wall"]);
  });

  it("leaves a draft that moved while it thought as it is", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore();
    api.on("POST screens/:id/layoutbot", answering({}));
    const held = api.defer("POST screens/:id/layoutbot");
    const asked = bot.ask("Covers");
    expect(bot.busy).toBe(true);
    doc.applyDocument(withNewPage(doc.document!));  // another tab's save, say
    const moved = clone(doc.document!);
    held.resolve();
    await asked;
    expect(doc.document).toEqual(moved);
    expect(bot.messages.at(-1)!.error).toBe(true);
  });

  it("shines over the pages and lets no key through while it thinks; Escape stops waiting", async () => {
    document.body.innerHTML = '<div id="canvas"></div>';
    const bot = useLayoutbotStore();
    api.on("POST screens/:id/layoutbot", answering({}));
    api.defer("POST screens/:id/layoutbot");
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
