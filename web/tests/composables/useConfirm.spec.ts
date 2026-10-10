// The editor's own questions (composables/useConfirm.ts) and the dialog that asks them (ConfirmDialog): the words they
// always had, one question at a time, Cancel in focus at first, Escape cancelling, a field for a name, a text to copy.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { nextTick } from "vue";
import ConfirmDialog from "../../src/components/ConfirmDialog.vue";
import { answer, askConfirm, askText, question, showText } from "../../src/composables/useConfirm";
import { resetAll } from "../../src/resets";
import { answerDialogs } from "../helpers/dialogs";

const dialog = () => document.querySelector<HTMLElement>("[role='alertdialog']");
const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("[role='alertdialog'] button")].find((b) => b.textContent?.trim() === text)!;
async function settle() { await flushPromises(); await nextTick(); await nextTick(); }

describe("the editor's questions", () => {
  it("are asked one at a time, in the order asked, each answer settling its own", async () => {
    const first = askConfirm("Replace the layout?"), second = askText("Name in this app", "Hall");
    expect(question.value).toEqual({ kind: "confirm", message: "Replace the layout?" });
    answer(true);
    expect(question.value).toEqual({ kind: "prompt", message: "Name in this app", value: "Hall" });
    answer("Living room");
    expect([await first, await second, question.value]).toEqual([true, "Living room", null]);
  });
  it("cancel a prompt with null, and are cancelled when the page starts over", async () => {
    const name = askText("Name in this app", "Hall");
    answer(false);
    expect(await name).toBeNull();
    const open = askConfirm("Start the calibration?");
    resetAll();
    expect(await open).toBe(false);
  });
  it("are answered by a test as a person would", async () => {
    const asked = answerDialogs((now) => (now.kind === "prompt" ? "Kitchen" : false));
    expect([await askConfirm("Clear the local override?"), await askText("Name in this app")]).toEqual([false, "Kitchen"]);
    expect(asked.map((now) => now.message)).toEqual(["Clear the local override?", "Name in this app"]);
  });
});

describe("the dialog that asks them", () => {
  it("shows the question in the editor's look, with Cancel in focus, and says yes with OK", async () => {
    mount(ConfirmDialog, { attachTo: document.body });
    const asking = askConfirm("You have unsaved changes. Open a different screen anyway?");
    await settle();
    expect(dialog()?.textContent).toContain("You have unsaved changes. Open a different screen anyway?");
    expect(document.activeElement?.textContent?.trim()).toBe("Cancel");
    button("OK").click();
    expect(await asking).toBe(true);
    await settle();
    expect(dialog()).toBeNull();
  });
  it("cancels with Cancel and with Escape", async () => {
    mount(ConfirmDialog, { attachTo: document.body });
    const first = askConfirm("Clear the local override?");
    await settle();
    button("Cancel").click();
    expect(await first).toBe(false);
    const second = askConfirm("Clear the local override?");
    await settle();
    dialog()!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(await second).toBe(false);
  });
  it("asks for a name in a field that has the focus, and takes it with Enter", async () => {
    mount(ConfirmDialog, { attachTo: document.body });
    const name = askText("Name in this app", "Hall");
    await settle();
    const field = document.querySelector<HTMLInputElement>("[role='alertdialog'] input")!;
    expect([field.value, document.activeElement === field]).toEqual(["Hall", true]);
    field.value = "Living room";
    field.dispatchEvent(new Event("input"));
    field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(await name).toBe("Living room");
  });
  it("shows a text to copy by hand, selected, with OK alone", async () => {
    mount(ConfirmDialog, { attachTo: document.body });
    const shown = showText("API key is selected. Copy with Ctrl+C or Command+C.", "the-key");
    await settle();
    const field = document.querySelector<HTMLInputElement>("[role='alertdialog'] input")!;
    expect([field.value, field.readOnly, field.selectionStart, field.selectionEnd]).toEqual(["the-key", true, 0, 7]);
    expect([...document.querySelectorAll("[role='alertdialog'] button")].map((b) => b.textContent?.trim())).toEqual(["OK"]);
    button("OK").click();
    expect(await shown).toBe(true);
  });
});
