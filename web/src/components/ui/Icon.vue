<script setup lang="ts">
// One of the editor's own icons, as text in the icon font so it takes the colour and size of what it sits in.
import { iconGlyph, type IconName } from "../../model/ui-icons";
defineProps<{ name: IconName }>();
</script>

<template><span class="mdi ui-icon" aria-hidden="true">{{ iconGlyph(name) }}</span></template>
