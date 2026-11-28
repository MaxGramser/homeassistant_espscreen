// Whether a key went to a field that takes text (an input, a text area, something editable): there the key is the
// field's, not a shortcut of the page (typing to search the library, Delete for the selected tile, ⌘Z for the draft).
const FIELD = "input, textarea, [contenteditable]";
export function isEditableTarget(target: EventTarget | null | undefined) {
  const element = target as Element | null;
  if (element?.closest?.(FIELD)) return true;
  // A field inside a shadow root (the template tile's code field, TemplateEditor.vue): its key events reach the page
  // with the shadow root's host as their target, so the focused element inside it decides.
  const inner = (element as HTMLElement | null)?.shadowRoot?.activeElement;
  return Boolean(inner?.closest?.(FIELD));
}
