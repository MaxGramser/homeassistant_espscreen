<script setup lang="ts">
// A plugin's README, as the app shows it: markdown without HTML, so a plugin cannot put a script or a form on the page.
// Links open in a new tab; a picture shows only from the plugin's own folder, at the commit the screen is pinned to,
// through the app (model/readme-pictures.ts: the editor's img-src is 'self').
import MarkdownIt from "markdown-it";
import { computed } from "vue";
import { readmePicture } from "../model/readme-pictures";

const props = defineProps<{ source: string; repo: string; plugin: string; version?: string | null }>();

const md = new MarkdownIt({ html: false, linkify: true, typographer: false, breaks: false });
md.renderer.rules.image = (tokens, index) => {
  const url = readmePicture(tokens[index].attrGet("src") || "", props.repo, props.plugin, props.version);
  return url ? `<img src="${md.utils.escapeHtml(url)}" alt="${md.utils.escapeHtml(tokens[index].content)}" loading="lazy">` : "";
};
const linkOpen = md.renderer.rules.link_open || ((tokens, index, options, _env, self) => self.renderToken(tokens, index, options));
md.renderer.rules.link_open = (tokens, index, options, env, self) => {
  tokens[index].attrSet("target", "_blank");
  tokens[index].attrSet("rel", "noopener noreferrer");
  return linkOpen(tokens, index, options, env, self);
};
const html = computed(() => md.render(props.source));
</script>

<!-- markdown-it with html off escapes every tag in the source; what comes out is markdown's own elements only. -->
<!-- eslint-disable-next-line vue/no-v-html -->
<template><div class="pd-readme" v-html="html"></div></template>
