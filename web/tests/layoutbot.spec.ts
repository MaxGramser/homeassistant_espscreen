// Layoutbot (docs/LAYOUTBOT.md, stores/layoutbot.ts, components/LayoutBot.vue): shown only where Home Assistant has an
// AI Task that makes data; a question sends the draft as it is, the add-on answers with a checked plan, the editor places
// it (model/layoutbot.ts, its own tests in layoutbot-plan.spec.ts) as one step of undo that the chat can take back, and
// while it thinks the pages take no edit.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import LayoutBot from "../src/components/LayoutBot.vue";
import { clone, emptyPage, instanceId } from "../src/model/pages";
import { useDocumentStore } from "../src/stores/document";
import { useInventoryStore } from "../src/stores/inventory";
import { useLayoutbotStore } from "../src/stores/layoutbot";
import { failure } from "./helpers/fake-api";
import type { PageLayout } from "../src/types";
import { fakeApi, type FakeApi } from "./helpers/fake-api";
import { openScreen, screenFixture } from "./helpers/fixtures";
import { useScreenStore } from "../src/stores/screen";
import { router } from "../src/router";

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
// The add-on's answer: a checked plan, here a cover on the screen's first page.
const PLAN = { pages: [{ page: 1, title: "", icon: null, sections: [], tiles: ["cover.blind"] }], remove: [] };
const answering = (body: Record<string, unknown> = {}) => () => ({ version: 2, reply: "Done", plan: PLAN, notes: [], agent: "a", seconds: 1, ...body });
beforeEach(async () => {
  // The add-on's inventory as the store holds it: a refresh after a save reads the same screens back.
  api = fakeApi({ "inventory": () => ({ screens: clone(useInventoryStore().inventory.screens), entities: useInventoryStore().inventory.entities }), "capabilities": { capabilities: {} }, "home-facts": { entities: [], areas: [], floors: [], devices: {} }, "PUT screens/:id": (request: any) =>
    ({ saved: true, document: { format: "pages-v2", revision: "r2", layout: request.body.layout, sourceGrid: { columns: 2, rows: 3 } } }) });
  await openScreen(hall());
  useInventoryStore().inventory.layoutbot = AGENTS;
  // The home's entities as the inventory lists them: a tile is placed only of an entity the home has.
  useInventoryStore().inventory.entities = ["light.a", "light.x", "cover.blind"].map((id) => ({ id, name: id.split(".")[1], state: "off", area: "" })) as any;
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

  it("sends the draft, places the plan as one step of undo and can take it back", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore(), before = clone(doc.document!);
    api.on("POST screens/:id/layoutbot", answering({ reply: "Added the blind." }));
    await bot.ask("Add the blind");
    const [asked] = api.asked("POST screens/:id/layoutbot");
    expect(asked.params.id).toBe("hall");
    expect(asked.body).toEqual({ version: 2, prompt: "Add the blind", layout: before, agent: "ai_task.cloud" });
    expect(doc.document!.pages[0].tiles.map((tile) => (tile.content as any).entityId)).toEqual(["light.a", "cover.blind"]);
    const answer = bot.messages.at(-1)!;
    expect(answer.text).toBe("Added the blind.");
    expect(bot.undoable(answer)).toBe(true);
    bot.undo(answer);
    expect(doc.document).toEqual(before);
    expect(answer.undone).toBe(true);
    expect(bot.undoable(answer)).toBe(false);
  });

  it("restructures the page shown by its own key, the person's words along, and places the tiles anew", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore(), before = clone(doc.document!);
    const grouped = { pages: [{ page: "new", title: "", icon: null, sections: [], tiles: ["light.a"] }], remove: [], restructure: { scope: "page", page: 1 } };
    api.on("POST screens/:id/layoutbot", answering({ reply: "Grouped.", plan: grouped }));
    const chat = mount(LayoutBot, { attachTo: document.body });
    bot.open = true;
    await flushPromises();
    expect(bot.canRestructure("page")).toBe(true);
    await bot.restructure("page", "lights first");
    const [asked] = api.asked("POST screens/:id/layoutbot");
    expect(asked.body).toEqual({ version: 2, prompt: "lights first", layout: before, agent: "ai_task.cloud", restructure: { scope: "page", page: 1 } });
    expect(bot.messages[0].text).toBe("Restructure this page: lights first");
    // The page keeps its id and its tiles; nothing else asked for, so nothing else changed.
    expect(doc.document!.pages[0].id).toBe(before.pages[0].id);
    expect(doc.document!.pages[0].tiles.map((tile) => (tile.content as any).entityId)).toEqual(["light.a"]);
    // Without words of the person's, the key alone asks.
    await bot.restructure("screen");
    expect(api.asked("POST screens/:id/layoutbot")[1].body).toMatchObject({ prompt: "", restructure: { scope: "screen" } });
    chat.unmount();
  });

  it("tells the person to update the app when the add-on answers in the old way", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore(), before = clone(doc.document!);
    api.on("POST screens/:id/layoutbot", () => ({ reply: "Done", layout: withNewPage(before), changed: true, notes: [] }));
    await bot.ask("Covers");
    expect(doc.document).toEqual(before);
    expect(bot.messages.at(-1)).toMatchObject({ error: true, text: "Update the Tessera app: this editor places Layoutbot's plans itself." });
  });

  it("asks to send after a real change and nothing else, and yes saves and sends this screen", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore();
    api.on("POST screens/:id/layoutbot", answering({ reply: "I only arrange pages.", plan: { pages: [], remove: [] } }));
    await bot.ask("Turn the lights on");
    expect(bot.messages.at(-1)!.send).toBeUndefined();
    api.on("POST screens/:id/layoutbot", answering());
    await bot.ask("Add the blind");
    const message = bot.messages.at(-1)!;
    expect(message.send).toBe("ask");
    expect(bot.targets(message)).toEqual(["Hall"]);
    expect(api.count("PUT screens/:id")).toBe(0);  // nothing saved before yes
    await bot.deliver(message);
    expect(api.asked("PUT screens/:id").map((put) => put.params.id)).toEqual(["hall"]);
    expect(message.send).toBe("sent");
    expect(doc.dirty).toBe(false);
  });

  it("says that the person's own unsaved changes go along on yes", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore();
    api.on("POST screens/:id/layoutbot", answering());
    await bot.ask("Add the blind");
    expect(bot.messages.at(-1)!.own).toBeUndefined();
    bot.undo(bot.messages.at(-1)!);
    doc.applyDocument(withNewPage(doc.document!));  // an edit of the person's own, not saved
    await bot.ask("Add the blind");
    expect(bot.messages.at(-1)!.own).toBe(true);
  });

  it("asks for other screens only when the person chose all screens", async () => {
    const bot = useLayoutbotStore();
    api.on("POST screens/:id/layoutbot", answering({ plan: { pages: [], remove: [] } }));
    await bot.ask("Covers");
    bot.allScreens = true;
    await bot.ask("Covers everywhere");
    expect(api.asked("POST screens/:id/layoutbot").map((call) => call.body.all_screens)).toEqual([undefined, true]);
  });

  it("shows another screen's change before anything is saved, sends each on yes and comes back", async () => {
    const inv = useInventoryStore(), bot = useLayoutbotStore(), scr = useScreenStore();
    const other = (id: string, name: string) => screenFixture({ id, name, online: true, layout: { title: name, tiles: [{ entity: "light.x", name: "", slot: 0 }] } } as any);
    inv.inventory.screens.push(other("wall", "Wallbox"), other("desk", "Desk"));
    bot.allScreens = true;
    api.on("POST screens/:id/layoutbot", answering({ elsewhere: [{ id: "wall", name: "Wallbox", plan: PLAN, notes: [] }, { id: "desk", name: "Desk", plan: PLAN, notes: [] }] }));
    api.on("PUT screens/wall", failure(409, "Changed in another tab"));
    await bot.ask("The blind on every screen");
    const message = bot.messages.at(-1)!;
    expect(message.elsewhere!.map((o) => [o.name, o.summary])).toEqual([
      ["Wallbox", { pages: 0, added: 1, removed: 0, changed: [1] }], ["Desk", { pages: 0, added: 1, removed: 0, changed: [1] }]]);
    expect(bot.targets(message)).toEqual(["Hall", "Wallbox", "Desk"]);
    expect(api.count("PUT screens/:id")).toBe(0);  // nothing saved before yes
    const entries = window.history.length;
    await bot.deliver(message);
    // Each through the editor's own Save & send, one after the other; the one that failed keeps nothing, the others go.
    expect(api.asked("PUT screens/:id").map((put) => put.path)).toEqual(["screens/hall", "screens/wall", "screens/desk"]);
    expect(api.asked("PUT screens/:id")[2].body.layout.pages[0].tiles.map((tile: any) => tile.content.entityId)).toEqual(["light.x", "cover.blind"]);
    expect(message.elsewhere!.map((o) => o.sent)).toEqual(["failed", "sent"]);
    expect(message.send).toBe("failed");
    expect(bot.messages.at(-1)!.text).toContain("Wallbox");
    expect(scr.selected).toBe("hall");
    expect(useDocumentStore().dirty).toBe(false);
    // Wallbox and Desk were passed through in place of the browser's entry: Back goes where the person was before.
    expect(window.history.length).toBe(entries);
    expect(router.currentRoute.value.path).toBe("/screens/hall");
  });

  it("leaves a draft that moved while it thought as it is", async () => {
    const doc = useDocumentStore(), bot = useLayoutbotStore();
    api.on("POST screens/:id/layoutbot", answering());
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
    api.on("POST screens/:id/layoutbot", answering());
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
