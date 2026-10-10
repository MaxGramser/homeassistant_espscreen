// What a card on the mockup writes (model/tile-text.ts): the line under its name, the second line, the values a large card
// stands tall, and the firmware's number rules it ports (tests/test_editor_parity.py runs those against the C++ too).
import { describe, expect, it } from "vitest";
import { bigKeyLine, bigValue, bodyText, decimalText, favoriteLine, fillPercent, haWord, headLine, humidityText, isOn, pageLink, rangeChip,
  readingText, roundValue, runText, sameLive, setpointText, stateText, subLine, temperatureText, unitSuffix, type ScreenWords } from "../src/model/tile-text";

const en: ScreenWords = { locale: "en", marks: { decimal: ".", group: ",", from: 4 } };
const comma: ScreenWords = { locale: "en", marks: { decimal: ",", group: ".", from: 4 }, percentSpace: true };
const climate = (state: string, a: Record<string, any>) => ({ state, a });

describe("the firmware's number rules", () => {
  it("writes a temperature as Home Assistant sends it, two decimals at most (temperature_text)", () => {
    expect([21, 21.5, 20.25, 20.333, 73, -3.5, 0].map((v) => temperatureText(v, en))).toEqual(["21°", "21.5°", "20.25°", "20.33°", "73°", "-3.5°", "0°"]);
    expect(temperatureText(21.5, comma)).toBe("21,5°");
  });

  it("writes a humidity whole or with one decimal, a tie to the even digit as printf does (humidity_text)", () => {
    expect([45, 41.5, 45.04, 45.96, 41.25, 41.75].map((v) => humidityText(v, en))).toEqual(["45%", "41.5%", "45%", "46%", "41.2%", "41.8%"]);
    expect(humidityText(41.5, comma)).toBe("41,5 %");
    expect(decimalText(-0.25, 1, en)).toBe("-0.2");
  });

  it("reads a thermostat in its own unit (reading_text)", () => {
    expect([readingText("climate", 20.5, en), readingText("humidifier", 40, en)]).toEqual(["20.5°", "40%"]);
  });

  it("spaces a unit as Home Assistant does", () => {
    expect([unitSuffix("°"), unitSuffix("%"), unitSuffix("%", true), unitSuffix("kWh"), unitSuffix(undefined)]).toEqual(["°", "%", " %", " kWh", ""]);
  });
});

describe("the line under a card's name", () => {
  it("says what a thermostat with a control is doing and what it measures (status_text)", () => {
    const heating = climate("heat", { hvac_action: "heating", current_temperature: 20.25, temperature: 21.5 });
    expect(stateText("climate.living", heating, { controlled: true }, en)).toBe("Heating · 20.25°");
    // Without a control the temperature it is set to; off, its mode and what it measures; a range, its state.
    expect(stateText("climate.living", heating, {}, en)).toBe("21.5°");
    expect(stateText("climate.living", climate("off", { current_temperature: 19 }), {}, en)).toBe("Off · 19°");
    expect(stateText("climate.living", climate("heat_cool", { current_temperature: 21 }), {}, en)).toBe("Heat/Cool · 21°");
    expect(stateText("climate.living", climate("cool", {}), { controlled: true }, en)).toBe("Cool");
  });

  it("says what a humidifier is doing and the humidity it measures (climate_card_status, brief)", () => {
    expect(stateText("humidifier.h", climate("on", { action: "humidifying", current_humidity: 41.5 }), {}, en)).toBe("Humidifying · 41.5%");
    expect(stateText("humidifier.h", climate("off", { action: "humidifying" }), {}, en)).toBe("Off");
    expect(stateText("humidifier.h", climate("on", {}), {}, en)).toBe("On");
  });

  it("takes Home Assistant's words: a door is open, a blind closing, a word it sent", () => {
    expect(stateText("binary_sensor.door", climate("on", { device_class: "door" }), {}, en)).toBe("Open");
    expect(stateText("binary_sensor.thing", climate("off", { device_class: "made_up" }), {}, en)).toBe("Off");
    expect(haWord("weather", { state: "windy-variant" }, en)).toBe("Windy");
    expect(stateText("cover.blind", climate("open", { current_position: 60 }), {}, en)).toBe("Open · 60%");
    expect(stateText("cover.blind", climate("open", { current_position: 100 }), {}, en)).toBe("Open");
    expect(stateText("washer.x", { state: "rinsing", word: "Rinsing now" }, {}, en)).toBe("Rinsing now");
    expect(stateText("vacuum.robot", climate("returning_home", {}), {}, en)).not.toBe("");
  });

  it("writes a measurement with its unit and a number as the screens write numbers", () => {
    expect(stateText("sensor.power", climate("1234.5", { unit_of_measurement: "W" }), {}, en)).toBe("1,234.5 W");
    expect(stateText("sensor.power", climate("1234.5", { unit_of_measurement: "W" }), {}, comma)).toBe("1.234,5 W");
    expect(stateText("sensor.code", climate("1234", {}), {}, en)).toBe("1234");
    expect(stateText("counter.visits", climate("1234", {}), {}, en)).toBe("1,234");
    expect(stateText("weather.home", climate("sunny", { temperature: 14.2 }), {}, en)).toBe("Sunny · 14.2°");
    expect(stateText("media_player.speaker", climate("playing", { media_title: "Song" }), {}, en)).toBe("Playing · Song");
    expect(stateText("remote.tv", climate("on", { current_activity: "Watch TV" }), {}, en)).toBe("Watch TV");
  });

  it("says nothing of a scene, unavailable or unknown for one that is gone, Running or Off for a run key", () => {
    expect(stateText("scene.evening", climate("2026-10-01", {}), { note: "Clock" }, en)).toBe("Clock");
    expect(stateText("sensor.x", climate("unavailable", {}), {}, en)).toBe("Unavailable");
    expect(stateText("sensor.x", climate("unknown", {}), {}, en)).not.toBe("Unavailable");
    expect(stateText("automation.a", climate("on", { current: 1 }), { runs: true }, en)).toBe("Running...");
    expect(stateText("automation.a", climate("off", {}), { runs: true }, en)).toBe("Off");
    expect(stateText("sensor.x", null, { note: "Graph" }, en)).toBe("Graph");
  });

  it("follows the second line chosen in the tile panel", () => {
    const live = climate("on", { brightness: 128, effect: "" });
    expect([subLine("none", live, "On", en), subLine("text:Upstairs", live, "On", en), subLine("attr:brightness", live, "On", en),
      subLine("attr:effect", live, "On", en), subLine("auto", live, "On", en)]).toEqual(["", "Upstairs", "128", "On", "On"]);
  });
});

describe("the values a card stands large", () => {
  it("takes a Big number's value and a key's circle as the screen does", () => {
    expect(bigValue("sensor", climate("21.37", { unit_of_measurement: "°C" }), en)).toBe("21.37");
    expect(bigValue("sensor", climate("unavailable", {}), en)).toBe("—");
    expect(roundValue("sensor", climate("21", { unit_of_measurement: "°C" }), en)).toBe("21°");
    expect(roundValue("sensor", climate("48", { unit_of_measurement: "%" }), en)).toBe("48%");
    expect(roundValue("light", climate("on", {}), en)).toBe("");
  });

  it("fills a slider with what the entity reports, a blind with its closed part", () => {
    expect(fillPercent("light", climate("on", { brightness: 128 }))).toBe(50);
    expect(fillPercent("light", climate("off", { brightness: 128 }))).toBe(0);
    expect(fillPercent("cover", climate("open", { current_position: 60 }))).toBe(40);
    expect(fillPercent("humidifier", climate("off", { humidity: 45, min_humidity: 30, max_humidity: 80 }))).toBe(30);
    expect(fillPercent("number", climate("3", { min: 0, max: 10 }))).toBe(30);
    expect(fillPercent("sensor", climate("3", {}))).toBe(0);
  });

  it("puts a range's low end in a chip between the -/+, where the screen draws one", () => {
    const range = climate("heat_cool", { supported_features: 2, target_temp_low: 19, target_temp_high: 24, target_temp_step: 1 });
    const chip = rangeChip("climate", range, true, en);
    expect(chip?.text).toBe("19°");
    expect(rangeChip("climate", range, false, en)).toBeNull();
    expect(setpointText("climate", range, chip, en)).toBe("19°");
    expect(setpointText("climate", climate("heat", { temperature: 21.5 }), null, en)).toBe("21.5°");
    expect(setpointText("humidifier", climate("on", { humidity: 45 }), null, comma)).toBe("45 %");
    expect(setpointText("climate", climate("heat", {}), null, en)).toBe("—");
  });

  it("says how bright a lamp is under its big key, and when a script never ran", () => {
    expect(bigKeyLine("light", climate("on", { brightness: 255 }), "On", 100, en)).toBe("100%");
    expect(bigKeyLine("script", climate("off", {}), "Off", 0, en)).toBe("Never run");
    expect(bigKeyLine("script", climate("off", { last_triggered: "2026-10-09" }), "Yesterday", 0, en)).toBe("Yesterday");
    expect(bigKeyLine("switch", climate("on", {}), "On", 0, en)).toBe("On");
    expect(isOn("automation", climate("on", {}), true)).toBe(false);
  });

  it("stands a tall card's value in its body and leaves it out of the line under its name", () => {
    expect(bodyText("light", climate("on", {}), true, "On", 70)).toBe("70%");
    expect(bodyText("sensor", climate("21", {}), true, "21 °C", 0)).toBe("21 °C");
    expect(bodyText("climate", climate("heat", {}), true, "21°", 0)).toBe("");
    expect(bodyText("sensor", climate("21", {}), false, "21 °C", 0)).toBe("");
    expect([headLine("21 °C", "21 °C"), headLine("21 °C", "21 °C · Kitchen"), headLine("21 °C", "Upstairs"), headLine("", "On")]).toEqual(["", "", "Upstairs", "On"]);
  });

  it("labels a run key, a page link and a favourite as the screens do", () => {
    expect([runText("scene", en), runText("script", en), runText("button", en)]).toEqual(["Activate", "Run", "Press"]);
    expect(pageLink(2, en)).toBe("Page 2 ›");
    expect(favoriteLine(undefined, "Kitchen", en)).toBe("Kitchen");
    expect(favoriteLine(undefined, undefined, en)).toBe("");
    // The kind of thing it plays, in the add-on's words for the screens, which come with the page.
    expect(favoriteLine("playlist", "Kitchen", en)).toBe("Playlist · Kitchen");
    expect(favoriteLine("track", undefined, en)).toBe("Song");
    expect(favoriteLine("unheard_of", "Kitchen", en)).toBe("Kitchen");
  });

  it("knows a report that says the same", () => {
    const a = { brightness: 1 };
    expect(sameLive({ state: "on", a }, { state: "on", a, word: null })).toBe(true);
    expect(sameLive({ state: "on", a: {} }, { state: "on", a: {} })).toBe(true);
    expect(sameLive({ state: "on", a }, { state: "on", a: { brightness: 1 } })).toBe(false);
    expect(sameLive({ state: "on", a: {} }, { state: "off", a: {} })).toBe(false);
  });
});
