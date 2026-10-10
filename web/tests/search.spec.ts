// The editor's searches (model/search.ts): the library, ⌘K, the pickers, New screen's boards and the plugins compare
// what is typed the same way.
import { describe, expect, it } from "vitest";
import { iconGroupsMatching, matchesQuery, matchesWords, prefixRank, queryWords, rankedValues } from "../src/model/search";

describe("a search", () => {
  it("finds what is typed in any field, without case, and across the space between two fields", () => {
    expect(matchesQuery("  KITCHEN ", "Ceiling", "light.ceiling", "Kitchen")).toBe(true);
    expect(matchesQuery("ceiling light", "Ceiling", "light.ceiling")).toBe(true);
    expect(matchesQuery("lamp", "Ceiling", "light.ceiling", undefined, null)).toBe(false);
    // Nothing typed finds everything; an empty field still takes its place between the spaces.
    expect(matchesQuery("", "anything")).toBe(true);
    expect(matchesQuery("a  b", "a", undefined, "b")).toBe(true);
  });
  it("of several words finds what has each of them somewhere", () => {
    const words = queryWords("  Waveshare  4.3 ");
    expect(words).toEqual(["waveshare", "4.3"]);
    expect(matchesWords(words, "Waveshare ESP32-S3 Touch LCD", 4.3)).toBe(true);
    expect(matchesWords(words, "Guition", 4)).toBe(false);
    expect(matchesWords([], "anything")).toBe(true);
  });
  it("ranks a name that starts with it first, then one with a word that does, as Spotlight does", () => {
    expect(prefixRank("Lamp kitchen", "lamp")).toBe(0);
    expect(prefixRank("Kitchen lamp", "LAMP")).toBe(1);
    expect(prefixRank("bed_lamp", "lamp")).toBe(1);
    expect(prefixRank("Floodlamp", "lamp")).toBe(2);
  });
  it("ranks the values a field suggests, ignoring case, spaces, dashes and underscores", () => {
    const commands = ["MEDIA_VOLUME", "VOLUME_UP", "volume down", "POWER"];
    expect(rankedValues(commands, "vol")).toEqual(["MEDIA_VOLUME", "VOLUME_UP", "volume down"]);
    expect(rankedValues(commands, "volumeup")).toEqual(["VOLUME_UP"]);
    expect(rankedValues(commands, "dia")).toEqual(["MEDIA_VOLUME"]);
    expect(rankedValues(commands, "")).toEqual(commands);
  });
});

describe("the icon search (the icon picker and Alerts)", () => {
  const groups = [{ label: "Lights", icons: [{ name: "ceiling-light", label: "Ceiling light" }, { name: "alarm-light", label: "Warning light" }] },
    { label: "Doors", icons: [{ name: "doorbell", label: "Doorbell" }] }];
  it("finds an icon by its label, its name with or without its dashes, and its group, and drops a group left empty", () => {
    expect(iconGroupsMatching(groups, "alarm-light").map((g) => g.icons.map((i) => i.name))).toEqual([["alarm-light"]]);
    expect(iconGroupsMatching(groups, "alarm light").map((g) => g.icons.map((i) => i.name))).toEqual([["alarm-light"]]);
    expect(iconGroupsMatching(groups, "warning").map((g) => g.label)).toEqual(["Lights"]);
    expect(iconGroupsMatching(groups, "doors").map((g) => g.icons.length)).toEqual([1]);
    expect(iconGroupsMatching(groups, "").map((g) => g.icons.length)).toEqual([2, 1]);
    expect(iconGroupsMatching(groups, "nothing")).toEqual([]);
  });
});
