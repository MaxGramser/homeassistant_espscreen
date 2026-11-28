#pragma once
// How far the screen's own camera turns its picture to stand upright (plugin API 0.19, tessera::camera_turn), worked
// out from three facts: how the board mounts the sensor against the glass (`orientation`, CAMERA_ORIENTATION in the
// board file: 0 or 180, packages/core.yaml), LVGL's rotation now (`turn`, glass::turn) and the rotation that lays the
// glass out lying down (`landscape`, ROTATION_LANDSCAPE). A screen turned half way round from lying down hangs upside
// down, its camera with it, so the picture turns half way round too. A quarter turn (a screen stood up) changes nothing:
// the picture stays lying down, as the sensor sees the room (docs/CAMERA.md). The answer is 0 or 180. Pure, so a PC
// tests it (tests/test_camera_turn.cpp).
namespace camera_turn {

inline int degrees(int orientation, int turn, int landscape) {
  const int from_lying = (((turn - landscape) % 360) + 360) % 360;
  const bool upside_down = ((((orientation % 360) + 360) % 360) == 180) != (from_lying == 180);
  return upside_down ? 180 : 0;
}

}  // namespace camera_turn
