// The pictures of a plugin's README (GitHub #450): the editor's img-src is 'self', so a picture is asked of the app,
// which fetches it from the plugin's own folder at its commit (plugins.readme_image).
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PluginReadme from "../src/components/PluginReadme.vue";
import { readmePicture } from "../src/model/readme-pictures";

const sha = "a".repeat(40);
const official = `https://github.com/MaxGramser/tessera-plugins/tree/${sha}/plugins/clock`;
const linked = "https://github.com/someone/tessera-clock";

describe("a README's pictures", () => {
  it("come through the app, named after the commit", () => {
    expect(readmePicture("docs/images/gold.png", official, "clock", sha)).toBe(`api/plugins/clock/readme/docs/images/gold.png?v=${sha}`);
    expect(readmePicture("./store.png", linked, "clock", sha)).toBe(`api/plugins/clock/readme/store.png?v=${sha}`);
    expect(readmePicture("docs/a b.png#top", linked, "clock", null)).toBe("api/plugins/clock/readme/docs/a%20b.png");
  });

  it("take a full address only of the plugin's own folder", () => {
    expect(readmePicture(`https://raw.githubusercontent.com/MaxGramser/tessera-plugins/${sha}/plugins/clock/docs/x.png`, official, "clock", sha))
      .toBe(`api/plugins/clock/readme/docs/x.png?v=${sha}`);
    expect(readmePicture("https://raw.githubusercontent.com/someone/tessera-clock/HEAD/docs/x.png", linked, "clock", sha))
      .toBe(`api/plugins/clock/readme/docs/x.png?v=${sha}`);
    for (const src of ["https://example.com/x.png", "//example.com/x.png", "data:image/png;base64,AAAA", "javascript:alert(1)",
      `https://raw.githubusercontent.com/MaxGramser/tessera-plugins/${sha}/plugins/bins/x.png`])
      expect(readmePicture(src, official, "clock", sha), src).toBe("");
  });

  it("never climb out of the folder", () => {
    for (const src of ["../bins/store.png", "docs/../../x.png", ".git/x.png", "/etc/x.png", "docs//x.png", ""])
      expect(readmePicture(src, official, "clock", sha), src).toBe("");
  });

  it("are drawn by the README with their words", () => {
    const readme = mount(PluginReadme, { props: { source: "![Gold flip cards](docs/gold.png)\n\n![away](https://example.com/x.png)",
      repo: linked, plugin: "clock", version: sha } });
    const pictures = readme.findAll("img");
    expect(pictures).toHaveLength(1);
    expect(pictures[0].attributes("src")).toBe(`api/plugins/clock/readme/docs/gold.png?v=${sha}`);
    expect(pictures[0].attributes("alt")).toBe("Gold flip cards");
  });
});
