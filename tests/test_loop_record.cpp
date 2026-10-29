// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_loop_record.cpp -o /tmp/test_loop_record && /tmp/test_loop_record
//
// The main loop at the task watchdog (components/smart_display/loop_record.h): the scan keeps the words of a stack that
// look like code, newest first, and no more than fit.
#include "../components/smart_display/loop_record.h"
#include <cassert>
#include <cstdio>

using namespace loop_record;

static bool looks_like_code(uint32_t w) { return (w & 0xFF000000u) == 0x48000000u || (w & 0xFFF00000u) == 0x4FF00000u; }

int main() {
  // A RISC-V frame at the top (MEPC, RA, then registers), the callers' return addresses further up, data in between.
  const uint32_t stack[] = {0x4FF23BEA, 0x4FF23BD8, 0x3C0A0000, 0x00000000, 0x12345678, 0x48123456, 0x3C0B0000,
                            0x4812ABCD, 0x00000002, 0x4813F000};
  uint32_t out[MOST] = {};
  const int n = scan(stack, stack + sizeof stack / sizeof stack[0], out, MOST, looks_like_code);
  assert(n == 5);
  assert(out[0] == 0x4FF23BEA && out[1] == 0x4FF23BD8 && out[2] == 0x48123456 && out[3] == 0x4812ABCD && out[4] == 0x4813F000);

  // At most `most`, the newest ones.
  uint32_t few[2] = {};
  assert(scan(stack, stack + 10, few, 2, looks_like_code) == 2 && few[0] == 0x4FF23BEA && few[1] == 0x4FF23BD8);

  // An empty or inverted range keeps nothing.
  assert(scan(stack, stack, out, MOST, looks_like_code) == 0);
  assert(scan(stack + 4, stack, out, MOST, looks_like_code) == 0);
  printf("test_loop_record: ok\n");
  return 0;
}
