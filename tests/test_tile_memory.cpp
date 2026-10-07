// What a layout costs inside the chip and the room a screen has for it (tile_memory.h, firmware 0.34.0+). The prices come
// from the tile catalogue (catalogue/<type>.yaml `memory`, tile_catalogue.h); the cases every reader answers alike are in
// tests/fixtures/memory-conformance.json, checked here, in tests/test_tile_memory.py and in web/tests/memory.spec.ts.
#include "../components/smart_display/tile_memory.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

// A tiny reader for the fixture's flat lines: {"domain": "...", "action": true, "line": false, "psram": true, "tile": 524,
// "extra": 1056, "cost": 1234}, one case per line between the brackets.
static std::string field(const std::string &line, const std::string &name) {
  const auto at = line.find("\"" + name + "\": ");
  if (at == std::string::npos) return "";
  auto start = at + name.size() + 4, end = line.find_first_of(",}", start);
  std::string value = line.substr(start, end - start);
  if (!value.empty() && value.front() == '"') value = value.substr(1, value.size() - 2);
  return value;
}

int main() {
  using namespace tile_memory;
  const Board psram{true, 524, 1056, 336}, inside{false, 524, 1056, 336};
  // A type the catalogue names costs its own; a board without PSRAM pays the tile and, where it keeps one, its extras.
  const auto &weather = entry("weather"), &sw = entry("switch");
  assert(weather.extras && !sw.extras);
  assert(cost("weather", false, false, psram) == weather.bytes);
  assert(cost("weather", false, false, inside) == weather.bytes + 524u + 1056u);
  assert(cost("switch", false, false, inside) == sw.bytes + 524u);
  // A tile's own action or line adds its bytes, and a block of extras where its type keeps none.
  assert(cost("switch", true, false, psram) == sw.bytes + tile_catalogue::ACTION_BYTES);
  assert(cost("switch", false, true, inside) == sw.bytes + tile_catalogue::LINE_BYTES + 524u + 1056u);
  // An unknown type costs as the dearest one.
  uint32_t dearest = 0;
  for (const auto &m : tile_catalogue::MEMORY) dearest = std::max<uint32_t>(dearest, m.bytes);
  assert(cost("nonsense", false, false, psram) == dearest);
  assert(own_action("action") && !own_action("toggle") && own_line("attr:battery") && !own_line("text:Hi") && !own_line("auto"));
  assert(domain_of("light.kitchen") == "light" && domain_of("screen.page_12") == "screen");
  // A page: its title, each entity item of its bar, and on a board without PSRAM its record.
  assert(page_cost(0, psram) == tile_catalogue::PAGE_BYTES);
  assert(page_cost(3, inside) == tile_catalogue::PAGE_BYTES + 3u * tile_catalogue::BAR_TEXT_BYTES + 336u);
  // The room counts what the tiles on the screen already take, less the reserve, and never goes below nothing.
  assert(room(100 * 1024, 0) == 100 * 1024 - RESERVE);
  assert(room(30 * 1024, 20 * 1024) == 50 * 1024 - RESERVE);
  assert(room(10 * 1024, 0) == 0 && room(RESERVE, 0) == 0 && LOW_WATER < RESERVE);
  // The smallest of the last five samples, the oldest falling out.
  Window w;
  assert(w.least() == 0);
  w.add(50); w.add(40); w.add(60);
  assert(w.least() == 40);
  w.add(70); w.add(80); w.add(90);  // 50 falls out, 40 is the oldest left
  assert(w.least() == 40 && w.count == Window::SIZE);
  w.add(100);  // and now 40 falls out
  assert(w.least() == 60);
  w.clear();
  assert(w.least() == 0 && w.count == 0 && !w.known());
  w.add(0);
  assert(w.known() && w.least() == 0);  // a room of nothing, measured, is known
  // A sample only with a layout that has settled (firmware 0.51.0): none before a layout landed, none in its first minute,
  // then one a minute. The clock may wrap.
  assert(!sample_due(500000, 0, false, 0));
  assert(!sample_due(100000, 100000, false, 0) && !sample_due(100000 + SETTLE_MS - 1, 100000, false, 0));
  assert(sample_due(100000 + SETTLE_MS, 100000, false, 0));
  assert(!sample_due(300000, 100000, true, 280000) && sample_due(340000, 100000, true, 280000));
  const uint32_t late = UINT32_MAX - 1000;
  assert(!sample_due(late + 30000, late, false, 0) && sample_due(late + SETTLE_MS, late, false, 0));
  // Every case the three readers answer alike.
  std::ifstream in("tests/fixtures/memory-conformance.json");
  assert(in && "run from the repository root");
  std::string line;
  unsigned cases = 0;
  while (std::getline(in, line)) {
    const bool page = line.find("\"page_entities\"") != std::string::npos;
    if (!page && line.find("\"domain\"") == std::string::npos) continue;
    const Board board{field(line, "psram") == "true", static_cast<uint32_t>(std::stoul(field(line, "tile"))),
                      static_cast<uint32_t>(std::stoul(field(line, "extra"))), static_cast<uint32_t>(std::stoul(field(line, "page")))};
    const uint32_t want = static_cast<uint32_t>(std::stoul(field(line, "cost")));
    const uint32_t got = page ? page_cost(static_cast<unsigned>(std::stoul(field(line, "page_entities"))), board)
                              : cost(field(line, "domain"), field(line, "action") == "true", field(line, "line") == "true", board);
    if (got != want) { std::printf("%s: %u, the fixture says %u\n", line.c_str(), got, want); return 1; }
    ++cases;
  }
  assert(cases > 50);
  return 0;
}
