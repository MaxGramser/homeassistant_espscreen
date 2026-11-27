// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_level_bar.cpp -o /tmp/test_level_bar && /tmp/test_level_bar
// A level on a still glass (level_bar.h): where its keys and blocks lie, what a tap picks, and how a value and a count
// of blocks turn into each other.
#include "../components/smart_display/level_bar.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

using namespace level_bar;

static void the_blocks_of_a_range() {
  // Per mille and per cent are ten blocks; a fan of four speeds is four.
  assert(steps_for(0, 1000) == 10 && steps_for(0, 100) == 10 && steps_for(0, 255) == 10);
  assert(steps_for(0, 4) == 4 && steps_for(1, 13) == 12 && steps_for(100, 0) == 10 && steps_for(3, 0) == 3);
  assert(steps_for(5, 5) == 10);
}

static void a_card_has_keys_and_a_tile_has_not() {
  // A card's level, 600 x 72 on a glass whose finger needs 64: a key at each end as wide as it is high, ten blocks between.
  const Layout card = layout(600, 72, 10, 64, 6);
  assert(card.keys && !card.upright);
  assert(card.minus.w == 72 && card.minus.h == 72 && card.minus.x == 0 && card.plus.x == 600 - 72);
  assert(card.blocks.x == 72 + 12 && card.blocks.x + card.blocks.w == 600 - 72 - 12);
  // The blocks fill their room: the first starts where it starts, the last ends where it ends, none touch.
  assert(card.block(1).x == card.blocks.x);
  assert(card.block(10).x + card.block(10).w == card.blocks.x + card.blocks.w);
  for (int n = 1; n < 10; ++n) {
    assert(card.block(n).w > 20);
    assert(card.block(n + 1).x - (card.block(n).x + card.block(n).w) == 6);
  }
  // The slider under a tile's name, 330 x 24: too low for a key, so the blocks take all of it.
  const Layout tile = layout(330, 24, 10, 64, 4);
  assert(!tile.keys && tile.blocks.w == 330 && tile.block(1).x == 0);
  // A thin level standing up: the blocks stand on each other, the first at the bottom.
  const Layout tall = layout(60, 300, 10, 64, 6);
  assert(tall.upright && !tall.keys);
  assert(tall.block(1).y + tall.block(1).h == 300 && tall.block(10).y == 0);
  // A card's level standing up (a lamp's brightness), 120 x 420: plus at the top, minus at the bottom.
  const Layout lamp = layout(120, 420, 10, 64, 6);
  assert(lamp.upright && lamp.keys && lamp.plus.y == 0 && lamp.minus.y == 420 - 120 && lamp.plus.h == 120);
  assert(lamp.block(1).y + lamp.block(1).h == 420 - 120 - 12 && lamp.block(10).y == 120 + 12);
  assert(pick(lamp, 60, 30).kind == Pick::PLUS && pick(lamp, 60, 400).kind == Pick::MINUS);
  assert(pick(lamp, 60, lamp.block(4).y + 3).level == 4);
  // Too narrow for two keys and ten blocks: blocks alone.
  assert(!layout(180, 72, 10, 64, 6).keys);
}

static void a_tap_picks() {
  const Layout card = layout(600, 72, 10, 64, 6);
  assert(pick(card, 10, 36).kind == Pick::MINUS && pick(card, 590, 36).kind == Pick::PLUS);
  // The middle of every block picks that block.
  for (int n = 1; n <= 10; ++n) {
    const Box b = card.block(n);
    const Pick p = pick(card, b.x + b.w / 2, 36);
    assert(p.kind == Pick::LEVEL && p.level == n);
  }
  // Without keys the very start of the first block picks none, so a tile's level can be set to nothing.
  const Layout tile = layout(330, 24, 10, 64, 4);
  assert(pick(tile, 2, 12).kind == Pick::LEVEL && pick(tile, 2, 12).level == 0);
  assert(pick(tile, 20, 12).level == 1 && pick(tile, 329, 12).level == 10);
  // A finger that drifted off an end still means that end.
  assert(pick(tile, -30, 12).level == 0 && pick(tile, 400, 12).level == 10);
  // Standing up, from the bottom.
  const Layout tall = layout(60, 300, 10, 64, 6);
  assert(pick(tall, 30, 290).level == 1 && pick(tall, 30, 5).level == 10 && pick(tall, 30, 150).level == 5);
}

static void a_value_and_its_blocks() {
  // Per mille, as the core's sliders count: 71 % is seven blocks, 3 % is one (the lamp is on), nothing is none.
  assert(level_of(710, 0, 1000, 10) == 7 && level_of(30, 0, 1000, 10) == 1 && level_of(0, 0, 1000, 10) == 0);
  assert(level_of(1000, 0, 1000, 10) == 10 && level_of(949, 0, 1000, 10) == 9 && level_of(950, 0, 1000, 10) == 10);
  for (int n = 0; n <= 10; ++n) assert(level_of(value_of(n, 0, 1000, 10), 0, 1000, 10) == n);
  assert(value_of(6, 0, 1000, 10) == 600 && value_of(10, 0, 255, 10) == 255 && value_of(0, 0, 255, 10) == 0);
  // A range that counts down (a blind whose fill hangs from the top) works the same way round.
  assert(value_of(3, 1000, 0, 10) == 700 && level_of(700, 1000, 0, 10) == 3 && level_of(1000, 1000, 0, 10) == 0);
  // Four speeds.
  assert(value_of(2, 0, 4, 4) == 2 && level_of(3, 0, 4, 4) == 3);
}

static void a_key_takes_one_step() {
  // From a whole block: one block down or up, never past an end.
  assert(step(600, +1, 0, 1000, 10) == 700 && step(600, -1, 0, 1000, 10) == 500);
  assert(step(1000, +1, 0, 1000, 10) == 1000 && step(0, -1, 0, 1000, 10) == 0);
  // From between two blocks (Home Assistant says 71 %): up goes to 80, down to 70, not past it to 60.
  assert(step(710, +1, 0, 1000, 10) == 800 && step(710, -1, 0, 1000, 10) == 700);
  assert(step(690, +1, 0, 1000, 10) == 700 && step(690, -1, 0, 1000, 10) == 600);
  // The last block down is nothing: a lamp at its lowest block goes off.
  assert(step(100, -1, 0, 1000, 10) == 0 && step(30, -1, 0, 1000, 10) == 0);
  // A range that counts down.
  assert(step(700, +1, 1000, 0, 10) == 600 && step(700, -1, 1000, 0, 10) == 800);
}

int main() {
  the_blocks_of_a_range();
  a_card_has_keys_and_a_tile_has_not();
  a_tap_picks();
  a_value_and_its_blocks();
  a_key_takes_one_step();
  std::puts("level_bar: ok");
  return 0;
}
