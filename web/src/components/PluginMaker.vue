<script setup lang="ts">
// Make a plugin of your own: the way from the template to everyone's Plugins page, in three steps under the list. A
// plugin stays in its maker's own repository (tessera-plugins docs/PUBLISHING.md): they test it here with a link, and
// list it once in the community list with a pull request that adds one file; after that their releases reach everyone.
import { t } from "../i18n";
import Icon from "./ui/Icon.vue";

defineProps<{ folder: string }>();
defineEmits<{ link: [] }>();

const REPO = "https://github.com/MaxGramser/tessera-plugins";
// GitHub's new-file page in community/, filled in with the four lines the list asks for: saving it opens the pull request.
const LISTING = "repo: https://github.com/<you>/<repository>\npath: .\nmaintainer: <you>\n";
const submit = `${REPO}/new/main/community?filename=${encodeURIComponent("<plugin-id>.yaml")}&value=${encodeURIComponent(LISTING)}`;
</script>

<template>
  <section class="plugin-maker" id="plugin-maker">
    <header class="pm-head">
      <span class="pm-mark" aria-hidden="true"><Icon name="puzzle-outline" /></span>
      <div class="pm-words">
        <h2>{{ t("editor.plugins.maker.title") }}</h2>
        <p>{{ t("editor.plugins.maker.lead") }}</p>
      </div>
      <a class="btn link pm-guide" :href="`${REPO}/blob/main/docs/MAKING_A_PLUGIN.md`" target="_blank" rel="noopener">{{ t("editor.plugins.maker.guide") }}<Icon name="arrow-right" /></a>
    </header>
    <ol class="pm-steps">
      <li>
        <span class="pm-step"><Icon name="code-braces" /></span>
        <b>{{ t("editor.plugins.maker.start.title") }}</b>
        <p>{{ t("editor.plugins.maker.start.text") }}</p>
        <a class="btn quiet" :href="`${REPO}/tree/main/template`" target="_blank" rel="noopener">{{ t("editor.plugins.maker.start.action") }}</a>
      </li>
      <li>
        <span class="pm-step"><Icon name="tablet-dashboard" /></span>
        <b>{{ t("editor.plugins.maker.test.title") }}</b>
        <p>{{ t("editor.plugins.maker.test.text") }}</p>
        <button type="button" class="btn quiet" @click="$emit('link')"><Icon name="link-variant" />{{ t("editor.plugins.add_link") }}</button>
        <small v-if="folder">{{ t("editor.plugins.maker.test.folder", { path: folder }) }}</small>
      </li>
      <li>
        <span class="pm-step"><Icon name="account-multiple-outline" /></span>
        <b>{{ t("editor.plugins.maker.share.title") }}</b>
        <p>{{ t("editor.plugins.maker.share.text") }}</p>
        <a class="btn quiet" :href="submit" target="_blank" rel="noopener">{{ t("editor.plugins.maker.share.action") }}</a>
      </li>
    </ol>
  </section>
</template>
