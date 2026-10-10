// The YAML Alerts hands out to copy (model/alert-yaml.ts), from what the add-on says of an alert's fields: kept as it
// stands by its snapshots, so a change to what someone pastes into Home Assistant is a change someone reads.
import { describe, expect, it } from "vitest";
import { actionYaml, allScreensYaml, choiceYaml, fieldValue, limitText, oneScreenYaml, screenValue, waitYaml, yamlName, yamlString,
  type AlertReference } from "../src/model/alert-yaml";

// What the add-on says of alerts (alert_reference), its fields as it names them, with generic boards.
const reference: AlertReference = {
  event: "esphome.screen_alert", broadcast: { show: "esp_screens_show_alert", dismiss: "esp_screens_dismiss_alert" },
  fields: [
    { name: "title", type: "string", example: "Someone is at the door" }, { name: "subtitle", type: "string", example: "Door 3, back" },
    { name: "icon", type: "string", example: "doorbell" }, { name: "color", type: "string", example: "orange" },
    { name: "button_text", type: "string", example: "Coming" }, { name: "timeout", type: "int", example: 0 }, { name: "flash", type: "bool", example: true },
  ],
  camera: { name: "camera", example: "camera.front_door" }, screen: { example: "kitchen-screen" },
  choice: { fields: [{ name: "button2_text", type: "string", example: "Not now" }], action2: { name: "button2_action", example: "script.snooze_reminder" } },
  limits: { compact: { title: 48, button_text: 12 }, standard: { title: 64, button_text: 16 } },
  limit_boards: { compact: ["Small board"], standard: ["Board A", "Board B"] },
};

describe("the YAML to copy", () => {
  it("writes a value as YAML takes it", () => {
    expect([yamlString('say "hi"\\'), yamlName("kitchen-screen"), yamlName("Living room"), screenValue({ node: "hall", name: "Hall" }), screenValue({ name: "Hall" })])
      .toEqual(['"say \\"hi\\"\\\\"', "kitchen-screen", '"Living room"', "hall", "Hall"]);
    expect(reference.fields!.map(fieldValue)).toEqual(['"Someone is at the door"', '"Door 3, back"', "doorbell", "orange", '"Coming"', "0", "true"]);
  });

  it("says the bytes a field holds on each look, with the boards that have it", () => {
    expect(limitText(reference, "title")).toMatchInlineSnapshot(`"Small board 48 · Board A and Board B 64 bytes"`);
    expect(limitText(reference, "subtitle")).toBe("");
    expect(limitText(undefined, "title")).toBe("");
  });

  it("gives one screen's action, and waiting for the answer", () => {
    expect(actionYaml(reference, "esphome.hall_show_alert")).toMatchInlineSnapshot(`
      "action: esphome.hall_show_alert
      data:
        title: "Someone is at the door"
        subtitle: "Door 3, back"
        icon: doorbell
        color: orange
        button_text: "Coming"
        timeout: 0
        flash: true"
    `);
    expect(actionYaml(undefined, "")).toMatchInlineSnapshot(`
      "action: esphome.<device_name>_show_alert
      data:
      "
    `);
    expect(waitYaml(reference, "esphome.hall_show_alert")).toMatchInlineSnapshot(`
      "# Doorbell: show the alert and wait until someone presses the button.
      actions:
        - action: esphome.hall_show_alert
          data:
            title: "Someone is at the door"
            subtitle: "Door 3, back"
            icon: doorbell
            color: orange
            button_text: "Coming"
            timeout: 0
            flash: true
        - wait_for_trigger:
            - trigger: event
              event_type: esphome.screen_alert
              event_data:
                action: ok
          timeout: "00:05:00"
        - if:
            - condition: template
              value_template: "{{ wait.trigger is not none }}"
          then:
            - action: notify.notify
              data:
                message: "Someone is coming to the door.""
    `);
  });

  it("gives the event for every screen, for one of them (a picture only where it draws one), and with two buttons", () => {
    expect(allScreensYaml(reference)).toMatchInlineSnapshot(`
      "event: esp_screens_show_alert
      event_data:
        title: "Someone is at the door"
        subtitle: "Door 3, back"
        icon: doorbell
        color: orange
        button_text: "Coming"
        timeout: 0
        flash: true
        # camera: camera.front_door   # a Guition shows its picture on the card"
    `);
    expect(oneScreenYaml(reference, { node: "hall", name: "Hall", pictures: true })).toMatchInlineSnapshot(`
      "event: esp_screens_show_alert
      event_data:
        screen: hall
        title: "Someone is at the door"
        subtitle: "Door 3, back"
        icon: doorbell
        color: orange
        button_text: "Coming"
        timeout: 0
        flash: true
        camera: camera.front_door"
    `);
    expect(oneScreenYaml(reference, { name: "Small one", pictures: false })).toMatchInlineSnapshot(`
      "event: esp_screens_show_alert
      event_data:
        screen: "Small one"
        title: "Someone is at the door"
        subtitle: "Door 3, back"
        icon: doorbell
        color: orange
        button_text: "Coming"
        timeout: 0
        flash: true"
    `);
    expect(oneScreenYaml({}, undefined)).toMatchInlineSnapshot(`
      "event: esp_screens_show_alert
      event_data:
        screen: kitchen-screen"
    `);
    expect(choiceYaml(reference)).toMatchInlineSnapshot(`
      "event: esp_screens_show_alert
      event_data:
        title: "Someone is at the door"
        icon: doorbell
        button_text: "Coming"
        button_color: green
        button2_text: "Not now"
        button2_color: red
        action: script.open_gate
        button2_action: script.snooze_reminder"
    `);
  });
});
