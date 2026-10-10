// The screensaver of the open screen (stores/screensaver.ts): its steps turned on and off and moved, the players of the
// music step, the summary of each step, and the clock's row of entities with its add, move and remove (undo included),
// each change shown at once and sent whole to the add-on.
import { describe, expect, it } from "vitest";
import { i18n } from "../../src/i18n";
import { openSaverItem, state } from "../../src/store";
import { SAVER_ITEMS_MAX, useScreensaverStore } from "../../src/stores/screensaver";
import { useScreenStore } from "../../src/stores/screen";
import { useUiStore } from "../../src/stores/ui";
import type { HeaderItem, Screen, ScreensaverChoice } from "../../src/types";
import { fakeApi } from "../helpers/fake-api";

const t = (key: string, named: Record<string, unknown> = {}) => i18n.global.t(key, named);
const entity = (id: string): HeaderItem => ({ type: "entity", entity: id, content: "state", icon: "auto", show: "always" });
function open(patch: Partial<ScreensaverChoice> = {}) {
  const screensaver = { show: true, media: "", camera: "", order: ["media", "camera", "clock"], off: [], weather: "auto", more: [], items: [],
    ready: true, pictures: true, ...patch } as ScreensaverChoice;
  state.inventory = { screens: [{ id: "hall", name: "Hall", online: true, layout: { title: "Hall", tiles: [] }, screensaver } as unknown as Screen],
    entities: ["media_player.kitchen", "media_player.study", "media_player.hall", "media_player.attic", "media_player.porch", "camera.door", "weather.home"]
      .map((id) => ({ id, name: id.split(".")[1], state: "", area: "" })) } as any;
  useScreenStore().selected = "hall";
  const api = fakeApi({ "PUT screens/:id/screensaver": ({ body }) => ({ screensaver: { ...body.screensaver, ready: true, pictures: true } }) });
  return { saver: useScreensaverStore(), api };
}

describe("the screensaver's steps", () => {
  it("turns a step off and on, moves it, and shows only the clock on a board without pictures", () => {
    const { saver, api } = open();
    saver.toggleStep("camera");
    expect([saver.isOn("camera"), saver.saver?.off]).toEqual([false, ["camera"]]);
    saver.toggleStep("camera");
    expect(saver.isOn("camera")).toBe(true);
    saver.moveStep("clock", -1);
    expect(saver.savedOrder).toEqual(["media", "clock", "camera"]);
    // Past either end the order stays as it is.
    saver.moveStep("media", -1);
    expect(saver.savedOrder).toEqual(["media", "clock", "camera"]);
    expect(api.count("PUT screens/:id/screensaver")).toBe(3);
    expect(saver.stepsShown(null)).toEqual(["media", "clock", "camera"]);
    useScreenStore().currentScreen!.screensaver!.pictures = false;
    expect(saver.stepsShown(null)).toEqual(["clock"]);
  });

  it("keeps up to four players, each once, the first as the screen's own media", () => {
    const { saver } = open();
    for (const id of ["media_player.kitchen", "media_player.kitchen", "media_player.study", "media_player.hall", "media_player.attic", "media_player.porch"])
      saver.addPlayer(id);
    expect(saver.players).toEqual(["media_player.kitchen", "media_player.study", "media_player.hall", "media_player.attic"]);
    expect([saver.saver?.media, saver.saver?.more]).toEqual(["media_player.kitchen", ["media_player.study", "media_player.hall", "media_player.attic"]]);
    saver.removePlayer("media_player.kitchen");
    expect(saver.saver?.media).toBe("media_player.study");
    expect(saver.entitiesOf("media", saver.players).map((e) => e.id)).toEqual(["media_player.kitchen", "media_player.porch"]);
  });

  it("says in one line what each step shows", () => {
    const { saver } = open({ media: "media_player.kitchen", weather: "", items: [entity("camera.door")] });
    expect(saver.summary("media")).toEqual({ text: "kitchen" });
    expect(saver.summary("camera")).toEqual({ text: t("editor.screen_settings.screensaver.summary.camera_none"), missing: true });
    expect(saver.summary("clock").text).toBe(`${t("editor.screen_settings.screensaver.summary.time_date")}, door`);
    expect(saver.weatherSource).toBe("");
    saver.changeSaver({ weather: "auto" });
    expect(saver.weatherSource).toBe("weather.home");
  });
});

describe("the clock's row of entities", () => {
  it("adds an entity once and up to four, moves it, and takes it off with undo back to the clock's drawer", () => {
    const { saver, api } = open();
    const ui = useUiStore();
    saver.addSaverItem(entity("media_player.kitchen"));
    expect(state.inspector).toEqual({ kind: "saver-item", index: 0 });
    saver.addSaverItem({ ...entity("media_player.kitchen"), content: "icon" });
    expect(ui.notice?.message).toBe(t("editor.screen_settings.screensaver.items_already"));
    for (const id of ["camera.door", "weather.home", "media_player.study", "media_player.hall"]) saver.addSaverItem(entity(id));
    expect(saver.saverItems).toHaveLength(SAVER_ITEMS_MAX);
    expect(ui.notice?.message).toBe(t("editor.screen_settings.screensaver.items_full", { n: SAVER_ITEMS_MAX }));
    saver.updateSaverItem(1, { content: "icon" });
    expect(saver.moveSaverItem(1, 0)).toBe(true);
    expect(saver.saverItems.map((item) => [item.entity, item.content])).toEqual([["camera.door", "icon"], ["media_player.kitchen", "state"],
      ["weather.home", "state"], ["media_player.study", "state"]]);
    openSaverItem(0);
    saver.removeSaverItem(0);
    expect(state.inspector).toEqual({ kind: "saver", step: "clock" });
    expect(saver.saverItems.map((item) => item.entity)).not.toContain("camera.door");
    ui.notice!.action!.run();
    expect(saver.saverItems[0].entity).toBe("camera.door");
    // Every change went to the add-on whole, its items without the editor's ids.
    expect(api.asked("PUT screens/:id/screensaver").at(-1)!.body.screensaver.items[0]).toEqual({ type: "entity", entity: "camera.door", content: "icon", icon: "auto", show: "always" });
  });
});
