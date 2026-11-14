#include <algorithm>
#include <array>
#include <cassert>
#include <iostream>
#include "components/smart_display/page_protocol.h"

using namespace page_protocol;

int main() {
  for (unsigned columns = 1; columns <= 3; ++columns) for (unsigned rows = 1; rows <= 4; ++rows) {
    for (const auto &size : TILE_SIZES)
      assert(accepts_size(size.name, columns, rows) == size.fits(columns, rows));
    assert(accepts_size("", columns, rows));
    assert(!accepts_size("unknown", columns, rows));
  }
  assert(!accepts_size("square", 1, 4) && !accepts_size("square", 2, 1));
  // Spans (firmware 0.19.0): every rectangle smaller than the grid that no name already is.
  assert(accepts_size("3x2", 3, 3) && accepts_size("2x3", 2, 4) && accepts_size("5x4", 5, 5));
  assert(!accepts_size("2x3", 2, 3));   // the whole grid is "full"
  assert(!accepts_size("3x2", 2, 4));   // wider than the grid
  assert(!accepts_size("2x2", 3, 3) && !accepts_size("1x2", 3, 3) && !accepts_size("2x1", 3, 3));  // the names say these
  assert(!accepts_size("0x3", 4, 4) && !accepts_size("3x", 4, 4) && !accepts_size("33x", 4, 4));
  unsigned columns = 0, rows = 0;
  assert(span_of("4x3", columns, rows) && columns == 4 && rows == 3);
  assert(accepts_size("square", 2, 3) && accepts_size("tall", 1, 4));
  assert(!accepts_size("tall", 3, 1) && accepts_size("wide", 1, 4));
  uint64_t id = 0;
  assert(key("ffffffffffffffff", id) && id == UINT64_MAX);
  assert(key("0000000000000000", id) && id == 0);
  assert(!key("FFFFFFFFFFFFFFFF", id));
  assert(!key("123", id));
  assert(!key("000000000000000g", id));
  Pages pages;
  for (unsigned i = 0; i < 5; ++i) { Page page; page.id = i + 1; pages.records.push_back(page); }
  pages.home = 3;
  for (unsigned mask = 0; mask < 32; ++mask) {
    unsigned included = 0;
    for (unsigned i = 0; i < 5; ++i) {
      pages.records[i].excluded = mask & (1u << i);
      if (!pages.records[i].excluded) ++included;
    }
    assert(pages.count() == included);
    int ordinal = 0;
    for (int i = 0; i < 5; ++i) {
      assert(pages.ordinal(i) == (pages.included(i) ? ordinal++ : -1));
      for (int direction : {-1, 1}) {
        int expected = i;
        if (pages.included(i)) for (int j = i + direction; j >= 0 && j < 5; j += direction)
          if (pages.included(j)) { expected = j; break; }
        assert(pages.step(i, direction) == expected);
        // Looping: the same in the middle, and from the ends round to the first page that is in the sequence.
        int around = i;
        if (pages.included(i)) for (int moved = 1; moved < 5; ++moved) {
          const int j = (i + direction * moved + 5) % 5;
          if (pages.included(j)) { around = j; break; }
        }
        assert(pages.step(i, direction, true) == around);
      }
    }
    assert(pages.restore(2, true) == 1);
    assert(pages.restore(99, true) == 3);
    assert(pages.restore(2, false) == 3);
  }
  std::reverse(pages.records.begin(), pages.records.end());
  assert(pages.restore(2, true) == 3);

  // Detail Back remembers the actual route, not numeric order. It remains a
  // small fixed buffer, including through cycles, reorders and removed pages.
  NavigationHistory history;
  pages.home = 1;
  history.push(pages, 1, 3);
  history.push(pages, 3, 4);
  assert(history.target(pages, 4) == 3);
  std::swap(pages.records[3], pages.records[0]);
  assert(history.pop(pages, 4) == 0);
  assert(history.pop(pages, 0) == 1);
  assert(history.pop(pages, 4) == pages.home);
  for (int i = 0; i < 100; ++i) history.push(pages, i % 5, (i + 1) % 5);
  assert(history.size == MAX_PAGES);
  history.clear(); history.push(pages, 4, 3);
  pages.records.pop_back();
  assert(history.pop(pages, 3) == pages.home && history.size == 0);
  assert(pages.footer(true) && !pages.footer(false));
  pages.records.resize(1); pages.records[0].excluded = true; pages.home = 0;
  assert(!pages.footer(true) && history.target(pages, 0) == 0);
  static_assert(sizeof(NavigationHistory) <= 72, "Back stores at most eight page IDs");

  // Interrupt after every record at every supported page/tile count. The same
  // revision must recover, while an already complete one stays interactive.
  for (unsigned count = 0; count <= MAX_TILES; ++count) for (unsigned np = 1; np <= MAX_PAGES; ++np) {
    for (unsigned stop = 0; stop < np + count; ++stop) {
      Transfer transfer;
      assert(transfer.grant(10, 100) == 100);
      assert(transfer.begin(30, np, count) == Begin::replace);
      for (unsigned n = 0; n < stop; ++n) assert(n < np ? transfer.page(n) : transfer.tile(n - np));
      assert(!transfer.commit() && !transfer.active);
      transfer.grant(11, 101);
      assert(transfer.begin(30, np, count) == Begin::replace);
      for (unsigned n = 0; n < np; ++n) { assert(transfer.page(n)); assert(!transfer.page(n)); }
      for (unsigned n = 0; n < count; ++n) { assert(transfer.tile(n)); assert(!transfer.tile(n)); }
      assert(!transfer.page(np) && !transfer.tile(count));
      assert(transfer.commit() && transfer.active && transfer.matches(30));
      transfer.grant(12, 102);
      assert(transfer.begin(30, np, count) == Begin::unchanged && transfer.active);
      assert(transfer.commit());
      transfer.grant(13, 103);
      assert(transfer.begin(31, np, count) == Begin::replace && !transfer.active);
    }
  }
  Transfer transfer;
  assert(transfer.packet(0, 1, 1) == Packet::reject);
  transfer.grant(1, 42);
  assert(transfer.grant(1, 43) == 42); // Lost hello reply: exact retry retains lease.
  assert(transfer.packet(42, 0, 1) == Packet::reject);
  assert(transfer.packet(42, 1, 1) == Packet::accept);
  transfer.accepted(1, 1);
  assert(transfer.packet(42, 1, 1) == Packet::duplicate);
  assert(transfer.packet(42, 1, 2) == Packet::reject);
  assert(transfer.packet(41, 100, 1) == Packet::reject);
  assert(transfer.begin(1, 0, 0) == Begin::reject);
  assert(transfer.begin(1, 9, 0) == Begin::reject);
  assert(transfer.begin(1, 1, 65) == Begin::reject);
  assert(transfer.begin(1, 1, 0) == Begin::replace);
  assert(transfer.begin(2, 1, 0) == Begin::reject);
  transfer.grant(2, 43);
  assert(transfer.packet(42, 10, 10) == Packet::reject);
  assert(transfer.begin(2, 1, 0) == Begin::replace);
  transfer.accepted(UINT32_MAX, 3);
  assert(transfer.packet(43, 1, 4) == Packet::reject); // Wrap requires a fresh lease.
  static_assert(sizeof(Transfer) <= 64, "The transport guard must remain bounded");
  std::cout << "Page navigation, 64-bit IDs and interrupted transfers passed; guard "
            << sizeof(Transfer) << " B, page " << sizeof(Page) << " B on this host.\n";
}
