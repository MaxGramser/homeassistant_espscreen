<script setup lang="ts">
// The template tile's code field (docs/TEXT_TILE.md, "Writing a template"): Home Assistant's Jinja with the tile's own
// markup, in CodeMirror, as Home Assistant's own template editor uses it.
//
// While you type it completes what fits where the cursor stands (model/template-complete.ts): an entity id with its name
// and its state now, an entity's real attributes with their values and the states it may take (api/text/entity, asked
// once per entity), Home Assistant's functions and filters, the tags, and outside the braces the tile's markup. A
// function, a tag or the table comes as a snippet: its fields are selected one after the other with Tab.
// Beside the code it shows what the template reads: the value of a states() or state_attr() after the call, and whether
// an is_state() holds now (as an IDE shows inlay hints). An entity id Home Assistant does not have is underlined, with
// the one it most likely meant to put in its place, and the line Home Assistant's error names is marked.
// Pointing at an entity id shows what it is and its state.
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { EditorState, RangeSetBuilder, StateEffect } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, hoverTooltip, keymap, placeholder as hint, tooltips, ViewPlugin, type ViewUpdate,
  WidgetType } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap, snippet, startCompletion,
  type Completion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { bracketMatching, HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { forceLinting, linter, type Diagnostic } from "@codemirror/lint";
import { jinja2 } from "@codemirror/legacy-modes/mode/jinja2";
import { tags } from "@lezer/highlight";
import { send } from "../../api";
import { t } from "../../i18n";
import { closer, closest, contextAt, errorLine, FILTERS, FUNCTIONS, markup, MEMBERS, quotedIds, refsOf, shown, statesOf, TAGS,
  type Item } from "../../model/template-complete";
import { useEntitiesStore } from "../../stores/entities";
import { useInventoryStore } from "../../stores/inventory";

const props = defineProps<{ modelValue: string; label: string; error?: string | null }>();
const emit = defineEmits<{ "update:modelValue": [value: string]; focus: []; blur: [] }>();
const inv = useInventoryStore();
const entities = useEntitiesStore();
const host = ref<HTMLDivElement | null>(null);
let view: EditorView | null = null;

// ---- What Home Assistant knows of one entity, asked once while the editor is open. An answer redraws the values.
type Facts = { state: string; attributes: Record<string, string>; states: string[] };
const facts = new Map<string, Promise<Facts | null>>();
const answered = new Map<string, Facts | null>();
const factsArrived = StateEffect.define<null>();
function factsOf(entity: string) {
  if (!facts.has(entity))
    facts.set(entity, send<Facts>(`text/entity?entity=${encodeURIComponent(entity)}`, "GET").catch(() => null).then((f) => {
      answered.set(entity, f);
      view?.dispatch({ effects: factsArrived.of(null) });
      return f;
    }));
  return facts.get(entity)!;
}
const known = () => inv.inventory.entities || [];
const knownIds = () => new Set(known().map((e) => e.id));
const stateNow = (id: string) => answered.get(id)?.state ?? entities.liveOf(id)?.state ?? "";

// ---- Completions: snippets whose fields Tab walks through.
function applied(item: Item): Completion["apply"] {
  return (v, completion, from, to) => {
    // A tag brings its own %}: the one that closes the braces already (`{% | %}`) goes in its place.
    const closing = item.kind === "keyword" ? /^\s*-?%\}/.exec(v.state.sliceDoc(to, to + 8)) : null;
    snippet(item.apply)(v, completion, from, closing ? to + closing[0].length : to);
    // A function that takes an entity opens the entity list in its first field at once.
    if (item.apply.includes("('${entity_id}")) setTimeout(() => startCompletion(v), 0);
  };
}
const kindOf: Record<Item["kind"], string> = { function: "function", filter: "method", keyword: "keyword", markup: "text", variable: "variable" };
const asCompletion = (item: Item): Completion => ({
  label: item.label, detail: item.detail, info: item.info, boost: item.boost, type: kindOf[item.kind], apply: applied(item),
});
const words = () => ({
  heading: t("editor.tile.text.markup.heading"), bullet: t("editor.tile.text.markup.bullet"), table: t("editor.tile.text.markup.table"),
  bold: t("editor.tile.text.markup.bold"), good: t("editor.tile.text.markup.good"), alert: t("editor.tile.text.markup.alert"),
  accent: t("editor.tile.text.markup.accent"),
});

async function complete(ctx: CompletionContext): Promise<CompletionResult | null> {
  const before = ctx.state.sliceDoc(0, ctx.pos);
  const after = ctx.state.sliceDoc(ctx.pos, ctx.pos + 2);
  const c = contextAt(before);
  const typed = before.slice("from" in c ? c.from : ctx.pos);
  switch (c.kind) {
    case "entity":
      return {
        from: c.from, validFor: /^[\w.]*$/,
        options: known().map((e) => ({
          label: e.id, detail: [e.name, stateNow(e.id)].filter(Boolean).join(" · "), info: [e.area, e.device].filter(Boolean).join(" · ") || undefined,
          type: "variable", apply: e.id + closer(c.quote, after),
        })),
      };
    case "attribute": {
      const f = await factsOf(c.entity);
      if (!f) return null;
      return { from: c.from, validFor: /^\w*$/,
        options: Object.entries(f.attributes).map(([key, value]) => ({ label: key, detail: shown(value), info: value.length > 28 ? value : undefined,
          type: "property", apply: key + closer(c.quote, after) })) };
    }
    case "state": {
      const f = await factsOf(c.entity);
      return { from: c.from, validFor: /^[^'"]*$/,
        options: statesOf(c.entity, f?.state ?? stateNow(c.entity), f?.states).map((value, i) => ({
          // The state it has now first; unavailable and unknown last: they are rarely what a template asks for.
          label: value, type: "enum", boost: i === 0 ? 2 : value === "unavailable" || value === "unknown" ? -2 : 0, detail: i === 0 ? t("editor.tile.text.complete.now") : undefined,
          apply: value + closer(c.quote, after) })) };
    }
    case "domain":
      return { from: c.from, validFor: /^\w*$/,
        options: [...new Set(known().map((e) => e.id.split(".")[0]))].map((domain) => ({ label: domain, type: "namespace", apply: `${domain}.` })) };
    case "object":
      return { from: c.from, validFor: /^\w*$/,
        options: known().filter((e) => e.id.startsWith(`${c.domain}.`)).map((e) => ({
          label: e.id.slice(c.domain.length + 1), detail: [e.name, stateNow(e.id)].filter(Boolean).join(" · "), type: "variable" })) };
    case "member":
      return { from: c.from, validFor: /^\w*$/, options: MEMBERS.map(asCompletion) };
    case "filter":
      return { from: c.from, validFor: /^\w*$/, options: FILTERS.map(asCompletion) };
    case "tag":
      return { from: c.from, validFor: /^\w*$/, options: TAGS.map(asCompletion) };
    case "function":
      if (!typed && !ctx.explicit) return null;
      return { from: c.from, validFor: /^\w*$/, options: FUNCTIONS.map(asCompletion) };
    case "markup":
      if (!typed && !ctx.explicit) return null;
      return { from: c.from, options: markup(words()).map(asCompletion) };
    default:
      return null;
  }
}

// ---- The values beside the code: what states() and state_attr() give now, and whether is_state() holds.
class ValueHint extends WidgetType {
  constructor(readonly text: string, readonly tone: "value" | "yes" | "no") { super(); }
  eq(other: ValueHint) { return other.text === this.text && other.tone === this.tone; }
  toDOM() {
    const span = document.createElement("span");
    span.className = `tpl-value tpl-${this.tone}`;
    span.textContent = this.text;
    return span;
  }
  ignoreEvent() { return true; }
}
function valuesOf(v: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  const ids = knownIds();
  for (const ref of refsOf(v.state.doc.toString())) {
    if (!ids.has(ref.entity)) continue;
    const f = answered.get(ref.entity);
    if (f === undefined) { void factsOf(ref.entity); continue; }
    const holds = ref.kind === "is" && stateNow(ref.entity) === ref.value;
    const tone = ref.kind !== "is" ? "value" : holds ? "yes" : "no";
    const hintText = ref.kind === "state" ? shown(f?.state ?? stateNow(ref.entity), f?.attributes.unit_of_measurement)
      : ref.kind === "attr" ? (f && ref.attribute! in f.attributes ? shown(f.attributes[ref.attribute!]) : "—")
      : holds ? "✓" : `✗ ${shown(stateNow(ref.entity))}`;
    builder.add(ref.end, ref.end, Decoration.widget({ widget: new ValueHint(hintText, tone), side: 1 }));
  }
  return builder.finish();
}
const values = ViewPlugin.fromClass(class {
  decorations: DecorationSet;
  constructor(v: EditorView) { this.decorations = valuesOf(v); }
  update(u: ViewUpdate) {
    if (u.docChanged || u.transactions.some((tr) => tr.effects.some((e) => e.is(factsArrived)))) this.decorations = valuesOf(u.view);
  }
}, { decorations: (plugin) => plugin.decorations });

// ---- What looks wrong: an entity Home Assistant does not have (with the one it likely meant), and the line of its error.
let haError: string | null = null;
const problems = linter((v) => {
  const out: Diagnostic[] = [];
  const ids = known().map((e) => e.id), have = new Set(ids);
  if (ids.length) for (const q of quotedIds(v.state.doc.toString())) {
    if (have.has(q.id)) continue;
    const meant = closest(q.id, ids);
    out.push({ from: q.from, to: q.to, severity: "warning", message: t("editor.tile.text.lint.unknown", { id: q.id }),
      actions: meant ? [{ name: t("editor.tile.text.lint.replace", { id: meant }), apply: (w, from, to) => w.dispatch({ changes: { from, to, insert: meant } }) }] : [] });
  }
  const line = errorLine(haError);
  if (haError && line && line <= v.state.doc.lines) {
    const at = v.state.doc.line(line);
    out.push({ from: at.from, to: at.to, severity: "error", message: haError });
  }
  return out;
}, { delay: 350 });

// Pointing at an entity id: its name, where it is, and its state now.
const pointed = hoverTooltip((v, pos) => {
  const line = v.state.doc.lineAt(pos);
  const text = line.text, at = pos - line.from;
  const re = /[a-z_]+\.[a-z0-9_]+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (at < m.index || at > m.index + m[0].length) continue;
    const entity = known().find((e) => e.id === m![0]);
    if (!entity) return null;
    const start = line.from + m.index;
    return { pos: start, end: start + m[0].length, above: true, create: () => {
      const dom = document.createElement("div");
      dom.className = "tpl-tip";
      const name = document.createElement("strong");
      name.textContent = entity.name || entity.id;
      const more = document.createElement("span");
      more.textContent = [stateNow(entity.id) && t("editor.tile.text.complete.state", { state: stateNow(entity.id) }), entity.area].filter(Boolean).join(" · ");
      dom.append(name, more);
      return { dom };
    } };
  }
  return null;
});

// `{` closes itself with `}` (closeBrackets); a `%` typed between them makes the tag Jinja wants, `{% | %}`, where `{{`
// already gave `{{ | }}`.
const tagBraces = EditorView.inputHandler.of((v, from, to, text) => {
  if (text !== "%" || from !== to || v.state.sliceDoc(from - 1, from) !== "{" || v.state.sliceDoc(from, from + 1) !== "}") return false;
  v.dispatch({ changes: { from, to: from + 1, insert: "%  %}" }, selection: { anchor: from + 2 }, userEvent: "input.type" });
  return true;
});

// Home Assistant's Jinja has no line statements: `#` at the start of a line is text, the tile's heading, never the
// legacy mode's `##` line comment; ⌘/ (Ctrl+/) comments a line out as {# … #}, the one comment Home Assistant reads.
type JinjaState = { intag?: boolean; incomment?: boolean };
const tileJinja = StreamLanguage.define<JinjaState>({
  ...(jinja2 as unknown as Parameters<typeof StreamLanguage.define<JinjaState>>[0]),
  token(stream, state) {
    if (stream.sol() && !state.intag && !state.incomment && stream.match(/^\s*#{1,3}(?=\s)/)) return "heading";
    return (jinja2 as unknown as { token: (s: typeof stream, st: JinjaState) => string | null }).token(stream, state);
  },
  languageData: { commentTokens: { block: { open: "{#", close: "#}" } } },
});

const look = HighlightStyle.define([
  { tag: tags.heading, color: "var(--ink)", fontWeight: "700" },
  { tag: [tags.keyword, tags.controlKeyword], color: "var(--accent)", fontWeight: "600" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--good)" },
  { tag: [tags.number, tags.bool, tags.atom], color: "var(--warn)" },
  { tag: [tags.variableName, tags.propertyName], color: "var(--ink)" },
  { tag: [tags.comment], color: "var(--muted)", fontStyle: "italic" },
  { tag: [tags.bracket, tags.operator, tags.punctuation], color: "var(--muted)" },
  { tag: tags.tagName, color: "var(--accent)" },
]);
const theme = EditorView.theme({
  "&": { fontSize: "13px", background: "var(--code-bg)", color: "var(--ink)", border: "1px solid var(--line)", borderRadius: "8px" },
  "&.cm-focused": { outline: "2px solid var(--focus)", outlineOffset: "1px" },
  ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.6", minHeight: "9.5em", maxHeight: "26em" },
  ".cm-content": { padding: "8px 0", caretColor: "var(--ink)" },
  ".cm-line": { padding: "0 10px" },
  ".cm-placeholder": { color: "var(--muted)" },
  ".cm-tooltip": { background: "var(--surface)", color: "var(--ink)", border: "1px solid var(--line)", borderRadius: "8px", boxShadow: "var(--pop-shadow)" },
  ".cm-tooltip-autocomplete ul li[aria-selected]": { background: "var(--accent-soft)", color: "var(--ink)" },
  // A list as wide as the panel allows, a long value cut with an ellipsis (its whole text in the info beside it).
  ".cm-tooltip.cm-tooltip-autocomplete > ul": { maxWidth: "min(30em, 92vw)" },
  ".cm-tooltip-autocomplete ul li": { overflow: "hidden", textOverflow: "ellipsis" },
  ".cm-completionDetail": { color: "var(--muted)", fontStyle: "normal", marginLeft: "0.8em" },
  ".cm-completionInfo": { maxWidth: "18em", fontFamily: "var(--mono)", fontSize: "12px", padding: "6px 8px" },
  ".cm-snippetField": { background: "var(--accent-soft)", borderRadius: "3px" },
  ".tpl-tip": { display: "grid", gap: "2px", padding: "6px 8px", fontFamily: "var(--ui-font)", fontSize: "12px" },
  ".tpl-tip span": { color: "var(--muted)" },
  ".tpl-value": { marginLeft: "6px", padding: "0 5px", borderRadius: "4px", fontFamily: "var(--ui-font)", fontSize: "11px",
    background: "var(--surface-2)", color: "var(--muted)", border: "1px solid var(--line)", whiteSpace: "nowrap" },
  ".tpl-yes": { color: "var(--good)" },
  ".tpl-no": { color: "var(--muted)" },
  ".cm-lintRange-warning": { backgroundImage: "none", textDecoration: "underline wavy var(--warn)", textUnderlineOffset: "3px" },
  ".cm-lintRange-error": { backgroundImage: "none", textDecoration: "underline wavy var(--danger)", textUnderlineOffset: "3px" },
  ".cm-diagnostic": { fontFamily: "var(--ui-font)", fontSize: "12px", padding: "6px 8px", borderLeftWidth: "3px" },
  ".cm-diagnosticAction": { background: "var(--accent)", color: "var(--accent-ink)", borderRadius: "6px", padding: "2px 8px", marginLeft: "0", marginTop: "6px", display: "block" },
  "&.tpl-error": { borderColor: "var(--danger)" },
});

onMounted(() => {
  // In a shadow root of its own: CodeMirror then puts its styles in adopted style sheets, which the add-on's Content
  // Security Policy (style-src 'self', server.py) allows; on the page itself it would write a <style> element, which the
  // policy refuses, and the field and its completion list would lose their look.
  const shadow = host.value!.attachShadow({ mode: "open" });
  const parent = document.createElement("div");
  shadow.append(parent);
  haError = props.error ?? null;
  view = new EditorView({
    parent,
    root: shadow,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        history(), closeBrackets(), tagBraces, bracketMatching(), tileJinja, syntaxHighlighting(look), theme,
        autocompletion({ override: [complete], activateOnTyping: true, icons: false }), pointed, values, problems,
        // Tooltips keep inside the inspector they stand in, which cuts off what leaves it.
        tooltips({ tooltipSpace: () => (host.value?.closest(".drawer") ?? document.documentElement).getBoundingClientRect() }),
        hint(t("editor.tile.text.placeholder")), EditorView.lineWrapping,
        EditorView.contentAttributes.of({ "aria-label": props.label, spellcheck: "false" }),
        keymap.of([...closeBracketsKeymap, ...completionKeymap, ...historyKeymap, indentWithTab, ...defaultKeymap]),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) emit("update:modelValue", u.state.doc.toString());
          if (u.focusChanged) { if (u.view.hasFocus) emit("focus"); else emit("blur"); }
        }),
      ],
    }),
  });
  if (props.error) view.dom.classList.add("tpl-error");
});
// Another tile, or undo outside the field: the field takes the text it is given, keeping the cursor where it can.
watch(() => props.modelValue, (text) => {
  if (!view || text === view.state.doc.toString()) return;
  const anchor = Math.min(view.state.selection.main.anchor, text.length);
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text }, selection: { anchor } });
});
watch(() => props.error, (error) => {
  haError = error ?? null;
  view?.dom.classList.toggle("tpl-error", Boolean(error));
  if (view) forceLinting(view);
});
/** Puts a snippet in at the cursor (the markup keys under the field): its fields are selected with Tab, as a completion's. */
function insert(text: string) {
  if (!view) return;
  const { from, to } = view.state.selection.main;
  const line = view.state.doc.lineAt(from);
  // A heading, a bullet or a table starts a line of its own.
  const lead = /^[#\-|]/.test(text) && from > line.from && line.text.trim() ? "\n" : "";
  snippet(lead + text)(view, null, from, to);
  view.focus();
}
defineExpose({ insert });
onBeforeUnmount(() => { view?.destroy(); view = null; });
</script>

<template>
  <div ref="host" class="template-editor" />
</template>

<style scoped>
.template-editor { min-width: 0; }
</style>
