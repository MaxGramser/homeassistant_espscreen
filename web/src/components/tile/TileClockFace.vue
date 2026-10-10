<script setup lang="ts">
// The clock faces at the editor's one clock, as the screen draws them (model/clock.ts): the analog hands, the calm dial,
// the flip clock's two blocks ("07" "12" on 24 hours, "7" "12" with AM or PM on 12), wide or in one cell, and the digital
// time with its date.
import type { TileCardView } from "../../composables/useTileCard";
import { useRegionStore } from "../../stores/region";

const region = useRegionStore();
defineProps<{ card: TileCardView }>();
</script>

<template>
  <template v-if="card.face.kind === 'analog'">
    <svg class="clockface" viewBox="0 0 60 60" aria-hidden="true">
      <circle cx="30" cy="30" r="27" fill="#fff" stroke="#c9ccd1" />
      <line v-for="a in [0, 90, 180, 270]" :key="a" x1="30" y1="5" x2="30" y2="9" stroke="#1b1b1b" stroke-width="1.5" :transform="`rotate(${a} 30 30)`" />
      <line x1="30" y1="30" x2="30" y2="16" stroke="#1b1b1b" stroke-width="2.4" stroke-linecap="round" :transform="`rotate(${card.clock.hourAngle} 30 30)`" />
      <line x1="30" y1="30" x2="30" y2="11" stroke="#1b1b1b" stroke-width="1.6" stroke-linecap="round" :transform="`rotate(${card.clock.minuteAngle} 30 30)`" />
      <circle cx="30" cy="30" r="1.8" fill="#1b1b1b" />
    </svg>
    <span v-if="card.face.wide" class="lead"><span class="tx"><span class="nm">{{ card.texts.name }}</span><span class="st">{{ card.texts.note }}</span></span></span>
  </template>
  <span v-else-if="card.face.kind === 'dial'" class="face-clock" :class="{ upright: !card.face.wide || card.face.tall || card.face.full }">
    <svg class="calm-dial" viewBox="0 0 60 60" aria-hidden="true">
      <circle cx="30" cy="30" r="29" fill="#1b1b1b" />
      <line v-for="a in [0, 90, 180, 270]" :key="a" x1="30" y1="4" x2="30" y2="11" stroke="#fff" stroke-width="3" stroke-linecap="round" :transform="`rotate(${a} 30 30)`" />
      <circle v-for="a in [30, 60, 120, 150, 210, 240, 300, 330]" :key="a" cx="30" cy="6" r="1.6" fill="#9e9e9e" :transform="`rotate(${a} 30 30)`" />
      <line x1="30" y1="30" x2="30" y2="15" stroke="#fff" stroke-width="4.5" stroke-linecap="round" :transform="`rotate(${card.clock.hourAngle} 30 30)`" />
      <line x1="30" y1="30" x2="30" y2="8" stroke="#2196f3" stroke-width="3" stroke-linecap="round" :transform="`rotate(${card.clock.minuteAngle} 30 30)`" />
      <circle cx="30" cy="30" r="3.6" fill="#2196f3" />
    </svg>
    <span v-if="card.face.wide || card.face.tall || card.face.full" class="face-text"><span class="big">{{ card.clock.digits }}</span><span class="st">{{ card.clock.longDate }}</span></span>
  </span>
  <!-- The flip clock on a card two columns wide and two rows tall, or a whole page (firmware 0.17.0): the blocks share the
       width and the day ("Tuesday 29 Sep") and AM or PM stand on one line under them. -->
  <span v-else-if="card.face.kind === 'flip-wide'" class="flip-wide">
    <span class="blocks"><span class="block">{{ card.clock.hours }}</span><span class="block">{{ card.clock.minutes }}</span></span>
    <span class="under"><span>{{ card.clock.flipDate }}</span><span v-if="!region.clock24">{{ card.clock.amPm }}</span></span>
  </span>
  <span v-else-if="card.face.kind === 'flip'" class="face-clock flip">
    <span class="blocks"><span class="block">{{ card.clock.hours }}</span><span class="block">{{ card.clock.minutes }}</span><small v-if="!region.clock24">{{ card.clock.amPm }}</small></span>
    <span v-if="card.face.wide && !card.face.tall && !card.face.full" class="face-text"><span class="st">{{ card.clock.longDate }}</span></span>
  </span>
  <span v-else class="digital-clock"><span class="big">{{ card.clock.digits }}</span><span class="st">{{ card.clock.longDate }}</span></span>
</template>

<style scoped>
.face-clock { display: flex; align-items: center; gap: 10px; min-width: 0; width: 100%; height: 100%; padding-inline: 2px; }
.face-clock.upright { flex-direction: column; justify-content: center; gap: 4px; }
.face-clock .calm-dial { height: 100%; max-height: 100%; aspect-ratio: 1; flex: none; }
.face-clock.upright .calm-dial { height: auto; width: min(70%, 100%); max-height: 70%; }
.face-clock .face-text { display: grid; gap: 1px; min-width: 0; }
.face-clock.upright .face-text { text-align: center; }
.face-clock .face-text .big { font-size: 22px; font-weight: 500; }
.face-clock .face-text .st { font-size: 9px; }
.face-clock.flip { justify-content: center; }
.face-clock .blocks { display: flex; align-items: baseline; gap: 3px; }
.face-clock .block { background: #f1f1f1; border-radius: 4px; padding: 1px 5px; font-size: 24px; font-weight: 500; line-height: 1.25; background-image: linear-gradient(transparent calc(50% - .5px), #fff calc(50% - .5px), #fff calc(50% + .5px), transparent calc(50% + .5px)); }
.face-clock .blocks small { font-size: 9px; margin-left: 2px; }
.flip-wide { display: flex; flex-direction: column; justify-content: center; gap: 6px; width: 100%; height: 100%; min-width: 0; container-type: size; }
/* As the screen draws it: two blocks sharing the width, each about as tall as wide, the digits filling them. */
.flip-wide .blocks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 3%; height: min(calc(100cqh - 34px), 44cqw); }
.flip-wide .block { display: grid; place-items: center; background: #f1f1f1; border-radius: 8px; font-size: min(36cqw, calc((100cqh - 34px) * .78)); font-weight: 400; line-height: 1;
  background-image: linear-gradient(transparent calc(50% - .5px), #fff calc(50% - .5px), #fff calc(50% + .5px), transparent calc(50% + .5px)); }
.flip-wide .under { display: flex; justify-content: space-between; font-size: 10px; opacity: .7; }
.digital-clock { display: grid; gap: 3px; align-content: center; text-align: center; min-width: 0; width: 100%; height: 100%; }
.digital-clock .big { font-size: 28px; font-weight: 400; }
.digital-clock .st { font-size: 9px; }
</style>
