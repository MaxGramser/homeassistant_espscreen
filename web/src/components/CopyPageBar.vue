<script setup lang="ts">
// Copy one page's top bar onto others: its items only, or the whole bar with its title and Home key.
import { computed, ref, watch } from 'vue';
import { t } from '../i18n';
import { titleOf } from '../model/pages';
import { copyPageBars, state } from '../store';
import CheckRow from './ui/CheckRow.vue';
import Icon from './ui/Icon.vue';
import Section from './ui/Section.vue';
import UiSelect from './ui/UiSelect.vue';
const props = defineProps<{ pageId: string }>();
const source = ref(props.pageId), targets = ref<string[]>([]), whole = ref('items');
watch(() => props.pageId, (id) => { source.value = id; targets.value = []; });
watch(source, (id) => { targets.value = id === props.pageId ? [] : [props.pageId]; });
const pages = computed(() => state.document!.pages.map((page, index) => [page.id, `${index + 1} · ${titleOf(state.document!, page)}`] as [string, string]));
const toggle = (id: string) => { targets.value = targets.value.includes(id) ? targets.value.filter((item) => item !== id) : [...targets.value, id]; };
function copy() { if (copyPageBars(source.value, targets.value, whole.value === 'whole')) targets.value = []; }
</script>
<template>
  <Section class="copy-bar" foldable :title="t('editor.pages.copy_bar')" icon="content-copy">
    <div class="f"><label class="f-label" for="copy-bar-from">{{ t('editor.pages.copy_from') }}</label>
      <UiSelect id="copy-bar-from" v-model="source" :options="pages" />
    </div>
    <div class="f"><label class="f-label" for="copy-bar-content">{{ t('editor.pages.copy_content') }}</label>
      <UiSelect id="copy-bar-content" v-model="whole" :options="[['items', t('editor.pages.copy_items')], ['whole', t('editor.pages.copy_whole')]]" />
    </div>
    <div class="f"><span class="f-label">{{ t('editor.pages.copy_to') }}</span>
      <div class="check-list">
        <CheckRow v-for="[id, text] in pages.filter(([id]) => id !== source)" :key="id" class="copy-target" :checked="targets.includes(id)" @toggle="toggle(id)">{{ text }}</CheckRow>
      </div>
    </div>
    <button class="btn primary" type="button" :disabled="!targets.length" @click="copy"><Icon name="content-copy" />{{ t('editor.pages.copy_apply') }}</button>
  </Section>
</template>
