#pragma once
// The screensaver's clock faces (module clock_faces, tier full; docs/SCREENSAVER.md, docs/MODULES.md): what
// runtime_tiles.h reaches of them. The faces themselves are module_clock_faces.cpp, a compilation unit of its own; a lite
// screen has neither, and keeps the digital clock.
#include "esphome/core/defines.h"
#ifdef SD_MOD_CLOCK_FACES
#include <string>
#include <vector>
#include "lvgl.h"
#include "esphome/core/time.h"
#include "header_bar.h"

namespace runtime_tiles {
struct SaverFace;
namespace clock_faces {
// The face whole into the screensaver's root, every minute: Glass, Classic (with the clock's row of entities, the
// temperature first, or `degrees` alone) or Bauhaus.
void draw(lv_obj_t *root, const SaverFace &face, const esphome::ESPTime &now, const std::vector<header_bar::Item> &row,
          const std::string &degrees);
// Every second: the seconds hand one step on, only its old and its new strip drawn again.
void tick(const esphome::ESPTime &now);
// The face left the glass (the screensaver hid): its hands are no longer there to move.
void forget();
}  // namespace clock_faces
}  // namespace runtime_tiles
#endif
