#pragma once
#include "calibration_math.h"
#include "esphome/core/preferences.h"
#include "esphome/core/hal.h"
#include "lvgl.h"
#include "theme.h"
#include "screen_text.h"
#include <functional>
namespace screen_calibration {
inline bool active = false, pressed = false;
inline unsigned point = 0, sample = 0;
inline uint32_t down_at = 0;
inline lv_obj_t *screen{}, *home{}, *cross{}, *instructions{}, *status{};
inline Calibration calibration;
inline std::array<std::array<Point,3>,5> samples;
// Where the screen itself put each tap. Together with the raw reading it says what the whole chain from
// panel to glass does, so the fit needs to know nothing about rotation or mirroring (firmware 0.2.92+).
inline std::array<std::array<Point,3>,5> screen_samples;
// The last reading of the tap being made, both halves from the same instant (firmware 0.2.97+). They used to be
// taken apart: the screen point at touch down, the panel's reading at lift. A finger rolls between those two
// moments, which is what a finger does, so the pair could describe two different places. None of the guards below
// caught it: the three taps and their median see the spread between taps, not the roll inside one, and the rule
// that every cross has to land back within 12 px holds the shifted chain against the shifted points, which agree.
// Measured on the fit itself (tests/test_calibration_math.cpp), a roll the same way on every cross moved the whole
// screen, about a pixel for every ten counts: 100 counts came out as 9.8 px, 200 as 19.5.
//
// Taken together the pair is exact, however noisy the moment is. The driver reports one filtered reading and
// derives the screen point from it (components/xpt2046/touchscreen/xpt2046.cpp: add_raw_touch_position_ is fed
// filter_.x()/filter_.y(), which is what filtered_raw_x() returns), so the two halves of one instant are two
// views of the same number. `fit` uses the pair only to learn what the chain from panel to glass does, and noise
// that is in both halves cancels there. Which instant is kept therefore hardly matters; the tap keeps the last
// one, which is the reading the wizard has always measured against.
inline Point last_screen, last_raw;
inline bool held = false;
inline uint8_t touch_id = 0;
inline esphome::ESPPreferenceObject preference;
inline std::function<void(const Calibration &)> apply;
inline std::function<void(bool)> isolation;
// The wizard's steps live in cyd_calibration.cpp, a compilation unit of its own (firmware 0.44.0): every header of
// this component lands in main.cpp, and on Xtensa an instruction reaches its literal only 256 KB back, which the
// CYD's main.cpp had outgrown with these at its end (page_receiver.cpp says how that first broke).
void prompt(const char *message = nullptr);
void begin();
void setup(lv_obj_t *home_screen, const lv_font_t *font, const lv_font_t *large,
           int xmin, int xmax, int ymin, int ymax);
// One reading of the finger that is down: where the screen put it and what the panel sent, at the same instant.
void hold(int id, int screen_x, int screen_y, int raw_x, int raw_y);
void press(int id, int screen_x, int screen_y, int raw_x, int raw_y);
// The middle of three taps, as one tap (cyd_calibration.cpp says why it is one tap and not a median per axis).
unsigned middle_of(const std::array<Point,3> &three);
void release();
}
