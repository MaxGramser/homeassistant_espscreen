// The add-on's answers: what a failed request says to the person using the page.
import { afterEach, describe, expect, it, vi } from "vitest";
import { getJson, send, setCsrf } from "../src/api";

const answer = (status: number, body: string, type = "application/json") =>
  vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status, headers: { "Content-Type": type } })));

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("shows the add-on's own sentence for any failed answer with a JSON error (app 0.2.78)", async () => {
    answer(400, JSON.stringify({ error: "Home Assistant refused light.turn_on: the entity is unavailable." }));
    await expect(send("screens/x", "PUT", {})).rejects.toThrow("Home Assistant refused light.turn_on: the entity is unavailable.");
    answer(503, JSON.stringify({ error: "Home Assistant didn't answer in time. Try again in a moment." }));
    await expect(getJson("capabilities?entity=light.a")).rejects.toThrow("Home Assistant didn't answer in time. Try again in a moment.");
    answer(502, JSON.stringify({ error: "Bad gateway from Home Assistant." }));
    await expect(getJson("states")).rejects.toThrow("Bad gateway from Home Assistant.");
  });
  it("keeps the general sentence for an answer that isn't JSON or has no error in it", async () => {
    const general = "That didn't work. Refresh the page and try again.";
    answer(502, "<html><body>502 Bad Gateway</body></html>", "text/html");
    await expect(getJson("inventory")).rejects.toThrow(general);
    answer(500, JSON.stringify({ detail: "nope" }));
    await expect(getJson("inventory")).rejects.toThrow(general);
    answer(500, JSON.stringify({ error: "" }));
    await expect(getJson("inventory")).rejects.toThrow(general);
  });
  it("sends relative URLs with the CSRF header and reads an empty answer as null", async () => {
    answer(200, "");
    expect(await send("screens/x/identify", "POST")).toBeNull();
    const call = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call[0]).toBe("api/screens/x/identify");
    expect(call[1].headers).toHaveProperty("X-Screen-CSRF");
  });
  it("sends multipart files through ingress with CSRF without overriding the browser boundary", async () => {
    answer(200, JSON.stringify({ id: "ww_local", upload: "opaque-token" }));
    setCsrf("test-csrf");
    const form = new FormData();
    form.append("manifest", new File(["{}"], "manifest.json", { type: "application/json" }));
    form.append("model", new File(["synthetic"], "model.tflite"));
    try {
      await send("screens/x/plugins/voice/models/wake_models/import?source=folder", "POST", form);
      const call = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(call[0]).toBe("api/screens/x/plugins/voice/models/wake_models/import?source=folder");
      expect(call[1].body).toBe(form);
      expect(call[1].headers).toMatchObject({ "X-Screen-CSRF": "test-csrf", "X-ESP-Screens-Language": "en" });
      expect(call[1].headers).not.toHaveProperty("Content-Type");
      await send("screens/x/plugins", "POST", { add: [] });
      const json = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[1][1];
      expect(json.headers["Content-Type"]).toBe("application/json");
      expect(json.body).toBe('{"add":[]}');
    } finally {
      setCsrf("");
    }
  });
});
