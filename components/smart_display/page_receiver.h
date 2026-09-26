#pragma once
// What ESP Screens sends a screen: a layout, a tile's state, a page, a bar value, a picture or a reply. The parser is
// page_receiver.cpp, a compilation unit of its own (see there why); runtime_tiles.h includes this after the model and
// the UI callbacks it fills are declared.
#include <string>
namespace runtime_tiles {
// Reads one message and applies it; returns the status the screen reports back ("Synced", "Loading tiles", an error).
std::string receive(const std::string &payload);
}  // namespace runtime_tiles
