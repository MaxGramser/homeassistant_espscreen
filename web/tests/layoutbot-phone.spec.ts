// Layoutbot on a phone (docs/LAYOUTBOT.md, "On a phone"): its key stands in the phone's dock beside Add tile, its chat is
// a sheet from the bottom (components/ui/UiSheet.vue), which rests low while it thinks and while its question waits so
// the page above shows the change, rides on the on-screen keyboard, and is open while the address says so
// (`?chat=layoutbot`): Back closes it, and it stays open while its Yes goes through the other screens and home again.
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import ScreenView from "../src/components/ScreenView.vue";
import LayoutBot from "../src/components/LayoutBot.vue";
import { clone } from "../src/model/pages";
import { router } from "../src/router";
import { useDocumentStore } from "../src/stores/document";
import { useInventoryStore } from "../src/stores/inventory";
import { useLayoutbotStore } from "../src/stores/layoutbot";
import { useScreenStore } from "../src/stores/screen";
import { useUiStore } from "../src/stores/ui";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi, type FakeApi } from "./helpers/fake-api";
import { openScreen, screenFixture } from "./helpers/fixtures";

const screen = (id: string, name: string) => screenFixture({ id, name, online: true,
  layout: { title: name, tiles: [{ entity: "light.a", name: "", slot: 0 }] } } as any);
// The add-on's answer: a checked plan, a new page with two lights.
const PLAN = { pages: [{ page: "new", title: "Lights", icon: null, sections: [], tiles: ["light.x", "light.y"] }], remove: [] };
const answer = (body: Record<string, unknown> = {}) => () => ({ version: 2, reply: "Two lights on a new page.", plan: PLAN, notes: [], agent: "a", seconds: 1, ...body });

let api: FakeApi;
let mounted: VueWrapper[] = [];
const sheet = () => document.querySelector<HTMLElement>(".ui-sheet");
const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>(".ui-sheet button")].find((b) => b.textContent?.includes(text));

beforeEach(async () => {
  // jsdom lays nothing out: the page the bot made is brought into view on a real phone.
  Element.prototype.scrollIntoView = () => {};
  api = fakeApi({ "inventory": () => ({ screens: clone(useInventoryStore().inventory.screens), entities: useInventoryStore().inventory.entities }),
    "capabilities": { capabilities: {} }, "home-facts": { entities: [], areas: [], floors: [], devices: {} },
    "PUT screens/:id": (request: any) => ({ saved: true, document: { format: "pages-v2", revision: `r-${request.params.id}`, layout: request.body.layout, sourceGrid: { columns: 2, rows: 3 } } }) });
  useUiStore().narrowPhone = true;
  await openScreen(screen("hall", "Hall"));
  await flushPromises();
  useInventoryStore().inventory.layoutbot = [{ id: "ai_task.cloud", name: "Cloud" }];
  useInventoryStore().inventory.entities = ["light.a", "light.x", "light.y"].map((id) => ({ id, name: id.split(".")[1], state: "off", area: "" })) as any;
  document.body.innerHTML = '<div id="canvas"></div>';
});
afterEach(async () => {
  mounted.forEach((wrapper) => wrapper.unmount());
  mounted = [];
  // Leaving a draft the bot changed asks first: yes, for the next test's sake.
  answerDialogs(() => true);
  await router.replace("/");
  document.body.replaceChildren();
});
async function phone() {
  mounted.push(mount(ScreenView, { attachTo: document.body }), mount(LayoutBot, { attachTo: document.body }));
  await flushPromises();
}

describe("Layoutbot on a phone", () => {
  it("is offered in the phone's dock, before Add tile, and floats nowhere", async () => {
    await phone();
    const dock = document.querySelector(".phone-dock")!;
    expect([...dock.children].map((child) => child.id || child.className.split(" ")[0])).toEqual(["bot-fab", "phone-add"]);
    expect(document.querySelectorAll(".bot-fab")).toHaveLength(1);
    expect(dock.querySelector(".bot-fab")!.classList.contains("docked")).toBe(true);
    expect(sheet()).toBeNull();
  });

  it("opens as a sheet the address names, and Back closes it", async () => {
    await phone();
    document.querySelector<HTMLButtonElement>(".phone-dock .bot-fab")!.click();
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/screens/hall?chat=layoutbot");
    expect(sheet()).not.toBeNull();
    expect(sheet()!.getAttribute("role")).toBe("dialog");
    // The field takes no focus by itself on a phone (no keyboard over the conversation) and is no smaller than 16 px.
    expect(document.activeElement?.tagName).not.toBe("TEXTAREA");
    expect(document.querySelector(".bot-chat-body")!.classList.contains("phone")).toBe(true);
    router.back();
    await new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/screens/hall");
    expect(sheet()).toBeNull();
  });

  it("sends a question, rests low while it thinks and while its question waits, and the grab raises it", async () => {
    await phone();
    const bot = useLayoutbotStore(), doc = useDocumentStore();
    bot.open = true;
    await flushPromises();
    expect(sheet()!.classList.contains("resting")).toBe(false);
    api.on("POST screens/:id/layoutbot", answer());
    const held = api.defer("POST screens/:id/layoutbot");
    button("Put all the lights")!.click();
    await flushPromises();
    expect(bot.busy).toBe(true);
    expect(sheet()!.classList.contains("resting")).toBe(true);
    expect(document.querySelector(".bot-shine")).not.toBeNull();
    held.resolve();
    await flushPromises();
    // The proposal: on the draft as one step of undo, its page the one shown above the sheet, Show and Yes in the sheet.
    expect(doc.document!.pages).toHaveLength(2);
    expect(doc.selectedPageId).toBe(doc.document!.pages[1].id);
    expect(sheet()!.classList.contains("resting")).toBe(true);
    expect(button("Show")).toBeDefined();
    expect(button("Yes, send")).toBeDefined();
    document.querySelector<HTMLButtonElement>(".ui-sheet-grab")!.click();
    await flushPromises();
    expect(sheet()!.classList.contains("resting")).toBe(false);
    document.querySelector<HTMLButtonElement>(".ui-sheet-grab")!.click();
    await flushPromises();
    expect(sheet()!.classList.contains("resting")).toBe(true);
  });

  it("stands on the on-screen keyboard, so the field stays above it", async () => {
    // The browser's visual viewport, as a phone's: the keyboard takes 300 px off its bottom once it is up.
    let keyboard = 0;
    const view = Object.assign(new EventTarget(), { offsetTop: 0 });
    Object.defineProperty(view, "height", { get: () => window.innerHeight - keyboard });
    Object.defineProperty(window, "visualViewport", { configurable: true, value: view });
    await phone();
    useLayoutbotStore().open = true;
    await flushPromises();
    expect(sheet()!.classList.contains("typing")).toBe(false);
    keyboard = 300;
    view.dispatchEvent(new Event("resize"));
    await flushPromises();
    expect(sheet()!.classList.contains("typing")).toBe(true);
    expect(sheet()!.style.bottom).toBe("300px");
    expect(sheet()!.style.maxHeight).toBe(`${window.innerHeight - 300 - 12}px`);
    Reflect.deleteProperty(window, "visualViewport");
  });

  it("Yes delivers to every screen, keeps the chat open on its way, and comes back home", async () => {
    const inv = useInventoryStore(), bot = useLayoutbotStore(), scr = useScreenStore();
    inv.inventory.screens.push(screen("wall", "Wallbox"));
    await phone();
    bot.open = true;
    bot.allScreens = true;
    await flushPromises();
    api.on("POST screens/:id/layoutbot", answer({ elsewhere: [{ id: "wall", name: "Wallbox", plan: PLAN, notes: [] }] }));
    await bot.ask("Lights everywhere");
    await flushPromises();
    const visited: string[] = [], entries = window.history.length;
    const stop = router.afterEach((to) => { visited.push(to.fullPath); });
    button("Yes, send")!.click();
    await flushPromises();
    await flushPromises();
    stop();
    expect(api.asked("PUT screens/:id").map((put) => put.path)).toEqual(["screens/hall", "screens/wall"]);
    expect(visited).toEqual(["/screens/wall?chat=layoutbot", "/screens/hall?chat=layoutbot"]);
    expect(scr.selected).toBe("hall");
    expect(bot.messages.at(-1)!.send).toBe("sent");
    expect(sheet()).not.toBeNull();
    // The screens it passed through took the browser's entry in place: Back closes the chat on the screen the person was
    // on, as before the question, and never lands on Wallbox.
    expect(window.history.length).toBe(entries);
    router.back();
    await new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/screens/hall");
    expect(scr.selected).toBe("hall");
    expect(sheet()).toBeNull();
  });

  it("brings the field into view when it takes focus, also where the frame never hears of the keyboard", async () => {
    await phone();
    useLayoutbotStore().open = true;
    await flushPromises();
    const asked: Element[] = [];
    Element.prototype.scrollIntoView = function (this: Element) { asked.push(this); };
    document.querySelector<HTMLTextAreaElement>(".bot-compose textarea")!.dispatchEvent(new FocusEvent("focus"));
    await new Promise((resolve) => setTimeout(resolve, 750));
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.every((element) => element.classList.contains("bot-compose"))).toBe(true);
    expect(sheet()!.classList.contains("typing")).toBe(false);  // no visual viewport here: the sheet knew nothing
  });

  it("sleeps without an AI Task and its sheet says how to connect one", async () => {
    useInventoryStore().inventory.layoutbot = [];
    await phone();
    expect(document.querySelector(".phone-dock .bot-fab")!.classList.contains("asleep")).toBe(true);
    useLayoutbotStore().open = true;
    await flushPromises();
    expect(sheet()!.querySelectorAll(".provider")).toHaveLength(4);
    expect(sheet()!.querySelector(".bot-compose")).toBeNull();
  });
});
