// Whether a key went to a field that takes text (an input, a text area, something editable): there the key is the
// field's, not a shortcut of the page (typing to search the library, Delete for the selected tile, ⌘Z for the draft).
export function isEditableTarget(target: EventTarget | null | undefined) {
  return Boolean((target as Element | null)?.closest?.("input, textarea, [contenteditable]"));
}
