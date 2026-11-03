// What the wizards of Events understand of the entity someone picks to start an automation (model/automation.ts): a
// helper or sensor that turns on, a doorbell Home Assistant knows as one, any other event entity, a button; and the
// trigger each one gets, as Home Assistant's own editor writes it.
import { describe, expect, it } from "vitest";
import { automationYaml, title, trigger, triggerKind } from "../src/model/automation";
import { alertRoute, buttonFields } from "../src/model/alert-yaml";
import { doorbellAutomation, doorFields, triggerKind as doorbellKind, type DoorbellReference } from "../src/model/doorbell-yaml";

describe("what starts an automation", () => {
  it("reads a boolean, a sensor and a switch as turning on", () => {
    for (const entity of ["input_boolean.someone_at_the_door", "binary_sensor.porch_visitor", "switch.bell"]) {
      expect(triggerKind(entity)).toBe("on");
      expect(trigger(entity, "on")).toEqual({ trigger: "state", entity_id: entity, from: "off", to: "on" });
    }
  });

  it("reads a doorbell Home Assistant knows as ringing, and any other event as firing", () => {
    const known = { "event.front_door_doorbell": "doorbell" as const };
    expect(triggerKind("event.front_door_doorbell", known)).toBe("doorbell");
    expect(trigger("event.front_door_doorbell", "doorbell")).toEqual({ trigger: "doorbell.rang", target: { entity_id: "event.front_door_doorbell" } });
    // A doorbell's event entity picked without the suggestion still starts it: every new state is a ring.
    expect(triggerKind("event.front_door_doorbell")).toBe("event");
    expect(trigger("event.remote_button", "event")).toEqual({ trigger: "state", entity_id: "event.remote_button", not_from: ["unavailable", "unknown"] });
  });

  it("reads a button as pressed, and leaves what cannot start one out", () => {
    expect(triggerKind("input_button.ring")).toBe("press");
    expect(triggerKind("button.ring")).toBe("press");
    for (const entity of ["sensor.temperature", "light.hall", "camera.front_door"]) expect(triggerKind(entity)).toBeNull();
  });

  it("calls every automation Tessera: <name>, once", () => {
    expect(title("Front door")).toBe("Tessera: Front door");
    expect(title("tessera: Front door")).toBe("Tessera: Front door");
  });
});

describe("the doorbell's automation", () => {
  const reference: DoorbellReference = { show: "esp_screens_doorbell", timeout: { default: 60, min: 10, max: 600 },
    suggestions: [{ trigger: "binary_sensor.porch_visitor", kind: "on", camera: "camera.porch", name: "Porch Visitor" }] };

  it("follows what the add-on said of the doorbell, and the screens and timeout chosen", () => {
    expect(doorbellKind(reference, "binary_sensor.porch_visitor")).toBe("on");
    const automation = doorbellAutomation(reference, { trigger: "binary_sensor.porch_visitor", camera: "camera.porch", name: "Porch",
      screens: ["hallway", "kitchen"], timeout: 90 });
    expect(automation.alias.startsWith("Tessera: ")).toBe(true);
    expect(automation.triggers).toEqual([{ trigger: "state", entity_id: "binary_sensor.porch_visitor", from: "off", to: "on" }]);
    expect(automation.actions).toEqual([{ event: "esp_screens_doorbell", event_data: { camera: "camera.porch", screen: ["hallway", "kitchen"], timeout: 90 } }]);
    expect(automationYaml(automation)).toContain("    from: \"off\"\n    to: \"on\"");
  });

  it("names the door as the add-on reads it: a lock, or an entity's action, and nothing half chosen", () => {
    expect(doorFields({ kind: "lock", lock: "lock.front_door" })).toEqual({ lock: "lock.front_door" });
    expect(doorFields({ kind: "action", entity: "button.gate", action: "button.press" })).toEqual({ door_action: "button.press", door_data: { entity_id: "button.gate" } });
    expect(doorFields({ kind: "action", entity: "button.gate", action: "" })).toEqual({});
    expect(doorFields({ kind: "lock" })).toEqual({});
    expect(doorFields({ kind: "none", lock: "lock.front_door" })).toEqual({});
    const automation = doorbellAutomation(reference, { trigger: "binary_sensor.porch_visitor", camera: "camera.porch", door: { kind: "lock", lock: "lock.front_door" } });
    expect(automation.actions).toEqual([{ event: "esp_screens_doorbell", event_data: { camera: "camera.porch", lock: "lock.front_door" } }]);
    // Quiet only when asked: the sound is on by default and the automation leaves it out.
    expect(doorbellAutomation(reference, { camera: "camera.porch", sound: false }).actions[0].event_data).toEqual({ camera: "camera.porch", sound: false });
    expect(doorbellAutomation(reference, { camera: "camera.porch", sound: true }).actions[0].event_data).toEqual({ camera: "camera.porch" });
    expect(doorbellAutomation(reference, { camera: "camera.porch", chime: false }).actions[0].event_data).toEqual({ camera: "camera.porch", chime: false });
    // A missed ring kept for a while says how long; until someone opens it (0, as before) the automation leaves it out.
    expect(doorbellAutomation(reference, { camera: "camera.porch", keep: 30 }).actions[0].event_data).toEqual({ camera: "camera.porch", keep_minutes: 30 });
    expect(doorbellAutomation(reference, { camera: "camera.porch", keep: 0 }).actions[0].event_data).toEqual({ camera: "camera.porch" });
  });
});

describe("the alert's buttons and how it is sent", () => {
  const closes = { text: "OK", color: "", entity: "", action: "" };
  it("gives a button's action only when it has both an entity and an action, and the second button only with two", () => {
    expect(buttonFields(closes, null)).toEqual({ button_text: "OK", button_color: "" });
    expect(buttonFields({ text: "Open", color: "green", entity: "lock.front_door", action: "lock.unlock" },
      { text: "Not now", color: "red", entity: "light.hall", action: "" })).toEqual({
      button_text: "Open", button_color: "green", action: "lock.unlock", data: { entity_id: "lock.front_door" },
      button2_text: "Not now", button2_color: "red" });
    expect(buttonFields(closes, { text: "Snooze", color: "", entity: "script.snooze", action: "script.turn_on" })).toMatchObject({
      button2_action: "script.turn_on", button2_data: { entity_id: "script.snooze" } });
  });

  it("always goes as the event, and says which screens show one button or no picture", () => {
    const screens = [{ name: "Hall", choice: true, pictures: true }, { name: "Kitchen", choice: false, pictures: false }];
    expect(alertRoute({ two: false, actions: 0, camera: false }, screens)).toEqual([{ key: "event" }]);
    expect(alertRoute({ two: true, actions: 2, camera: true }, screens)).toEqual([
      { key: "event" }, { key: "one_button", screens: ["Kitchen"] }, { key: "action" }, { key: "no_picture", screens: ["Kitchen"] }]);
  });
});
