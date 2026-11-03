// The doorbell on the glass (module doorbell, tier full; docs/DOORBELL.md): someone rings, the screen wakes, chimes and
// opens the doorbell's camera full screen, live with its sound. What the module's header promises, on the camera full view
// of runtime_tiles.h (camera_open), which builds the view and streams it; this file gives it the doorbell's parts.
//
// The view: the doorbell's disc where the back key stands, its name and how long ago it rang beside it, the close key at
// the right; the picture in the room under that bar, beside the keys on glass lying down and above them on glass that is
// square or stands up. The keys: Door when the ring has one (doorbell_door.h: two taps open its lock or its action, which
// ESP Screens performs), Talk where the screen has a microphone (not yet, grey: PLATFORM_PLAN.md 5) and Sound where it
// has a speaker (hw::caps); one above the other beside the picture, or side by side under it. Nothing of LVGL lies over that room: a live picture is written to the glass past LVGL
// (live_view.h), so a key over it would be painted over 15 times a second.
//
// A ring stays open while someone looks: the first touch says "answered" (ESP Screens then closes it on the other screens),
// and it closes ANSWERED_MS after the last touch or ring. Nobody touched it: it closes the ring's timeout after the last
// ring and says "missed", and the top bar shows the ring until someone opens it again.
//
// Compiled on its own, as module_vacuum_tile.cpp is: on Xtensa the literal pool of one object file must stay within
// reach of all of its code, and the full tier holds S3 boards too.
#include "esphome/core/defines.h"
#ifdef SD_MOD_DOORBELL
#include <cmath>
#include <vector>
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "runtime_tiles.h"
#include "module_doorbell.h"
#include "doorbell_door.h"
#include "hw.h"
#include "plugin_host.h"
#include "settings_screen.h"
#ifdef USE_SPEAKER
#include "plugin_sound.h"
#include "roomy.h"
#endif

namespace runtime_tiles {
namespace doorbell {

std::function<void(const std::string &, const std::string &)> report;

namespace {
const char *const TAG = "doorbell";
const char *const DOORBELL = "\U000F12E6", *const CLOSE = "\U000F0156", *const SOUND = "\U000F057E", *const SILENT = "\U000F0581";
const char *const MICROPHONE = "\U000F036C";
// Nobody touched it: it closes the ring's timeout after the last ring (the event's, a minute unless it says). Someone did:
// five minutes after the last touch or ring, as a battery doorbell stops streaming after a few minutes anyway.
constexpr uint32_t ANSWERED_MS = 300000;
uint32_t untouched_ms = 60000;
// The ring around the disc while it rings.
constexpr uint32_t RINGING_MS = 15000;

struct Ring {
  std::string camera, name, key;
  uint32_t rang = 0;  // unix time, 0 when the app did not say
  unsigned door = 0;  // the op's `d` (doorbell_door::kind_of)
  std::string door_state;
  bool quiet = false;  // its view opens with Sound off (the automation's `sound: false`)
  std::string link;    // the stream the app made for this screen as the event came (the op's `l`), or empty
};
Ring now_ring, last_ring;  // the ring on the glass, and the last one this screen showed (the top bar opens it again)
bool active = false, touched = false, ended = false;
uint32_t ring_ms = 0, touch_ms = 0;
live_view::Rect room{};
lv_obj_t *disc = nullptr, *halo = nullptr, *note = nullptr, *sound_key = nullptr, *sound_icon = nullptr, *sound_text = nullptr;
std::string note_said;
// The door key of the ring on the glass, and what it shows now (painted again only when that changes).
doorbell_door::Door door;
lv_obj_t *door_key = nullptr, *door_icon = nullptr, *door_text = nullptr, *door_line = nullptr;
doorbell_door::Look door_shown{};
std::string door_line_said;
// Where pill() put the door key's word: its left, and its top with a line under it and without one, so a new line
// moves it up or down and never sideways.
int door_word_x = 0, door_word_top = 0, door_word_alone = 0;

void say(const char *what) {
  ESP_LOGI(TAG, "%s (%s)", what, now_ring.camera.c_str());
  if (report) report(what, now_ring.key);
}

// A finger on the view: the first says the ring is answered, every one keeps it open.
void touch() {
  touch_ms = esphome::millis();
  if (!active || touched) return;
  touched = true;
  say("answered");
}

// ---- The chime: two notes of a door chime, a bell's partials dying away, made once at 16 kHz ----
#ifdef USE_SPEAKER
esphome::speaker::Speaker *speaker = nullptr;
tessera::SoundPlayer player;
tessera::Sound chime_sound;
// In PSRAM (roomy.h): 60 KB, made at the first ring, when a full screen may have no block that large inside the chip. A
// plain vector there aborted a Tab5 with nine plugins and six pages at its first ring (TR-YVP7YV, 2026-10-25). Only the
// sound player reads it, through the speaker's copy.
roomy::List<int16_t> chime_samples;

void make_chime() {
  constexpr int RATE = 16000;
  constexpr float LENGTH = 1.9f, SECOND = 0.55f, DECAY = 0.42f, ATTACK = 0.006f;
  constexpr float NOTES[2] = {659.25f, 523.25f};  // E5, then C5
  constexpr float PARTIALS[3][2] = {{1.0f, 1.0f}, {2.0f, 0.32f}, {3.0f, 0.1f}};
  chime_samples.assign(static_cast<size_t>(LENGTH * RATE), 0);
  for (size_t i = 0; i < chime_samples.size(); ++i) {
    const float t = static_cast<float>(i) / RATE;
    float sum = 0;
    for (int n = 0; n < 2; ++n) {
      const float u = t - n * SECOND;
      if (u < 0) continue;
      const float envelope = std::min(1.0f, u / ATTACK) * std::exp(-u / DECAY);
      for (const auto &p : PARTIALS) sum += p[1] * envelope * std::sin(2.0f * static_cast<float>(M_PI) * NOTES[n] * p[0] * u);
    }
    chime_samples[i] = static_cast<int16_t>(std::max(-1.0f, std::min(1.0f, sum * 0.33f)) * 32767.0f);
  }
  chime_sound.data = reinterpret_cast<const uint8_t *>(chime_samples.data());
  chime_sound.length = chime_samples.size() * sizeof(int16_t);
  chime_sound.rate = RATE;
  chime_sound.channels = 1;
}
#endif

void chime() {
#ifdef USE_SPEAKER
  if (!speaker) return;
  if (chime_samples.empty()) make_chime();
  player.play(chime_sound);
#endif
}

// ---- The view's parts ----
const lv_font_t *title_font() { return watch_font ? watch_font : detail_font; }

// Where everything goes, from the bar's sizes (detail_bar) and the glass: the picture as large as a doorbell's 4:3 picture
// can be beside the keys on glass lying down, and over them on glass that is square or stands up.
struct Plan {
  live_view::Rect picture;
  int keys_x, keys_y, keys_w, key_h, gap;
  bool column;  // the keys one above the other beside the picture, else side by side under it
};
Plan plan() {
  const auto m = detail_bar::metrics();
  const int w = overlay_card::screen_width(), h = overlay_card::screen_height();
  const int top = detail_bar::bottom() + m.gap, key_h = std::max(ui::touch_min(), m.key * 135 / 100);
  Plan p{};
  p.key_h = key_h;
  p.gap = m.gap;
  p.column = w * 10 > h * 12;
  if (p.column) {
    const int high = h - top - m.y;
    int wide = high * 4 / 3, column = w - 3 * m.x - wide;
    if (column < m.key * 4) { column = m.key * 4; wide = w - 3 * m.x - column; }
    p.picture = {m.x, top, wide, high};
    p.keys_x = 2 * m.x + wide;
    p.keys_w = column;
  } else {
    p.picture = {m.x, top, w - 2 * m.x, h - top - m.y - m.gap - key_h};
    p.keys_x = m.x;
    p.keys_w = w - 2 * m.x;
  }
  p.keys_y = h - m.y - key_h;
  return p;
}
// Key `i` of `n`, the first at the top of the column or at the left of the row, the last (Sound) where it always stood.
live_view::Rect slot(const Plan &p, int i, int n) {
  if (p.column) return {p.keys_x, p.keys_y - (n - 1 - i) * (p.key_h + p.gap), p.keys_w, p.key_h};
  const int each = std::max(1, (p.keys_w - (n - 1) * p.gap) / n);
  return {p.keys_x + i * (each + p.gap), p.keys_y, each, p.key_h};
}

void paint_sound() {
  if (!sound_key) return;
  const bool on = !camera_muted;
  lv_obj_set_style_bg_color(sound_key, theme::color(on ? theme::ACCENT : theme::CAMERA_TRACK), 0);
  lv_obj_set_style_bg_color(sound_key, theme::color(on ? theme::ACCENT_PRESSED : theme::KEY_PRESSED), LV_STATE_PRESSED);
  lv_label_set_text(sound_icon, on ? SOUND : SILENT);
  lv_label_set_text(sound_text, screen_text::tr(on ? screen_text::txt::doorbell_sound_on : screen_text::txt::doorbell_sound_off));
}

// Where a key's word starts: its glyph a padding in from the left, the word a quarter of the key's height after it.
int word_at(int key_h) {
  const int glyph = mini_icon_font ? lv_font_get_line_height(mini_icon_font) : key_h / 2;
  return key_h * 42 / 100 + glyph + key_h / 4;
}

// The tops of a key's word and of the line under it, the two on the key's middle a little apart; and the word's top alone.
struct Rows { int top, line, alone; };
Rows two_rows(int key_h) {
  const lv_font_t *word = title_font();
  const int high = word ? lv_font_get_line_height(word) : key_h / 3;
  const int low = detail_font ? lv_font_get_line_height(detail_font) : high / 2, gap = std::max(1, low / 6);
  const int top = (key_h - high - gap - low) / 2;
  return {top, top + high + gap, (key_h - high) / 2};
}

// A key of the view: a pill as wide as its place, its glyph and its word at the left, as the keys of a card are; with
// `line`, a smaller line under the word (the door's state, Talk's "Coming soon").
lv_obj_t *pill(lv_obj_t *root, const live_view::Rect &at, lv_obj_t *&icon, lv_obj_t *&text, lv_obj_t **line = nullptr) {
  auto *key = lv_obj_create(root);
  lv_obj_remove_style_all(key);
  lv_obj_set_pos(key, at.x, at.y);
  lv_obj_set_size(key, at.w, at.h);
  lv_obj_remove_flag(key, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(key, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_radius(key, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(key, LV_OPA_COVER, 0);
  // The glyph a padding in from the left, the word a quarter of the key's height after it, both on its middle line
  // (this LVGL has no flex layout).
  const int pad = at.h * 42 / 100, word_x = word_at(at.h);
  icon = lv_label_create(key);
  if (mini_icon_font) lv_obj_set_style_text_font(icon, mini_icon_font, 0);
  lv_obj_align(icon, LV_ALIGN_LEFT_MID, pad, 0);
  text = lv_label_create(key);
  // The word in the name's font, readable from a step back, as large as the doorbell's name.
  const lv_font_t *word = title_font();
  if (word) lv_obj_set_style_text_font(text, word, 0);
  lv_label_set_long_mode(text, LV_LABEL_LONG_DOT);
  lv_obj_set_width(text, std::max(1, at.w - word_x - pad));
  lv_obj_align(text, LV_ALIGN_LEFT_MID, word_x, 0);
  for (auto *part : {icon, text}) {
    lv_obj_remove_flag(part, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_text_color(part, theme::color(theme::ON_ACCENT), 0);
  }
  if (line) {
    // The word and the line together on the key's middle, a sixth of the line's height apart, the line in the card's
    // detail font. Placed from the key's top: offsets from its middle left the line on the word (2026-10-28, a photo).
    *line = lv_label_create(key);
    if (detail_font) lv_obj_set_style_text_font(*line, detail_font, 0);
    lv_label_set_long_mode(*line, LV_LABEL_LONG_DOT);
    lv_obj_set_width(*line, std::max(1, at.w - word_x - pad));
    lv_obj_remove_flag(*line, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_text_color(*line, theme::color(theme::ON_ACCENT), 0);
    const auto rows = two_rows(at.h);
    lv_obj_align(text, LV_ALIGN_TOP_LEFT, word_x, rows.top);
    lv_obj_align(*line, LV_ALIGN_TOP_LEFT, word_x, rows.line);
  }
  return key;
}

// The door key as the door is now (doorbell_door::look): its colour, glyph and line, painted when one of them changed.
void paint_door(uint32_t now) {
  if (!door_key) return;
  using doorbell_door::Line;
  const auto look = doorbell_door::look(door, now, theme::hex(theme::CAMERA_TRACK));
  std::string line;
  if (look.line == Line::STATE) line = door.state == "unavailable" ? screen_text::tr(screen_text::txt::ha_unavailable) : lock_state_text(door.state);
  else if (look.line == Line::TAP_AGAIN) line = screen_text::tr(screen_text::txt::doorbell_door_confirm);
  else if (look.line == Line::UNLOCKING) line = screen_text::tr(screen_text::txt::ha_lock_unlocking);
  else if (look.line == Line::SENT) line = screen_text::tr(screen_text::txt::doorbell_door_sent);
  if (look.color == door_shown.color && look.glyph == door_shown.glyph && line == door_line_said) return;
  door_shown = look;
  door_line_said = line;
  const uint32_t bg = theme::state(look.color);
  lv_obj_set_style_bg_color(door_key, lv_color_hex(bg), 0);
  lv_obj_set_style_bg_color(door_key, lv_color_hex(theme::key_pressed(bg)), LV_STATE_PRESSED);
  lv_label_set_text(door_icon, look.glyph);
  lv_label_set_text(door_line, line.c_str());
  // Without a line (an action's key at rest) the word stands on the key's middle.
  lv_obj_align(door_text, LV_ALIGN_TOP_LEFT, door_word_x, line.empty() ? door_word_alone : door_word_top);
  if (line.empty()) lv_obj_add_flag(door_line, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_remove_flag(door_line, LV_OBJ_FLAG_HIDDEN);
}
}  // namespace

void bind_speaker(esphome::speaker::Speaker *s) {
#ifdef USE_SPEAKER
  speaker = s;
  player.set_speaker(s);
#else
  (void) s;
#endif
}

bool shown() { return active; }
bool holds() { return active && camera_root != nullptr; }
live_view::Rect area() { return room; }

void build(lv_obj_t *root, const std::string &name) {
  const auto p = plan();
  room = p.picture;
  const auto home = detail_bar::back_slot(root);
  const auto m = detail_bar::metrics();
  // The disc where the back key stands, in the doorbell's amber, with a ring around it while it rings.
  halo = lv_obj_create(root);
  lv_obj_remove_style_all(halo);
  const int grow = home.h * 13 / 100;
  lv_obj_set_pos(halo, home.x - grow, home.y - grow);
  lv_obj_set_size(halo, home.w + 2 * grow, home.h + 2 * grow);
  lv_obj_set_style_radius(halo, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_border_color(halo, theme::color(theme::MARK_AMBER), 0);
  lv_obj_set_style_border_width(halo, std::max(2, ui::px(3)), 0);
  lv_obj_set_style_border_opa(halo, LV_OPA_60, 0);
  lv_obj_remove_flag(halo, LV_OBJ_FLAG_CLICKABLE);
  disc = lv_obj_create(root);
  lv_obj_remove_style_all(disc);
  lv_obj_set_pos(disc, home.x, home.y);
  lv_obj_set_size(disc, home.w, home.h);
  lv_obj_set_style_radius(disc, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(disc, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(disc, theme::color(theme::MARK_AMBER), 0);
  lv_obj_remove_flag(disc, LV_OBJ_FLAG_CLICKABLE);
  auto *glyph = lv_label_create(disc);
  if (detail_bar::icon_font) lv_obj_set_style_text_font(glyph, detail_bar::icon_font, 0);
  lv_obj_set_style_text_color(glyph, theme::color(theme::CAMERA_PAGE), 0);  // black on amber in both looks
  lv_label_set_text(glyph, DOORBELL);
  lv_obj_center(glyph);
  // The name and, under it, how long ago it rang, left of the keys at the right.
  const auto close_at = detail_bar::right_slot(root, 0), spin_at = detail_bar::right_slot(root, 1);
  const int left = home.x + home.w + m.gap * 3 / 2, width = std::max(1, spin_at.x - m.gap - left);
  const lv_font_t *big = title_font();
  const int line = big ? lv_font_get_line_height(big) : home.h / 2, small = detail_font ? lv_font_get_line_height(detail_font) : line / 2;
  const int y = home.y + std::max(0, (home.h - line - small) / 2);
  camera_title = lv_label_create(root);
  if (big) lv_obj_set_style_text_font(camera_title, big, 0);
  lv_obj_set_style_text_color(camera_title, theme::color(theme::CAMERA_INK), 0);
  lv_label_set_long_mode(camera_title, LV_LABEL_LONG_DOT);
  lv_obj_set_pos(camera_title, left, y);
  lv_obj_set_size(camera_title, width, line);
  lv_label_set_text(camera_title, name.c_str());
  note = lv_label_create(root);
  if (detail_font) lv_obj_set_style_text_font(note, detail_font, 0);
  lv_obj_set_style_text_color(note, theme::color(theme::CAMERA_NOTE), 0);
  lv_label_set_long_mode(note, LV_LABEL_LONG_DOT);
  lv_obj_set_pos(note, left, y + line);
  lv_obj_set_size(note, width, small);
  note_said.clear();
  // The close key at the right, where a card's key at the right stands.
  detail_bar::key(root, close_at, CLOSE, [](lv_event_t *) {
    // Closed by a finger is answered too: ESP Screens closes it on the other screens.
    if (active && !ended) { touched = ended = true; say("closed"); }
    lv_async_call([](void *) { camera_close(); }, nullptr);
  });
  // The keys: Door when the ring has one, Talk where the screen hears (not yet), Sound where it plays; a key it cannot
  // use is not there at all.
  const bool has_door = door.kind != doorbell_door::Kind::NONE, hears = hw::caps().microphone, plays = hw::caps().speaker;
  const int keys = has_door + hears + plays;
  int at = 0;
  if (has_door) {
    // Two taps open the door (doorbell_door.h); the second says "door", and ESP Screens performs it.
    door_shown = {};
    door_line_said = "-";
    const auto door_at = slot(p, at++, keys);
    door_key = pill(root, door_at, door_icon, door_text, &door_line);
    door_word_x = word_at(door_at.h);
    door_word_top = two_rows(door_at.h).top;
    door_word_alone = two_rows(door_at.h).alone;
    lv_label_set_text(door_text, screen_text::tr(screen_text::txt::doorbell_door));
    lv_obj_add_event_cb(door_key, [](lv_event_t *) {
      touch();
      const uint32_t now = esphome::millis();
      if (door.tap(now)) say("door");
      paint_door(now);
    }, LV_EVENT_SHORT_CLICKED, nullptr);
    paint_door(esphome::millis());
  }
  if (hears) {
    // Talk: the doorbell's own speaker, which Home Assistant does not offer yet (PLATFORM_PLAN.md 5). Grey, and a tap on
    // it only counts as a touch of the view.
    lv_obj_t *icon = nullptr, *text = nullptr, *line = nullptr;
    auto *talk = pill(root, slot(p, at++, keys), icon, text, &line);
    lv_obj_set_style_bg_color(talk, theme::color(theme::CAMERA_TRACK), 0);
    lv_obj_remove_flag(talk, LV_OBJ_FLAG_CLICKABLE);
    lv_label_set_text(icon, MICROPHONE);
    lv_label_set_text(text, screen_text::tr(screen_text::txt::doorbell_talk));
    lv_label_set_text(line, screen_text::tr(screen_text::txt::doorbell_coming_soon));
    for (auto *part : {icon, text, line}) lv_obj_set_style_text_color(part, theme::color(theme::CAMERA_NOTE), 0);
  }
  if (plays) {
    // Sound, on at a ring unless its automation says it opens quiet: a tap turns it on or off, as the sound key of the
    // camera's view does.
    sound_key = pill(root, slot(p, at, keys), sound_icon, sound_text);
    lv_obj_add_event_cb(sound_key, [](lv_event_t *) {
      touch();
      camera_muted = !camera_muted;
      live_view::mute(camera.stream.handle, camera_muted);
      paint_sound();
    }, LV_EVENT_SHORT_CLICKED, nullptr);
    paint_sound();
  }
  // A finger anywhere on the view keeps it open and answers it.
  lv_obj_add_event_cb(root, [](lv_event_t *) { touch(); }, LV_EVENT_PRESSED, nullptr);
  // The camera's note and its first spinner in the middle of the picture's room, not of the glass.
  if (camera_note) lv_obj_align(camera_note, LV_ALIGN_TOP_LEFT, room.x + room.w / 2 - lv_obj_get_width(camera_note) / 2, room.y + room.h / 2);
  if (camera_spinner) {
    lv_obj_update_layout(camera_spinner);
    const int s = lv_obj_get_width(camera_spinner);
    lv_obj_align(camera_spinner, LV_ALIGN_TOP_LEFT, room.x + (room.w - s) / 2, room.y + (room.h - s) / 2);
  }
  tick(esphome::millis());
}

void picture_shown(lv_obj_t *picture) {
  if (!picture) return;
  const auto *src = static_cast<const lv_image_dsc_t *>(lv_image_get_src(picture));
  if (!src) return;
  const int w = src->header.w, h = src->header.h;
  lv_obj_align(picture, LV_ALIGN_TOP_LEFT, room.x + (room.w - w) / 2, room.y + (room.h - h) / 2);
  lv_obj_move_background(picture);
}

void sound_changed() { paint_sound(); }

void spinner_place(lv_obj_t *spinner, int size) {
  if (!spinner || !camera_root) return;
  const auto slot = detail_bar::right_slot(camera_root, 1);
  lv_obj_set_pos(spinner, slot.x + (slot.w - size) / 2, slot.y + (slot.h - size) / 2);
}

void closing() {
  if (!active) return;
  if (!ended) { ended = true; say("closed"); }
  active = false;
  disc = halo = note = sound_key = sound_icon = sound_text = nullptr;  // they go with the view
  door_key = door_icon = door_text = door_line = nullptr;
  room = {};
}

void tick(uint32_t now) {
#ifdef USE_SPEAKER
  player.loop();
#endif
  if (!active || !camera_root) return;
  paint_door(now);  // the end of a "tap again", of "Sent", of the wait for the lock's new state
  // How long ago it rang, in the top bar's words ("Just now", "2 min ago"), from the app's moment.
  if (note) {
    // A screen's clock a few seconds behind Home Assistant's never says the ring is still to come.
    const uint32_t now_s = now_epoch();
    const std::string text = header_bar::ago_text(now_s && now_ring.rang > now_s ? now_s : now_ring.rang, now_s);
    if (text != note_said) { note_said = text; lv_label_set_text(note, text.c_str()); }
  }
  if (halo) {
    const bool ringing = now - ring_ms < RINGING_MS;
    if (ringing == lv_obj_has_flag(halo, LV_OBJ_FLAG_HIDDEN)) {
      if (ringing) lv_obj_remove_flag(halo, LV_OBJ_FLAG_HIDDEN);
      else lv_obj_add_flag(halo, LV_OBJ_FLAG_HIDDEN);
    }
  }
  if (!touched && now - ring_ms > untouched_ms) {
    ended = true;
    say("missed");
    camera_close();
  } else if (touched && now - std::max(ring_ms, touch_ms) > ANSWERED_MS) {
    ended = true;
    camera_close();
  }
}

// The door of a ring onto the key: what it is and its lock's state, waiting for nothing.
void take_door(const Ring &r) {
  door = doorbell_door::Door{};
  door.kind = doorbell_door::kind_of(r.door);
  door.set_state(r.door_state);
}

void ring(const std::string &camera_entity, const std::string &name, const std::string &key, uint32_t rang, uint32_t untouched_s,
          unsigned door_kind, const std::string &door_state_now, bool quiet, bool chimes, const std::string &link) {
  if (!camera_supported() || camera_entity.rfind("camera.", 0) != 0 || !valid_entity(camera_entity)) return;
  const uint32_t now = esphome::millis();
  ring_ms = now;
  untouched_ms = std::max<uint32_t>(10, std::min<uint32_t>(600, untouched_s ? untouched_s : 60)) * 1000;
  if (active && camera_root && camera.entity == camera_entity &&
      doorbell_door::kind_of(door_kind) == door.kind) {
    // It rings again while it shows (and with the same door): the chime again, the moment it rang, its ring around the disc.
    now_ring.key = key;
    now_ring.rang = rang;
    now_ring.door = door_kind;
    now_ring.door_state = door_state_now;
    door.set_state(door_state_now);
    last_ring = now_ring;
    ended = false;
    if (chimes) chime();
    tick(now);
    return;
  }
  // Out of standby and Sleep, over any card, the settings page, a camera or another ring.
  if (plugin_host::wake) plugin_host::wake("doorbell");
  settings_screen::close();
  camera_close();
  camera_muted = quiet;  // a ring is to be heard, unless its automation says the screen stands somewhere quiet
  now_ring = last_ring = Ring{camera_entity, name, key, rang, door_kind, door_state_now, quiet, link};
  take_door(now_ring);
  active = true;
  touched = ended = false;
  touch_ms = 0;
  camera_open(camera_entity, name);  // its stream at once when the app made one (link()), else the view asks
  if (!camera_root) { active = false; return; }
  // The ring's view claims the speaker as DOORBELL when its stream opens (runtime_tiles live_begin, audio_owner.h): music
  // pauses, a camera's sound and the voice assistant step back, and nothing takes it from a ring. The chime itself goes
  // through the announcement input and mixes; an automation with `chime: false` rings without it.
  if (chimes) chime();
}

void door_state(const std::string &key, const std::string &state) {
  if (last_ring.key == key) last_ring.door_state = state;
  if (now_ring.key != key) return;
  now_ring.door_state = state;
  door.set_state(state);
  if (active) paint_door(esphome::millis());
}

void close_ring(const std::string &key) {
  if (!active || now_ring.key != key) return;
  ESP_LOGI(TAG, "answered on another screen");
  ended = true;  // the screen that answered said so
  camera_close();
}

const std::string &link() { return now_ring.link; }

void reopen() {
  if (last_ring.camera.empty() || !camera_supported()) return;
  camera_close();
  now_ring = last_ring;
  now_ring.link.clear();  // minutes later its stream may be gone: the view asks for one
  take_door(now_ring);
  camera_muted = now_ring.quiet;
  active = true;
  touched = true;
  ended = false;
  ring_ms = esphome::millis() - RINGING_MS;  // opened by a finger: no ring around the disc
  touch_ms = esphome::millis();
  camera_open(now_ring.camera, now_ring.name);
  if (!camera_root) { active = false; return; }
  say("seen");
}

}  // namespace doorbell
}  // namespace runtime_tiles
#endif
