// The numbers of the pictures the firmware and the app keep the same, as the compiler sees them (picture_store.h,
// camera_view.h, picture_jpeg.h, live_view.h), printed for tests/test_camera.py: one line each, `name<TAB>value`.
// For every file named on the command line, what picture_jpeg::jpeg_notes reads of it, so that test hands this
// program the JPEGs the app makes (picture_paint.encode) and sees the screen read them. Built by that test; no test of
// its own (tests/*.cpp are).
#include "../../components/smart_display/camera_view.h"
#include "../../components/smart_display/live_view.h"
#include "../../components/smart_display/picture_jpeg.h"
#include "../../components/smart_display/picture_store.h"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>

int main(int argc, char **argv) {
  std::printf("MAX_SIDE\t%d\n", picture_store::MAX_SIDE);
  std::printf("MAX_BYTES\t%zu\n", picture_store::MAX_BYTES);
  std::printf("LARGE_SIDE\t%d\n", picture_store::LARGE_SIDE);
  std::printf("REFRESH_MS\t%u\n", static_cast<unsigned>(camera_view::REFRESH_MS));
  std::printf("MCU\t%d\n", picture_jpeg::MCU);
  std::printf("NOTES_MARK\t%s\n", picture_jpeg::NOTES_MARK);
  std::printf("MAX_CORNERS\t%d\n", picture_jpeg::MAX_CORNERS);
  std::printf("FADE_PERCENT\t%d\n", live_view::FADE_PERCENT);
  std::printf("FADE_DEPTH\t%d\n", live_view::FADE_DEPTH);
  // The cap one picture takes for a store of each budget (picture_store::cap_for): `cap<TAB>budget<TAB>side<TAB>bytes`.
  for (size_t budget : {size_t(0), size_t(1) << 20, size_t(4) << 20, picture_store::MAX_BYTES * 3,
                        picture_store::MAX_BYTES * 3 + 3, size_t(6) << 20, size_t(12) << 20, size_t(64) << 20}) {
    const picture_store::Cap cap = picture_store::cap_for(budget);
    std::printf("cap\t%zu\t%d\t%zu\n", budget, cap.side, cap.bytes);
  }
  // `notes<TAB>file<TAB>width<TAB>height<TAB>corners`, each corner `x,y,w,h,radius,ground`; `notes<TAB>file<TAB>none`
  // where the screen finds none.
  for (int i = 1; i < argc; ++i) {
    std::ifstream in(argv[i], std::ios::binary);
    const std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    picture_jpeg::JpegNotes notes;
    if (!picture_jpeg::jpeg_notes(bytes.data(), bytes.size(), notes)) {
      std::printf("notes\t%s\tnone\n", argv[i]);
      continue;
    }
    std::printf("notes\t%s\t%d\t%d\t", argv[i], notes.width, notes.height);
    for (size_t c = 0; c < notes.corners.size(); ++c) {
      const auto &k = notes.corners[c];
      std::printf("%s%d,%d,%d,%d,%d,%u", c ? ";" : "", k.x, k.y, k.w, k.h, k.radius, static_cast<unsigned>(k.ground));
    }
    std::printf("\n");
  }
  return 0;
}
