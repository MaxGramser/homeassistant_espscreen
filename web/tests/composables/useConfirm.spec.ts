// The editor's own questions (composables/useConfirm.ts) and the dialog that asks them (ConfirmDialog): the words they
// always had, the yes in words of its own and red where it throws something away, one question at a time, Cancel in
// focus at first, Escape cancelling, a field for a name, a text to copy.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { nextTick } from "vue";
import ConfirmDialog from "../../src/components/ConfirmDialog.vue";
import { answer, askConfirm, askText, cancelQuestions, question, showText } from "../../src/composables/useConfirm";
import { answerDialogs } from "../helpers/dialogs";

const dialog = () => document.querySelector<HTMLElement>("[role='alertdialog']");
const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("[role='alertdialog'] button")].find((b) => b.textContent?.trim() === text)!;
async function settle() { await flushPromises(); await nextTick(); await nextTick(); }

describe("the editor's questions", () => {
  it("are asked one at a time, in the order asked, each answer settling its own", async () => {
    const first = askConfirm("Replace the layout?", { confirm: "Replace layout", danger: true }), second = askText("Name in this app", "Hall", { confirm: "Rename" });
    expect(question.value).toEqual({ kind: "confirm", message: "Replace the layout?", confirm: "Replace layout", danger: true });
    answer(true);
    expect(question.value).toEqual({ kind: "prompt", message: "Name in this app", value: "Hall", confirm: "Rename" });
    answer("Living room");
    expect([await first, await second, question.value]).toEqual([true, "Living room", null]);
  });
  it("cancel a prompt with null, and are cancelled when the page starts over", async () => {
    const name = askText("Name in this app", "Hall", { confirm: "Rename" });
    answer(false);
    expect(await name).toBeNull();
    const open = askConfirm("Start the calibration?", { confirm: "Start calibration" });
    cancelQuestions();
    expect(await open).toBe(false);
  });
  it("are answered by a test as a person would", async () => {
    const asked = answerDialogs((now) => (now.kind === "prompt" ? "Kitchen" : false));
    expect([await askConfirm("Clear the local override?", { confirm: "Clear override", danger: true }), await askText("Name in this app", "", { confirm: "Rename" })]).toEqual([false, "Kitchen"]);
    expect(asked.map((now) => now.message)).toEqual(["Clear the local override?", "Name in this app"]);
  });
});

describe("the dialog that asks them", () => {
  it("shows the question in the editor's look, with Cancel in focus, and says yes in the words of what it does", async () => {
    mount(ConfirmDialog, { attachTo: document.body });
    const asking = askConfirm("You have unsaved changes. Open a different screen anyway?", { confirm: "Discard and open", danger: true });
    await settle();
    expect(dialog()?.textContent).toContain("You have unsaved changes. Open a different screen anyway?");
    // Cancel first, the yes after it: Enter alone throws nothing away, however red the yes is.
    expect([...dialog()!.querySelectorAll("button")].map((b) => b.textContent?.trim())).toEqual(["Cancel", "Discard and open"]);
    expect(document.activeElement?.textContent?.trim()).toBe("Cancel");
    expect(button("Discard and open").classList.contains("destructive")).toBe(true);
    button("Discard and open").click();
    expect(await asking).toBe(true);
    await settle();
    expect(dialog()).toBeNull();
  });
  it("draws a yes that throws nothing away as the page's own blue", async () => {
    mount(ConfirmDialog, { attachTo: document.body });
    const asking = askConfirm("Start the calibration on Hall?", { confirm: "Start calibration" });
    await settle();
    expect([button("Start calibration").classList.contains("primary"), button("Start calibration").classList.contains("destructive")]).toEqual([true, false]);
    expect(document.activeElement?.textContent?.trim()).toBe("Cancel");
    button("Start calibration").click();
    expect(await asking).toBe(true);
  });
  it("cancels with Cancel and with Escape", async () => {
    mount(ConfirmDialog, { attachTo: document.body });
    const first = askConfirm("Clear the local override?", { confirm: "Clear override", danger: true });
    await settle();
    button("Cancel").click();
    expect(await first).toBe(false);
    const second = askConfirm("Clear the local override?", { confirm: "Clear override", danger: true });
    await settle();
    dialog()!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(await second).toBe(false);
  });
  it("asks for a name in a field that has the focus, and takes it with Enter", async () => {
    mount(ConfirmDialog, { attachTo: document.body });
    const name = askText("Name in this app", "Hall", { confirm: "Rename" });
    await settle();
    const field = document.querySelector<HTMLInputElement>("[role='alertdialog'] input")!;
    expect([field.value, document.activeElement === field]).toEqual(["Hall", true]);
    expect(button("Rename").classList.contains("primary")).toBe(true);
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
