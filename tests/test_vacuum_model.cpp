// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_vacuum_model.cpp -o /tmp/test_vacuum_model && /tmp/test_vacuum_model
// The vacuum card of the module (vacuum_model.h): the keys a robot gets from what it can do, as Home Assistant's dialog
// gives them; rooms picked in the order of the taps and sent as one list of areas; the rooms page per floor and its pages.
#include "../components/smart_display/vacuum_model.h"
#include <cassert>
#include <cstdio>
#include <string>

using namespace vacuum_model;
namespace f = tile_catalogue::vacuum;

int main() {
  // A Roborock: start, pause, stop, dock, locate, by area.
  const Can roborock = can(f::START | f::PAUSE | f::STOP | f::RETURN_HOME | f::LOCATE | f::CLEAN_AREA | f::STATE | f::FAN_SPEED);
  assert(roborock.by_area && roborock.locate);
  assert(first_key("docked", roborock) == Key::START && second_key("docked", roborock) == Key::DOCK);
  assert(first_key("cleaning", roborock) == Key::PAUSE && second_key("cleaning", roborock) == Key::DOCK);
  assert(first_key("paused", roborock) == Key::RESUME && second_key("paused", roborock) == Key::DOCK);
  // On its way home Dock is what it does: Stop beside Start.
  assert(first_key("returning", roborock) == Key::START && second_key("returning", roborock) == Key::STOP);
  assert(std::string(service(Key::RESUME)) == "vacuum.start" && std::string(service(Key::DOCK)) == "vacuum.return_to_base");

  // SwitchBot over Bluetooth: start and dock only. While it cleans, Dock is how a run ends.
  const Can switchbot = can(f::START | f::RETURN_HOME | f::STATE);
  assert(first_key("cleaning", switchbot) == Key::DOCK && second_key("cleaning", switchbot) == Key::NONE);
  assert(first_key("docked", switchbot) == Key::START && second_key("docked", switchbot) == Key::DOCK);

  // Miele: no dock. Pause and Stop while it cleans, Start alone while it rests.
  const Can miele = can(f::START | f::STOP | f::PAUSE | f::FAN_SPEED | f::STATE);
  assert(first_key("cleaning", miele) == Key::PAUSE && second_key("cleaning", miele) == Key::STOP);
  assert(first_key("idle", miele) == Key::START && second_key("idle", miele) == Key::NONE);

  // Matter at its least: start, stop, state.
  const Can matter = can(f::START | f::STOP | f::STATE);
  assert(first_key("cleaning", matter) == Key::STOP && second_key("cleaning", matter) == Key::NONE);

  // Features unknown (an unavailable robot): the keys it may have, nothing it may not.
  const Can unknown = can(0);
  assert(unknown.start && unknown.dock && !unknown.locate && !unknown.by_area);

  // Rooms in the order of the taps; a second tap takes one out, the rest keep their order.
  Data d;
  d.rooms = {{"hall", "Hall", 0, 0}, {"kitchen", "Kitchen", 0, 0}, {"living_room", "Living room", 0, 0}, {"bad id!", "Odd", 0, 0}};
  std::vector<uint8_t> picked;
  toggle(picked, 1); toggle(picked, 2); toggle(picked, 0);
  assert(place(picked, 1) == 1 && place(picked, 2) == 2 && place(picked, 0) == 3);
  toggle(picked, 2);
  assert(place(picked, 0) == 2 && place(picked, 2) == 0);
  assert(areas_template(d, picked) == "{{ ['kitchen', 'hall'] }}");
  // An id that is no slug never reaches the template.
  std::vector<uint8_t> odd{3};
  assert(areas_template(d, odd).empty());
  // Rooms that went: picks of them go too.
  picked = {0, 3, 1};
  keep_valid(picked, 2);
  assert(picked.size() == 2 && picked[0] == 0 && picked[1] == 1);

  // Floors: one floor shows every room; two show a floor at a time.
  Data two;
  two.floors = {"Ground floor", "First floor"};
  for (int i = 0; i < 10; ++i) two.rooms.push_back({"r" + std::to_string(i), "Room", 0, static_cast<uint8_t>(i < 5 ? 0 : 1)});
  assert(on_floor(two, 0).size() == 5 && on_floor(two, 1).size() == 5 && on_floor(two, 1)[0] == 5);
  Data one = two;
  one.floors.clear();
  assert(on_floor(one, 1).size() == 10);
  assert(pages(10, 4) == 3 && pages(10, 10) == 1 && pages(0, 4) == 1);
  // Even rows: four as two and two, five as three and two, seven in four columns as four and three.
  assert(even_columns(4, 3) == 2 && even_columns(5, 3) == 3 && even_columns(4, 4) == 4 && even_columns(7, 4) == 4 && even_columns(3, 2) == 2);
  std::printf("vacuum card: ok\n");
  return 0;
}
