#pragma once
// A file from ESP Screen Manager, downloaded whole beside the main loop (docs/SCREEN_FILES.md). The add-on serves every
// file a screen takes under /files/<sha256>.<ext> on its LAN port (8098), the same port as the pictures: the name is the
// file's content, so a screen that has a name has its file and asks for nothing. The first user is a call's ringtone
// (module_call.cpp); whatever comes next (a chime, a plugin's data) asks the same way.
//
// What it knows: one GET at a time in a task of its own (http_get.h), the body whole into PSRAM (roomy.h), up to the size
// its caller allows, and the answer handed over on the main loop (tick, every 50 ms with the pictures). What it does not:
// what a file means; its caller reads it (wav.h for a sound). A download that does not connect, answers anything but
// 200, is larger than allowed, breaks off or takes longer than ten seconds ends as a failure; the caller decides what
// then (a ring rings with the screen's own tone).
//
// Only a board with pictures builds the task (SCREEN_PICTURES, packages/features/camera.yaml); elsewhere get() fails at once.
// name_of() is pure: tests/test_wav.cpp checks it on a PC.
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>

namespace file_fetch {

// The bytes of a finished download, in PSRAM; its owner frees them with roomy::release. Null on a failure.
using Done = std::function<void(bool ok, uint8_t *data, size_t size)>;

// Downloads `url` (http://host:port/files/<name>), at most `most` bytes, and calls `done` on the main loop. Downloads
// wait their turn, one at a time. False when it cannot start (not a link, no pictures on this board): `done` is not called.
bool get(const std::string &url, size_t most, Done done);
// Hands finished downloads to their `done` and starts the next (the main loop, every 50 ms).
void tick();

// The name of a file's link: what follows /files/, without its extension; "" for a link that is not a file's. A caller
// keeps it to know whether the file it has is the one a link names.
inline std::string name_of(const std::string &url) {
  const std::string mark = "/files/";
  const size_t at = url.find(mark);
  if (at == std::string::npos) return "";
  const size_t start = at + mark.size();
  size_t stop = url.find_first_of(".?#", start);
  if (stop == std::string::npos) stop = url.size();
  return url.substr(start, stop - start);
}

}  // namespace file_fetch
