// The troubleshooting report of a screen (ReportPanel, "My screen doesn't work right"): the page is a route of its own
// (#/screens/<id>/report), Collect asks the add-on and follows the report every 1.5 seconds until it is ready, every file
// can be read before anything is sent, and Send with consent ends in a reference to quote. A report sent before shows
// its reference again when the page is reopened, and a failed one offers Try again.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ReportPanel from "../src/components/ReportPanel.vue";
import { router } from "../src/router";
import { MOMENT, useFakeClock } from "./helpers/clock";
import { fakeApi, reply, type Routed } from "./helpers/fake-api";
import { useInventoryStore } from "../src/stores/inventory";
import { useUiStore } from "../src/stores/ui";

const offer = { ready: true, blockers: [], retention_days: 30, last: null, email: null, privacy_url: "https://example.com/privacy",
  crash: { at: new Date(MOMENT - 2 * 3600 * 1000).toISOString(), reason: "Abort - assert failed (task watchdog)", decoded: ["0x48016bb4: esp_video at file.c:123"], count: 2 } };
const summary = { board: "tab5", board_name: "M5Stack Tab5", chip: "esp32p4", firmware: "0.57.0", channel: "dev", esphome: "2026.9.0", addon: "0.4.90",
  ha: "2026.10.2", plugins: [{ id: "screen_camera", version: "0.4.2" }], crash: null, online: true, built_on: "addon", elf: true };
const files = [{ name: "report.md", size: 5120, lines: 120, kind: "md" }, { name: "summary.json", size: 2048, lines: 60, kind: "json" }];
const collecting = { id: "r-1", screen: "living", depth: "basic", state: "collecting", step: "screen_log", progress: 0.4, files: [], summary: null,
  warnings: [], size: 0, reference: null, sent_at: null, error: null };
const ready = { ...collecting, state: "ready", step: "zip", progress: 1, files, summary, warnings: ["no_elf"], size: 184320 };

async function openPanel(routes: Record<string, Routed>) {
  useInventoryStore().inventory = { connected: true, screens: [{ id: "living", name: "Living room", online: true, board: "tab5", layout: { title: "Living room", tiles: [] } }], entities: [] } as any;
  const api = fakeApi(routes);
  await useUiStore().openReport("living");
  const panel = mount(ReportPanel);
  await flushPromises();
  return { api, panel };
}

describe("the troubleshooting report", () => {
  it("is a route of its own", async () => {
    const ui = useUiStore();
    await ui.openReport("living");
    expect(router.currentRoute.value.fullPath).toBe("/screens/living/report");
    expect(ui.route).toBe("#report");
    expect(ui.reportScreen).toBe("living");
  });

  it("collects, lets every file be read, and sends with consent", async () => {
    const clock = useFakeClock();
    let polls = 0;
    const { api, panel } = await openPanel({
      "GET screens/:id/report": offer,
      "POST screens/:id/report": reply(202, { id: "r-1" }),
      "GET reports/:id": () => (++polls < 2 ? collecting : ready),
      "GET reports/:id/files/:name": ({ params }: any) => reply(200, `# Report\n\nfile ${params.name}`),
      "POST reports/:id/send": ({ body }: any) => body.consent === true ? { state: "sent", reference: "TR-7K3M9Q", expires_at: "2026-11-22T12:00:00Z" } : reply(400, { error: "no consent" }),
    });
    // The start: the last crash, and the choices.
    expect(panel.find("#report-title").text()).toBe("Living room doesn't work right");
    expect(panel.find("#report-crash").text()).toContain("Abort - assert failed (task watchdog), 2 hours ago, seen 2 times this week");
    await panel.find("#report-full").setValue(true);
    await panel.find("#report-note").setValue("The screen reboots when I open the camera.");
    await panel.find("#report-email").setValue("me@example.com");
    await panel.find("#report-collect").trigger("click");
    await clock.settle();
    expect(api.asked("POST screens/:id/report")[0].body).toEqual({ depth: "full" });
    // Collecting: the add-on's step, followed every 1.5 seconds.
    expect(panel.find("#report-collecting").exists()).toBe(true);
    expect(panel.find("#report-step").text()).toBe("Listening to the screen's log");
    expect(panel.find(".progress i").attributes("style")).toContain("width: 40%");
    await clock.tick(1500);
    expect(api.count("GET reports/:id")).toBe(2);
    // Ready: the facts, the warning, the files.
    expect(panel.find("#report-summary").text()).toContain("M5Stack Tab5 (tab5)");
    expect(panel.find("#report-summary").text()).toContain("0.57.0 (dev)");
    expect(panel.find("#report-summary").text()).toContain("screen_camera 0.4.2");
    expect(panel.find("#report-warnings").text()).toContain("debug file is missing");
    const rows = panel.findAll(".rp-file");
    expect(rows.map((row) => row.find("code").text())).toEqual(["report.md", "summary.json"]);
    expect(rows[0].text()).toContain("5.0 KB");
    await rows[1].trigger("click");
    await flushPromises();
    // The real route answers plain text; the fake API answers everything as JSON, so the text shows quoted here.
    expect(panel.find("#report-file-view pre").text()).toBe(JSON.stringify("# Report\n\nfile summary.json"));
    expect(panel.find("#report-download").attributes("href")).toBe("api/reports/r-1.zip");
    // Send: only with consent.
    expect(panel.find("#report-send").text()).toContain("kept for 30 days");
    expect(panel.find("#report-send-button").attributes("disabled")).toBeDefined();
    await panel.find("#report-consent").setValue(true);
    await panel.find("#report-send-button").trigger("click");
    await flushPromises();
    expect(api.asked("POST reports/:id/send")[0].body).toEqual({ consent: true, note: "The screen reboots when I open the camera.", email: "me@example.com", remember_email: false });
    expect(panel.find("#report-reference").text()).toBe("TR-7K3M9Q");
    const issue = new URL(panel.find("#report-github").attributes("href")!);
    expect(issue.searchParams.get("title")).toBe("[Bug]: M5Stack Tab5");
    expect(issue.searchParams.get("versions")).toBe("add-on 0.4.90, firmware 0.57.0");
    expect(issue.searchParams.get("what-happened")).toBe("The screen reboots when I open the camera.\n\nReport reference: TR-7K3M9Q\nBoard: M5Stack Tab5 (tab5)");
    expect(panel.find("#report-discord").attributes("href")).toBe("https://discord.gg/M7x96AUzC");
  });

  it("says why a send did not go through and keeps the download", async () => {
    const clock = useFakeClock();
    const { panel } = await openPanel({
      "GET screens/:id/report": offer,
      "POST screens/:id/report": reply(202, { id: "r-1" }),
      "GET reports/:id": ready,
      "POST reports/:id/send": { state: "offline", error: "Tessera could not be reached." },
    });
    await panel.find("#report-collect").trigger("click");
    await clock.settle();
    await panel.find("#report-consent").setValue(true);
    await panel.find("#report-send-button").trigger("click");
    await flushPromises();
    expect(panel.find("#report-send-error").text()).toBe("Tessera could not be reached.");
    expect(panel.find("#report-download").exists()).toBe(true);
    expect(panel.find("#report-reference").exists()).toBe(false);
  });

  it("shows the reference of a report sent before, and a blocker keeps Collect off", async () => {
    const { panel } = await openPanel({
      "GET screens/:id/report": { ...offer, email: "me@example.com", last: { id: "r-0", reference: "TR-AB12CD", sent_at: "2026-10-23T12:00:00Z", depth: "basic" } },
      "GET reports/:id": { ...ready, id: "r-0", state: "sent", reference: "TR-AB12CD" },
    });
    expect(panel.find("#report-reference").text()).toBe("TR-AB12CD");
    await panel.find("#report-new").trigger("click");
    await flushPromises();
    expect(panel.find("#report-collect").exists()).toBe(true);
    expect((panel.find("#report-email").element as HTMLInputElement).value).toBe("me@example.com");
  });

  it("keeps Collect off behind a blocker", async () => {
    const { panel } = await openPanel({ "GET screens/:id/report": { ...offer, ready: false, blockers: ["no_profile"] } });
    expect(panel.find("#report-collect").attributes("disabled")).toBeDefined();
    expect(panel.text()).toContain("This screen's YAML is not in this app's folder");
  });

  it("says why a collect failed and offers Try again", async () => {
    const clock = useFakeClock();
    const { api, panel } = await openPanel({
      "GET screens/:id/report": offer,
      "POST screens/:id/report": reply(202, { id: "r-2" }),
      "GET reports/:id": { ...collecting, id: "r-2", state: "failed", error: "The screen's profile could not be read." },
    });
    await panel.find("#report-collect").trigger("click");
    await clock.settle();
    expect(panel.find("#report-failed").text()).toContain("The screen's profile could not be read.");
    await panel.find("#report-retry").trigger("click");
    await flushPromises();
    expect(panel.find("#report-collect").exists()).toBe(true);
    expect(api.count("GET screens/:id/report")).toBe(2);
  });
});
