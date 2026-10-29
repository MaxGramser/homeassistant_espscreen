// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_ppa_guard.cpp -o /tmp/test_ppa_guard && /tmp/test_ppa_guard
//
// The PPA guard (components/smart_display/ppa_guard.h): a turned block the 2D-DMA would never finish goes to the engine
// in pieces. Proven here: the rules match ESP-IDF's (the issue's own three cases), the pieces cover the block exactly
// once and land where the whole would have (against a plain rotation on the host), every piece is one the engine takes
// whole, and every turned block of a screen's sizes has a plan of few pieces.
#include "../components/smart_display/ppa_guard.h"
#include <cassert>
#include <cstdio>
#include <vector>

using namespace ppa_guard;

static Block block(uint32_t w, uint32_t h, Angle angle, Scale sx = {}, Scale sy = {}, uint32_t depth = 16) {
  Block b;
  b.w = w;
  b.h = h;
  b.angle = angle;
  b.sx = sx;
  b.sy = sy;
  b.depth = depth;
  b.unit_w = depth >= 24 ? 32 : 64;
  return b;
}

// Where the input pixel x, y of a block lands when the whole block is turned and scaled: the reference the pieces must
// agree with. Nearest neighbour: an output pixel takes the input pixel under it.
static void reference(const Block &b, uint32_t out_x, uint32_t out_y, uint32_t &in_x, uint32_t &in_y) {
  const Size out = output_of(b);
  // Unscale first: along the output's x the scale of the input axis that became it.
  const Scale scale_x = turned(b.angle) ? b.sy : b.sx, scale_y = turned(b.angle) ? b.sx : b.sy;
  const uint32_t ux = out_x * FRAG_MAX / (scale_x.whole * FRAG_MAX + scale_x.frag);
  const uint32_t uy = out_y * FRAG_MAX / (scale_y.whole * FRAG_MAX + scale_y.frag);
  (void) out;
  switch (b.angle) {
    case A0:
      in_x = ux;
      in_y = uy;
      break;
    case A90:  // counter-clockwise: the output's first row is the input's last column
      in_x = b.w - 1 - uy;
      in_y = ux;
      break;
    case A180:
      in_x = b.w - 1 - ux;
      in_y = b.h - 1 - uy;
      break;
    case A270:  // the output's first column is the input's last row
      in_x = uy;
      in_y = b.h - 1 - ux;
      break;
  }
}

// The plan of a block: every piece safe, the output covered exactly once, every output pixel from the input pixel the
// whole block would have put there. Returns the number of pieces, 0 when the guard gave the block up.
static int check(const Block &b, bool must_split) {
  Piece pieces[MAX_PIECES];
  const int n = plan(b, pieces);
  if (n == 0) return 0;
  if (must_split) assert(n > 1);
  if (n == 1) {  // the block itself, from its corner
    assert(pieces[0].in_x == 0 && pieces[0].in_y == 0 && pieces[0].in_w == b.w && pieces[0].in_h == b.h);
    return 1;
  }
  const Size out = output_of(b);
  std::vector<uint8_t> covered(static_cast<size_t>(out.w) * out.h, 0);
  for (int i = 0; i < n; ++i) {
    const Piece &p = pieces[i];
    assert(p.in_w > 0 && p.in_h > 0 && p.in_x + p.in_w <= b.w && p.in_y + p.in_h <= b.h);
    const Block piece = part(b, p.in_w, p.in_h);
    assert(safe(piece));
    const Size size = output_of(piece);
    assert(p.out_x + size.w <= out.w && p.out_y + size.h <= out.h);
    for (uint32_t y = 0; y < size.h; ++y)
      for (uint32_t x = 0; x < size.w; ++x) {
        const uint32_t ox = p.out_x + x, oy = p.out_y + y;
        assert(covered[static_cast<size_t>(oy) * out.w + ox] == 0);
        covered[static_cast<size_t>(oy) * out.w + ox] = 1;
        // The piece turned on its own, put at its place, shows the pixel the whole would show.
        uint32_t px = 0, py = 0, wx = 0, wy = 0;
        reference(piece, x, y, px, py);
        reference(b, ox, oy, wx, wy);
        assert(p.in_x + px == wx && p.in_y + py == wy);
      }
  }
  for (uint8_t c : covered) assert(c == 1);
  return n;
}

int main() {
  // ESP-IDF #19023's three cases at 270 degrees, RGB565: the control goes whole, the suspect stalls while the driver
  // leaves the bypass off, and the reporter's split (368x65 and 368x1) is two pieces the driver sets the bypass for.
  assert(!stalls(block(600, 40, A270)) && safe(block(600, 40, A270)));
  assert(stalls(block(368, 66, A270)) && !driver_bypasses(block(368, 66, A270)));
  assert(driver_bypasses(block(368, 65, A270)) && driver_bypasses(block(368, 1, A270)));
  assert(check(block(600, 40, A270), false) == 1);
  assert(check(block(368, 66, A270), true) == 2);
  // The reporter's other stalls (its comment on the fix): 364x67 and the single-unit blocks 46x4 and 46x2.
  assert(stalls(block(364, 67, A270)) && !driver_bypasses(block(364, 67, A270)) && check(block(364, 67, A270), true) >= 2);
  assert(stalls(block(46, 4, A270)) && check(block(46, 4, A270), true) >= 2);
  assert(stalls(block(46, 2, A270)) && check(block(46, 2, A270), true) >= 2);

  // The Tab5's live tiles of TR-4EFBDE (618x308 and 618x307, turned a quarter) go whole: their leftover is not small.
  assert(check(block(618, 308, A270), false) == 1 && check(block(618, 307, A270), false) == 1);
  // A thin strip LVGL draws across a turned glass: 300x4 stalls (a 4-wide column of units with a 12-row leftover) and
  // goes in two pieces the driver sets the bypass for.
  assert(stalls(block(300, 4, A270)) && !driver_bypasses(block(300, 4, A270)) && check(block(300, 4, A270), true) == 2);

  // The top bar's hold line on a reTerminal D1001 (2026-10-27): a 6-row strip turned a quarter whose last unit is
  // exactly the FIFO (6 x 16 x 16 bits). The hardware stalled on 336x6 and on 864x6, a piece of 872x6, so both go in
  // pieces now, each one the engine takes whole, while the driver still counts such a block strictly and sets no bypass
  // for it. 904x6 goes whole: the driver sets the bypass for it (904 % 64 = 8). 200x6 too (200 % 64 = 8).
  assert(stalls(block(336, 6, A90)) && !driver_bypasses(block(336, 6, A90)));
  assert(stalls(block(864, 6, A90)) && !driver_bypasses(block(864, 6, A90)));
  for (uint32_t w : {336u, 864u, 872u, 528u, 1280u}) assert(check(block(w, 6, A90), true) >= 2);
  assert(check(block(904, 6, A90), false) == 1 && check(block(200, 6, A90), false) == 1);

  // Unturned, the driver's rule is the hardware's: never a split, whatever the size.
  for (uint32_t w = 1; w <= 200; ++w)
    for (uint32_t h = 1; h <= 200; h += 3) {
      assert(check(block(w, h, A0), false) == 1);
      assert(check(block(w, h, A180), false) == 1);
    }

  // A build for the P4's revision 3 runs macro blocks of 32 rows (the engine's register, as the driver reads it): 33x17
  // turned 270 is safe with 16 (the driver sets the bypass) and stalls with 32 (it does not), so there it goes in
  // pieces; 30x2 is the other way round, one unit tall with 32 rows.
  Block rev3 = block(33, 17, A270);
  rev3.mb = 32;
  assert(safe(block(33, 17, A270)) && stalls(rev3) && !driver_bypasses(rev3) && check(rev3, true) >= 2);
  Block rev3_thin = block(30, 2, A270);
  rev3_thin.mb = 32;
  assert(!safe(block(30, 2, A270)) && safe(rev3_thin) && check(rev3_thin, false) == 1);

  // Every turned block up to 200 x 200, at both angles, in 16- and 32-bit pixels and with macro blocks of 16 and 32
  // rows: a plan, few pieces, all safe.
  int most = 0;
  uint32_t most_w = 0, most_h = 0;
  for (uint32_t mb : {16u, 32u})
    for (uint32_t depth : {16u, 32u})
      for (Angle angle : {A90, A270})
        for (uint32_t w = 1; w <= 200; ++w)
          for (uint32_t h = 1; h <= 200; ++h) {
            Block b = block(w, h, angle, {}, {}, depth);
            b.mb = mb;
            const int n = check(b, stalls(b) && !driver_bypasses(b));
            assert(n >= 1);
            if (n > most) {
              most = n;
              most_w = w;
              most_h = h;
            }
          }
  printf("turned blocks up to 200x200: at most %d pieces (%ux%u)\n", most, (unsigned) most_w, (unsigned) most_h);
  assert(most <= 6);

  // The long thin strips LVGL flushes on a turned glass (a line, a divider, a bar's edge), up to the glass's 1280: every
  // one has a plan.
  int most_strip = 0;
  uint32_t strip_w = 0, strip_h = 0;
  for (Angle angle : {A90, A270})
    for (uint32_t thin = 1; thin <= 8; ++thin)
      for (uint32_t along = 1; along <= 1280; ++along)
        for (int way = 0; way < 2; ++way) {
          const Block b = way ? block(thin, along, angle) : block(along, thin, angle);
          const int n = check(b, stalls(b) && !driver_bypasses(b));
          assert(n >= 1);
          if (n > most_strip) {
            most_strip = n;
            strip_w = b.w;
            strip_h = b.h;
          }
        }
  printf("thin strips up to 1280: at most %d pieces (%ux%u)\n", most_strip, (unsigned) strip_w, (unsigned) strip_h);
  assert(most_strip <= 8);

  // A screen's own sizes: a tile, a card two cells wide, a strip of a few rows and a whole glass, at 1280x720 and
  // 720x1280, every width and height near a unit's edge.
  int most_large = 0;
  for (uint32_t w : {1u, 2u, 5u, 6u, 16u, 17u, 63u, 64u, 65u, 300u, 308u, 320u, 321u, 325u, 618u, 640u, 641u, 645u,
                     700u, 720u, 1024u, 1280u})
    for (uint32_t h : {1u, 2u, 5u, 6u, 16u, 17u, 63u, 64u, 65u, 69u, 300u, 307u, 308u, 320u, 321u, 325u, 618u, 640u,
                       641u, 645u, 700u, 720u, 1024u, 1280u})
      for (Angle angle : {A90, A270}) {
        const Block b = block(w, h, angle);
        const int n = check(b, stalls(b) && !driver_bypasses(b));
        assert(n >= 1);
        if (n > most_large) most_large = n;
      }
  printf("a screen's sizes: at most %d pieces\n", most_large);
  assert(most_large <= 6);

  // Scaled, as a camera's picture fills the full view (live_view.cpp fit): twice, one and a half, and a size whose scaled
  // picture is not whole, which the guard leaves alone.
  assert(check(block(320, 180, A270, {2, 0}, {2, 0}), false) >= 1);
  {
    const Block twice = block(368, 33, A270, {2, 0}, {2, 0}), half = block(368, 44, A270, {1, 8}, {1, 8});
    assert(check(twice, stalls(twice) && !driver_bypasses(twice)) >= 1);
    assert(check(half, stalls(half) && !driver_bypasses(half)) >= 1);
  }
  // Twice, every size: a plan for each, as at its own size. One and a half: a cut is legal every other pixel only, so
  // a few blocks find no plan and go as they are; the rest are proven as above.
  for (uint32_t w = 1; w <= 160; ++w)
    for (uint32_t h = 1; h <= 160; ++h) {
      const Block b = block(w, h, A270, {2, 0}, {2, 0});
      assert(check(b, stalls(b) && !driver_bypasses(b)) >= 1);
    }
  int unplanned = 0, scaled_blocks = 0;
  for (uint32_t w = 2; w <= 160; w += 2)
    for (uint32_t h = 2; h <= 160; h += 2) {
      const Block b = block(w, h, A270, {1, 8}, {1, 8});
      ++scaled_blocks;
      if (check(b, false) == 0) ++unplanned;
    }
  printf("one and a half: %d of %d blocks have no plan\n", unplanned, scaled_blocks);
  assert(unplanned * 20 < scaled_blocks);
  {
    Piece pieces[MAX_PIECES];
    const Block odd = block(367, 66, A270, {1, 8}, {1, 8});  // 367 x 1.5 is not whole
    assert(!exact(367, odd.sx) && plan(odd, pieces) == 1);
  }

  // An empty block or one the guard knows nothing about gives no plan.
  {
    Piece pieces[MAX_PIECES];
    assert(plan(block(0, 10, A270), pieces) == 0 && plan(block(10, 0, A270), pieces) == 0);
    Block unknown = block(10, 10, A270);
    unknown.depth = 0;
    assert(plan(unknown, pieces) == 0);
  }
  printf("test_ppa_guard: ok\n");
  return 0;
}
