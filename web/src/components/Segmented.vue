<script setup lang="ts">
// A choice of a few, all in sight: the chosen one is raised. `shapes` draws a size as the shape it takes on the grid
// (columns x rows), so Normal, Double-width and the rest read at a glance.
defineProps<{ choices: readonly (readonly [unknown, string])[]; value: unknown; disabled?: boolean; shapes?: Record<string, [number, number]> }>();
const emit = defineEmits<{ (e: "pick", value: any): void }>();
</script>

<template>
  <div class="seg wrap" role="group">
    <button v-for="[key, text] in choices" :key="String(key)" type="button" :disabled="disabled"
      :aria-pressed="String(key) === String(value) ? 'true' : 'false'" @click="emit('pick', key)">
      <i v-if="shapes?.[String(key)]" class="seg-shape" :class="{ whole: String(key) === 'full' }" aria-hidden="true"
        :style="{ width: `${4 + shapes[String(key)][0] * 6}px`, height: `${4 + shapes[String(key)][1] * 6}px` }"></i>{{ text }}
    </button>
  </div>
</template>
