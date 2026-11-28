// The template tile's completion (model/template-complete.ts): what the editor offers where the cursor stands.
import { describe, expect, it } from "vitest";
import { closer, closest, contextAt, errorLine, FUNCTIONS, openBrace, quotedIds, refsOf, shown, statesOf, TAGS } from "../src/model/template-complete";

const at = (text: string) => contextAt(text);

describe("template completion", () => {
  it("knows whether the cursor is inside the braces", () => {
    expect(openBrace("# Hi {{ states(")).toBe(5);
    expect(openBrace("{{ 1 }} after")).toBe(-1);
    expect(openBrace("{% if x %}")).toBe(-1);
  });
  it("offers entities as the first argument", () => {
    expect(at("{{ states('sensor.kit")).toEqual({ kind: "entity", from: 11, quote: "'" });
    expect(at('{% if is_state("light.')).toMatchObject({ kind: "entity", quote: '"' });
    expect(at("{{ state_attr('")).toMatchObject({ kind: "entity" });
    expect(at("{{ area_name('")).toMatchObject({ kind: "entity" });
  });
  it("offers the attributes of the entity named", () => {
    expect(at("{{ state_attr('climate.living', 'curr")).toEqual({ kind: "attribute", from: 33, entity: "climate.living", quote: "'" });
    expect(at("{{ states.climate.living.attributes.")).toMatchObject({ kind: "attribute", entity: "climate.living", quote: "" });
  });
  it("offers the states the entity may have", () => {
    expect(at("{% if is_state('sensor.dishwasher', '")).toMatchObject({ kind: "state", entity: "sensor.dishwasher" });
    expect(at("{% if states('lock.door') == '")).toMatchObject({ kind: "state", entity: "lock.door" });
    expect(statesOf("lock.door", "jammed")).toEqual(["jammed", "locked", "unlocked", "locking", "unlocking", "open", "unavailable", "unknown"]);
    expect(statesOf("select.mode", "eco", ["eco", "comfort"])).toEqual(["eco", "comfort", "unavailable", "unknown"]);
  });
  it("walks states.<domain>.<object>.", () => {
    expect(at("{{ states.")).toMatchObject({ kind: "domain" });
    expect(at("{{ states.light.")).toMatchObject({ kind: "object", domain: "light" });
    expect(at("{{ states.light.desk.la")).toMatchObject({ kind: "member", entity: "light.desk" });
  });
  it("offers filters, tags and functions", () => {
    expect(at("{{ states('sensor.x') | ro")).toMatchObject({ kind: "filter" });
    expect(at("{% ")).toMatchObject({ kind: "tag" });
    expect(at("{% if is_")).toMatchObject({ kind: "function" });
    expect(at("{{ 'a string with is_")).toEqual({ kind: "none" });
  });
  it("offers the tile's markup at the start of a line", () => {
    expect(at("Hello\n  ")).toMatchObject({ kind: "markup", from: 8 });
    expect(at("Hello\n:go")).toMatchObject({ kind: "markup", from: 6 });
    expect(at("Some words here")).toEqual({ kind: "none" });
  });
  it("closes a string unless it is closed", () => {
    expect(closer("'", ")")).toBe("'");
    expect(closer("'", "')")).toBe("");
  });
  it("finds what a template reads, inside the braces only", () => {
    const text = "states('x.y') {{ states('sensor.a') }} {% if is_state('lock.d', 'locked') %}{{ state_attr('climate.c', 'temp') }}";
    const refs = refsOf(text);
    expect(refs.map((r) => [r.kind, r.entity, r.attribute ?? r.value ?? ""])).toEqual([
      ["state", "sensor.a", ""], ["is", "lock.d", "locked"], ["attr", "climate.c", "temp"]]);
    expect(text.slice(refs[0].from, refs[0].to)).toBe("sensor.a");
    expect(text.slice(refs[0].end - 2, refs[0].end)).toBe("')");
    expect(refsOf("{{ states.sensor.a.state }}")).toEqual([]);
    expect(quotedIds("'a.b' {{ 'light.x' }}").map((q) => q.id)).toEqual(["light.x"]);
  });
  it("names the entity a typing slip meant", () => {
    const ids = ["sensor.zonnepanelen_vermogen", "sensor.net_vermogen", "light.aanrecht"];
    expect(closest("sensor.zonnepanele_vermogen", ids)).toBe("sensor.zonnepanelen_vermogen");
    expect(closest("light.aanrechtt", ids)).toBe("light.aanrecht");
    expect(closest("switch.garage", ids)).toBeNull();
  });
  it("reads the line of Home Assistant's error", () => {
    expect(errorLine("TemplateSyntaxError: unexpected '}' (line 3)")).toBe(3);
    expect(errorLine("UndefinedError: 'x' is undefined")).toBeNull();
  });
  it("writes a value short, with its unit", () => {
    expect(shown("2.43", "kW")).toBe("2.43 kW");
    expect(shown("unavailable", "kW")).toBe("unavailable");
    expect(shown(["a", "b"])).toBe('["a","b"]');
    expect(shown("x".repeat(40)).length).toBe(28);
  });
  it("gives snippets fields to Tab through", () => {
    expect(FUNCTIONS.find((f) => f.label === "is_state")?.apply).toBe("is_state('${entity_id}', '${state}')");
    expect(TAGS.find((f) => f.label === "if")?.apply).toBe("if ${condition} %}\n${}\n{% endif %}");
  });
});
