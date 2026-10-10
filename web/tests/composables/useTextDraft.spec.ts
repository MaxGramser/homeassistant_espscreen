// A text field that changes the draft as it is typed (composables/useTextDraft.ts): a tile's name, a title.
import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { useTextDraft } from "../../src/composables/useTextDraft";
import { inScope } from "../helpers/with-setup";

describe("a text draft", () => {
  it("keeps the person's spaces in the field and the trimmed text in the draft, and shows the draft on blur", () => {
    const saved = ref("Hall");
    const { result: field } = inScope(() => useTextDraft(saved, (value) => { saved.value = value; }));
    field.focus();
    field.input("Living room ");
    expect([field.value.value, saved.value]).toEqual(["Living room ", "Living room"]);
    field.blur();
    expect(field.value.value).toBe("Living room");
  });
  it("keeps a required field's last text while it is empty, and follows a change from elsewhere while not typed in", async () => {
    const saved = ref("Hall");
    const { result: field } = inScope(() => useTextDraft(saved, (value) => { saved.value = value; }, () => true));
    field.focus();
    field.input("  ");
    expect(saved.value).toBe("Hall");
    field.blur();
    expect(field.value.value).toBe("Hall");
    saved.value = "Kitchen";
    await nextTick();
    expect(field.value.value).toBe("Kitchen");
  });
});
