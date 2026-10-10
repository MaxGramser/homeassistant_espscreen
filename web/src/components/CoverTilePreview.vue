<script setup lang="ts">
// This preview never sends HA actions. Native cover sliders own interaction.
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { deviceStyle, isCompact, screenShape, screenText, state } from '../store';
import { glyph } from '../model/topbar';
import { tallKeys } from '../model/ui-scale';
import { controlKeys, coverTiltKeys, coverTiltKind } from '../model/tall-controls';
const props = defineProps<{ primary: string; entityState: string; attributes: Record<string, any> }>();
const root = ref<HTMLElement>();
const width = ref(0), height = ref(0);
let observer: ResizeObserver | undefined;
watch(root, element => {
  observer?.disconnect();
  if (!element) return;
  observer = new ResizeObserver(([entry]) => { width.value = entry!.contentRect.width; height.value = entry!.contentRect.height; });
  observer.observe(element);
});
onBeforeUnmount(() => observer?.disconnect());
const scale = computed(() => parseFloat(deviceStyle.value['--mockup-width']) / screenShape.value.width);
// The keys and their gap as the glass draws them (ui-scale tallKeys), in the mockup's pixels.
const keys = computed(() => tallKeys({ ...screenShape.value, look: isCompact.value ? 'compact' : 'standard' }));
const touch = computed(() => keys.value.touch * scale.value);
const gap = computed(() => keys.value.gap * scale.value);
const mainKeys = computed(() => controlKeys('cover', props.primary, props.entityState, props.attributes));
const tilt = computed(() => coverTiltKind(props.entityState, props.attributes));
const tiltKeys = computed(() => tilt.value === 'buttons' ? coverTiltKeys(props.attributes) : []);
const groups = computed(() => [
  ...(props.primary ? [{ kind: props.primary, keys: mainKeys.value, tilt: false, value: props.attributes.current_position, label: screenText('screen.cover.position') }] : []),
  ...(tilt.value ? [{ kind: tilt.value, keys: tiltKeys.value, tilt: true, value: props.attributes.current_tilt_position, label: screenText('screen.cover.tilt') }] : []),
]);
const labelHeight = computed(() => parseFloat(root.value ? getComputedStyle(root.value).fontSize : '12') * 1.3);
const controlHeight = computed(() => height.value - labelHeight.value - gap.value);
const horizontal = (count: number) => controlHeight.value < count * touch.value + (count - 1) * gap.value;
const groupWidth = (g: typeof groups.value[number]) => g.kind !== 'position' && horizontal(g.keys.length) ? g.keys.length * touch.value + (g.keys.length - 1) * gap.value : Math.min((width.value - (groups.value.length - 1) * 2 * gap.value) / groups.value.length, 2 * touch.value);
const fits = computed(() => {
  const count = groups.value.length;
  return !!tilt.value && count > 0 && controlHeight.value >= touch.value
    && width.value >= groups.value.reduce((sum, g) => sum + groupWidth(g), 0) + (count - 1) * 2 * gap.value
    && groups.value.every(g => groupWidth(g) >= touch.value && (g.kind !== 'position' || controlHeight.value >= 2 * touch.value));
});
const icon = (name: string) => glyph(state.inventory.icons?.controls?.[name] || '');
const percent = (value: unknown) => typeof value === 'number' ? `${Math.round(value)}%` : '—';
</script>
<template>
  <span ref="root" class="cover-preview" :style="{ '--cover-touch': `${touch}px`, '--cover-gap': `${gap}px` }">
    <template v-if="fits">
      <span v-for="g in groups" :key="g.tilt ? 'tilt' : 'position'" class="cover-group" :style="{ width: `${groupWidth(g)}px` }">
        <span class="cover-control">
          <span v-if="g.kind === 'position'" class="cover-track" :class="{ slats: g.tilt }" :style="{ '--position': `${g.value ?? 50}%` }">
            <span v-if="!g.tilt" class="cover-fill"></span><i></i>
          </span>
          <span v-else class="cover-keys" :class="{ horizontal: horizontal(g.keys.length) }"><span v-for="k in g.keys" :key="k.icon" class="cover-key mdi" :class="{ disabled: k.disabled }">{{ icon(k.icon) }}</span></span>
        </span>
        <span class="cover-caption" :title="g.label + ': ' + percent(g.value)">{{ g.label }}</span>
      </span>
    </template>
    <span v-else class="cover-fallback">
      <span v-if="primary === 'position'" class="cover-range" :style="{ '--position': `${100 - (attributes.current_position ?? 50)}%` }"></span>
      <span v-else-if="mainKeys.length" class="cover-row"><span v-for="k in mainKeys" :key="k.icon" class="cover-key mdi" :class="{ disabled: k.disabled }">{{ icon(k.icon) }}</span></span>
    </span>
  </span>
</template>
<style scoped>
.cover-preview { flex: 1; min-height: 0; display: flex; justify-content: center; gap: calc(2 * var(--cover-gap)); padding-top: var(--cover-gap); position: relative; font-size: 10px; }
.cover-group { width: calc(2 * var(--cover-touch)); min-width: var(--cover-touch); display: flex; flex-direction: column; gap: var(--cover-gap); }
.cover-control { flex: 1; min-height: 0; display: flex; justify-content: center; align-items: center; }
.cover-track { height: 100%; width: 100%; border-radius: 12px; background: var(--tile-circle); position: relative; overflow: hidden; }
.cover-fill { position: absolute; inset: 0 0 var(--position); background: var(--tile-accent); }
.cover-track i { position: absolute; left: 30%; width: 40%; height: 3px; border-radius: 3px; background: white; bottom: clamp(6px, var(--position), calc(100% - 9px)); }
.cover-track.slats { background: repeating-linear-gradient(to bottom, var(--tile-circle) 0 4%, var(--tile-accent) 5% 7%, var(--tile-circle) 8% 10%); }
.cover-track.slats i { left: 20%; width: 60%; height: 5px; background: var(--tile-accent); box-shadow: 0 0 0 2px var(--tile-circle); }
.cover-keys { display: flex; flex-direction: column; gap: var(--cover-gap); }
.cover-keys.horizontal { flex-direction: row; }
.cover-key { width: var(--cover-touch); height: var(--cover-touch); border-radius: 50%; display: grid; place-items: center; font-size: calc(var(--cover-touch) * .6); background: var(--tile-circle); color: var(--tile-accent); flex: none; }
.cover-key.disabled { opacity: .35; }
.cover-caption { line-height: 1.3; text-align: center; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; color: var(--muted); }
.cover-fallback { display: flex; align-items: end; justify-content: center; width: 100%; }
.cover-row { display: flex; gap: var(--cover-gap); }
.cover-range { height: var(--cover-touch); width: 100%; border-radius: 10px; background: linear-gradient(to right, var(--tile-accent) var(--position), var(--tile-circle) var(--position)); }
</style>
