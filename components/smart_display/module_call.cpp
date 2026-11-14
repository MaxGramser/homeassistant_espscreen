// Calls between screens on the glass (module call, tier full; docs/CALLS.md). What its header promises; compiled on its
// own, as module_doorbell.cpp is. The looks follow the study of 2026-11-10: a dark ground, a disc with the screen's icon,
// the name, and round keys; a key that is off is white with dark ink.
#include "esphome/core/defines.h"
#ifdef SD_MOD_CALL
#include <algorithm>
#include <cmath>
#include <vector>
#include <ArduinoJson.h>
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "runtime_tiles.h"
#include "module_call.h"
#include "hw.h"
#include "plugin_host.h"
#include "settings_screen.h"
#include "talk_uplink.h"
#ifdef USE_SPEAKER
#include "plugin_sound.h"
#include "roomy.h"
#endif

namespace runtime_tiles {
namespace call {

std::function<void(const std::string &, const std::string &, bool, const std::string &)> report;
std::function<float()> volume_get;
std::function<void(float)> volume_set;
std::function<bool()> ring_on;
float ring_top = 1.0f;

namespace {
const char *const TAG = "call";
const char *const PHONE = "\U000F03F2", *const HANGUP = "\U000F03F5", *const VIDEO = "\U000F0567", *const VIDEO_OFF = "\U000F0568";
const char *const MIC = "\U000F036C", *const MIC_OFF = "\U000F036D", *const SPEAKER = "\U000F057E", *const SILENT = "\U000F0581";
const char *const CLOSE = "\U000F0156", *const MISSED = "\U000F03FA";
const char *const FAKE_CAMERA = "camera.tessera_call";
constexpr uint32_t CLAIM_ID = 78, END_SHOWN_MS = 2500, RING_EVERY_MS = 3000, RING_GONE_MS = 60000;
// A key's disc a quarter larger than a tile's circle, on a dark ground (the study's key_d).
int key_d() { return std::max(ui::touch_min(), detail_bar::metrics().key * 5 / 4); }

enum class Stage : uint8_t { NONE, OUT, RING, LIVE, ENDED };
Stage stage = Stage::NONE;
std::string call_key, peer_name, peer_icon, stream_link, talk_link, end_why;
bool with_video = false, peer_films = true, mic_off = false, camera_off = false, on_hold = false;
uint32_t live_since = 0, end_at = 0, last_ring = 0, ring_since = 0;
// The call that is not on the camera's view: going out, coming in, how it ended. On the top layer.
lv_obj_t *card = nullptr, *list = nullptr;
lv_obj_t *timer_label = nullptr, *mic_key = nullptr, *mic_glyph = nullptr, *speaker_key = nullptr, *speaker_glyph = nullptr,
         *camera_key_obj = nullptr, *camera_glyph = nullptr;
std::string timer_said;
live_view::Rect room{};

uint32_t red() { return theme::ha::RED; }
uint32_t green() { return theme::ha::GREEN; }
const lv_font_t *title_font() { return watch_font ? watch_font : detail_font; }

void say(const char *action, const std::string &to = "", bool video = false) {
  ESP_LOGI(TAG, "%s %s", action, to.c_str());
  if (report) report(action, to, video, call_key);
}

#ifdef USE_SPEAKER
esphome::speaker::Speaker *speaker_out = nullptr;
tessera::SoundPlayer player;
tessera::Sound ring_sound;
// While it rings the speaker's volume stands at the top; ring_stop puts back what it was, from one place.
float ring_volume_restore = -1.0f;
roomy::List<int16_t> ring_samples;
void make_ring() {
  // Two bursts of a bright two-tone ring at full scale, made once at 16 kHz. Bright on purpose: these small speakers carry 1.4 to
  // 1.9 kHz best, and 523 Hz at a quarter of full scale could not be heard at half volume (a reTerminal D1001, 2026-11-10).
  constexpr int RATE = 16000;
  constexpr float LENGTH = 1.1f, LOW = 1400.0f, HIGH = 1900.0f, BURST = 0.42f, GAP = 0.56f;
  ring_samples.assign(static_cast<size_t>(LENGTH * RATE), 0);
  for (size_t i = 0; i < ring_samples.size(); ++i) {
    const float t = static_cast<float>(i) / RATE;
    const float u = t < GAP ? t : t - GAP;
    if (u > BURST) continue;
    const float edge = std::min(std::min(u, BURST - u) / 0.012f, 1.0f);
    const float s = std::sin(2.0f * static_cast<float>(M_PI) * LOW * t) + std::sin(2.0f * static_cast<float>(M_PI) * HIGH * t);
    ring_samples[i] = static_cast<int16_t>(edge * s * 0.49f * 32767.0f);
  }
  ring_sound.data = reinterpret_cast<const uint8_t *>(ring_samples.data());
  ring_sound.length = ring_samples.size() * sizeof(int16_t);
  ring_sound.rate = RATE;
  ring_sound.channels = 1;
}
void ring_stop() {
  player.stop();
  if (ring_volume_restore >= 0.0f && volume_set) volume_set(ring_volume_restore);
  ring_volume_restore = -1.0f;
}
void ring_once() {
  if (ring_on && !ring_on()) return;
  if (!speaker_out) { ESP_LOGW(TAG, "no speaker for the ring"); return; }
  if (ring_samples.empty()) make_ring();
  ESP_LOGI(TAG, "ringing");
  player.play(ring_sound);
}
#else
void ring_once() {}
void ring_stop() {}
#endif

void claim_audio() {
  audio_owner::Claim claim;
  claim.role = audio_owner::Role::CALL;
  claim.id = CLAIM_ID;
  claim.lost = []() { ring_stop(); };  // a doorbell's ring takes the speaker: this ring's volume goes back at once
  audio_owner::the().claim(audio_owner::Side::BOTH, claim);
}
void release_audio() { audio_owner::the().release(audio_owner::Side::BOTH, audio_owner::Role::CALL, CLAIM_ID); }

lv_obj_t *plain(lv_obj_t *parent) {
  auto *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  return o;
}

// A disc with a glyph on its middle.
lv_obj_t *disc(lv_obj_t *parent, int x, int y, int d, uint32_t fill, const char *glyph, const lv_font_t *font, uint32_t ink, lv_obj_t **label = nullptr) {
  auto *o = plain(parent);
  lv_obj_set_pos(o, x, y);
  lv_obj_set_size(o, d, d);
  lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(o, lv_color_hex(fill), 0);
  auto *g = lv_label_create(o);
  if (font) lv_obj_set_style_text_font(g, font, 0);
  lv_obj_set_style_text_color(g, lv_color_hex(ink), 0);
  lv_label_set_text(g, glyph);
  lv_obj_center(g);
  if (label) *label = g;
  return o;
}

lv_obj_t *round_key(lv_obj_t *parent, int x, int y, int d, uint32_t fill, const char *glyph, lv_event_cb_t cb, lv_obj_t **label = nullptr) {
  auto *o = disc(parent, x, y, d, fill, glyph, mini_icon_font, theme::hex(theme::ON_ACCENT), label);
  lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_color(o, lv_color_hex(theme::key_pressed(fill)), LV_STATE_PRESSED);
  lv_obj_add_event_cb(o, cb, LV_EVENT_SHORT_CLICKED, nullptr);
  return o;
}

lv_obj_t *text(lv_obj_t *parent, const std::string &words, const lv_font_t *font, uint32_t ink, int y) {
  auto *l = lv_label_create(parent);
  if (font) lv_obj_set_style_text_font(l, font, 0);
  lv_obj_set_style_text_color(l, lv_color_hex(ink), 0);
  lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0);
  lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
  lv_obj_set_width(l, overlay_card::screen_width() - 2 * detail_bar::metrics().x);
  lv_label_set_text(l, words.c_str());
  lv_obj_align(l, LV_ALIGN_TOP_MID, 0, y);
  return l;
}

void free_card() {
  if (card) lv_obj_delete(card);
  card = nullptr;
}

lv_obj_t *new_card() {
  free_card();
  card = plain(lv_layer_top());
  lv_obj_set_size(card, lv_pct(100), lv_pct(100));
  lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(card, theme::color(theme::CAMERA_PAGE), 0);
  lv_obj_add_flag(card, LV_OBJ_FLAG_CLICKABLE);  // nothing reaches the tiles below
  return card;
}

const char *disc_glyph() { return peer_icon.empty() ? PHONE : peer_icon.c_str(); }

// The disc, the name and a line, on the middle of the upper part of the glass.
void who(lv_obj_t *root, const std::string &line, bool rings) {
  const int h = overlay_card::screen_height(), w = overlay_card::screen_width();
  const int d = ui::px(ui::large() ? 150 : 84), cy = h * 36 / 100;
  if (rings) {
    for (int i = 2; i >= 1; --i) {
      const int r = d + i * d * 2 / 5;
      auto *ring = plain(root);
      lv_obj_set_pos(ring, w / 2 - r / 2, cy - r / 2);
      lv_obj_set_size(ring, r, r);
      lv_obj_set_style_radius(ring, LV_RADIUS_CIRCLE, 0);
      lv_obj_set_style_bg_opa(ring, i == 2 ? 28 : 56, 0);
      lv_obj_set_style_bg_color(ring, lv_color_hex(green()), 0);
    }
  }
  disc(root, w / 2 - d / 2, cy - d / 2, d, theme::hex(theme::CAMERA_TRACK), disc_glyph(), big_icon_font ? big_icon_font : mini_icon_font, theme::hex(theme::ON_ACCENT));
  const lv_font_t *big = title_font();
  const int y = cy + d / 2 + d / 4 + (rings ? d / 3 : 0);
  text(root, peer_name, big, theme::hex(theme::CAMERA_INK), y);
  text(root, line, detail_font, theme::hex(theme::CAMERA_NOTE), y + (big ? lv_font_get_line_height(big) : 28) + ui::px(4));
}

// ---- Going out, coming in, how it ended ----
void hang_up_cb(lv_event_t *) {
  say(stage == Stage::RING ? "decline" : stage == Stage::OUT ? "cancel" : "end");
}
void answer_cb(lv_event_t *) { say("answer"); }

void show_out() {
  auto *root = new_card();
  who(root, screen_text::tr(with_video ? screen_text::txt::call_calling_video : screen_text::txt::call_calling), false);
  const int d = key_d() * 4 / 3, w = overlay_card::screen_width(), h = overlay_card::screen_height();
  round_key(root, w / 2 - d / 2, h - d - detail_bar::metrics().y * 2, d, red(), HANGUP, hang_up_cb);
}

void labelled_key(lv_obj_t *root, int cx, int cy, int d, uint32_t fill, const char *glyph, const char *word, lv_event_cb_t cb) {
  round_key(root, cx - d / 2, cy - d / 2, d, fill, glyph, cb);
  auto *l = lv_label_create(root);
  if (detail_font) lv_obj_set_style_text_font(l, detail_font, 0);
  lv_obj_set_style_text_color(l, theme::color(theme::CAMERA_INK), 0);
  lv_label_set_text(l, word);
  lv_obj_align(l, LV_ALIGN_TOP_LEFT, 0, cy + d / 2 + ui::px(6));
  lv_obj_update_layout(l);
  lv_obj_set_x(l, cx - lv_obj_get_width(l) / 2);
}

void show_ring() {
  auto *root = new_card();
  who(root, screen_text::tr(with_video ? screen_text::txt::call_video : screen_text::txt::call_audio), true);
  const int d = key_d() * 4 / 3, w = overlay_card::screen_width(), h = overlay_card::screen_height();
  const int cy = h - d / 2 - detail_bar::metrics().y * 2 - (detail_font ? lv_font_get_line_height(detail_font) : 20);
  const int gap = w > h ? w / 6 : w / 4;
  labelled_key(root, w / 2 - gap, cy, d, red(), HANGUP, screen_text::tr(screen_text::txt::call_decline), hang_up_cb);
  labelled_key(root, w / 2 + gap, cy, d, green(), with_video ? VIDEO : PHONE, screen_text::tr(screen_text::txt::call_answer), answer_cb);
}

const char *why_text(const std::string &why) {
  using namespace screen_text::txt;
  if (why == "declined") return screen_text::tr(call_declined);
  if (why == "busy") return screen_text::tr(call_busy);
  if (why == "no_answer" || why == "missed") return screen_text::tr(call_no_answer);
  if (why == "quiet") return screen_text::tr(call_quiet);
  if (why == "gone") return screen_text::tr(call_gone);
  return screen_text::tr(call_ended);
}

void show_end() {
  auto *root = new_card();
  who(root, why_text(end_why), false);
  end_at = esphome::millis();
}

// ---- In the call: the keys ----
uint32_t on_off(bool off) { return off ? 0xFFFFFF : theme::hex(theme::CAMERA_TRACK); }

void paint_keys() {
  const uint32_t ink = theme::hex(theme::ON_ACCENT), dark = theme::hex(theme::CAMERA_PAGE);
  if (mic_key) {
    lv_obj_set_style_bg_color(mic_key, lv_color_hex(on_off(mic_off)), 0);
    lv_label_set_text(mic_glyph, mic_off ? MIC_OFF : MIC);
    lv_obj_set_style_text_color(mic_glyph, lv_color_hex(mic_off ? dark : ink), 0);
  }
  if (speaker_key) {
    lv_obj_set_style_bg_color(speaker_key, lv_color_hex(on_off(camera_muted)), 0);
    lv_label_set_text(speaker_glyph, camera_muted ? SILENT : SPEAKER);
    lv_obj_set_style_text_color(speaker_glyph, lv_color_hex(camera_muted ? dark : ink), 0);
  }
  if (camera_key_obj) {
    lv_obj_set_style_bg_color(camera_key_obj, lv_color_hex(on_off(camera_off)), 0);
    lv_label_set_text(camera_glyph, camera_off ? VIDEO_OFF : VIDEO);
    lv_obj_set_style_text_color(camera_glyph, lv_color_hex(camera_off ? dark : ink), 0);
  }
}

void mic_cb(lv_event_t *) {
  mic_off = !mic_off;
  talk_uplink::set_muted(mic_off);
  say("mic", "", !mic_off);
  paint_keys();
}
void speaker_cb(lv_event_t *) {
  camera_muted = !camera_muted;
  live_view::mute(camera.stream.handle, camera_muted);
  paint_keys();
}
void camera_cb(lv_event_t *) {
  camera_off = !camera_off;
  say("camera", "", !camera_off);
  paint_keys();
}

// Where the keys of a call go: one column beside the picture on glass lying down, a row under it on glass that stands.
struct KeySpots { int x, y, dx, dy; };

void lay_keys(lv_obj_t *root, const KeySpots &at, int d) {
  int i = 0;
  const auto place = [&](lv_event_cb_t cb, const char *glyph, uint32_t fill, lv_obj_t **glyph_out) {
    auto *k = round_key(root, at.x + i * at.dx, at.y + i * at.dy, d, fill, glyph, cb, glyph_out);
    ++i;
    return k;
  };
  mic_key = place(mic_cb, MIC, on_off(false), &mic_glyph);
  speaker_key = place(speaker_cb, SPEAKER, on_off(false), &speaker_glyph);
  camera_key_obj = camera_glyph = nullptr;
  if (with_video) camera_key_obj = place(camera_cb, VIDEO, on_off(false), &camera_glyph);
  place(hang_up_cb, HANGUP, red(), nullptr);
  paint_keys();
}

std::string timer_text() {
  const uint32_t s = live_since ? (esphome::millis() - live_since) / 1000 : 0;
  char out[12];
  std::snprintf(out, sizeof out, "%u:%02u", (unsigned) (s / 60), (unsigned) (s % 60));
  return out;
}

void forget_view_parts() {
  timer_label = mic_key = mic_glyph = speaker_key = speaker_glyph = camera_key_obj = camera_glyph = nullptr;
  room = {};
}

void talk_up() {
  if (talk_link.empty() || talk_uplink::state() == talk_uplink::State::LIVE || talk_uplink::state() == talk_uplink::State::CONNECTING) return;
  if (!talk_uplink::start(talk_link)) ESP_LOGW(TAG, "could not start the voice");
  talk_uplink::set_muted(mic_off || on_hold);
}

void open_live_view() {
  free_card();
  claim_audio();
  talk_up();
  camera_muted = false;
  camera_close();  // whatever else fills the glass
  camera_open(FAKE_CAMERA, peer_name);
}

void leave_call() {
  talk_uplink::stop();
  on_hold = false;
  release_audio();
}

// ---- The list ----
struct Row { std::string id, name, icon, state; bool sound, video; uint32_t missed; };
std::vector<Row> rows;

void close_list() {
  if (list) lv_obj_delete(list);
  list = nullptr;
}

std::string pending_to;
bool pending_video = false;

void dial_cb(lv_event_t *e) {
  const auto index = reinterpret_cast<intptr_t>(lv_event_get_user_data(e));
  if (index < 0 || static_cast<size_t>(index) >= rows.size()) return;
  pending_to = rows[index].id;
  pending_video = lv_obj_has_flag(lv_event_get_target_obj(e), LV_OBJ_FLAG_USER_1);
  // Not from inside the key's own event: closing the list deletes the key.
  lv_async_call([](void *) {
    close_list();
    say("dial", pending_to, pending_video);
  }, nullptr);
}

const char *row_line(const Row &r) {
  using namespace screen_text::txt;
  if (r.state == "busy") return screen_text::tr(call_in_call);
  if (r.state == "quiet") return screen_text::tr(call_quiet);
  if (r.state == "offline") return screen_text::tr(call_offline);
  if (r.missed) return screen_text::tr(call_missed_at);
  return screen_text::tr(r.video ? call_available : call_sound_only);
}

void fill_list() {
  if (!list) return;
  auto *panel = lv_obj_get_child(list, 0);
  auto *body = lv_obj_get_child(panel, 2);
  lv_obj_clean(body);
  // Measured only after LVGL has laid the card out: before that it is 0 wide and at the top, and a card sized from that stays empty.
  lv_obj_update_layout(list);
  const int body_y = lv_obj_get_y(body);
  const int width = lv_obj_get_content_width(body), row_h = std::max(ui::touch_min() + ui::px(10), key_d() + ui::px(12)), d = key_d();
  int y = 0;
  if (rows.empty()) {
    // No other screen can be called: the card says so, it never stands empty.
    auto *none = lv_label_create(body);
    if (detail_font) lv_obj_set_style_text_font(none, detail_font, 0);
    lv_obj_set_style_text_color(none, theme::color(theme::OFF), 0);
    lv_label_set_long_mode(none, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(none, width);
    lv_label_set_text(none, screen_text::tr(screen_text::txt::call_no_screens));
    lv_obj_update_layout(none);
    y = lv_obj_get_height(none) + ui::px(8);
  }
  for (size_t index = 0; index < rows.size(); ++index) {
    const auto &row = rows[index];
    auto *line = plain(body);
    lv_obj_set_pos(line, 0, y);
    lv_obj_set_size(line, width, row_h);
    const bool off = row.state == "offline";
    disc(line, 0, (row_h - d) / 2, d, off ? theme::hex(theme::TRACK) : theme::hex(theme::KEY), row.icon.empty() ? PHONE : row.icon.c_str(), mini_icon_font, off ? theme::hex(theme::OFF) : theme::hex(theme::INK));
    int right = width;
    const auto key = [&](bool video) {
      right -= d;
      auto *k = disc(line, right, (row_h - d) / 2, d, theme::tint(green(), 40), video ? VIDEO : PHONE, mini_icon_font, theme::icon(green()));
      lv_obj_add_flag(k, LV_OBJ_FLAG_CLICKABLE);
      if (video) lv_obj_add_flag(k, LV_OBJ_FLAG_USER_1);
      lv_obj_add_event_cb(k, dial_cb, LV_EVENT_SHORT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(index)));
      right -= ui::px(10);
    };
    if (row.sound) key(false);
    if (row.video) key(true);
    const int left = d + ui::px(12), words = std::max(ui::px(40), right - left);
    const lv_font_t *big = title_font();
    auto *name = lv_label_create(line);
    if (big) lv_obj_set_style_text_font(name, big, 0);
    lv_obj_set_style_text_color(name, theme::color(off ? theme::OFF : theme::INK), 0);
    lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);
    lv_obj_set_width(name, words);
    lv_label_set_text(name, row.name.c_str());
    const int nh = big ? lv_font_get_line_height(big) : 24, lh = detail_font ? lv_font_get_line_height(detail_font) : 16;
    lv_obj_set_pos(name, left, (row_h - nh - lh) / 2);
    auto *note = lv_label_create(line);
    if (detail_font) lv_obj_set_style_text_font(note, detail_font, 0);
    lv_obj_set_style_text_color(note, row.missed ? lv_color_hex(theme::state(theme::ha::RED)) : theme::color(theme::OFF), 0);
    lv_label_set_long_mode(note, LV_LABEL_LONG_DOT);
    lv_obj_set_width(note, words);
    lv_label_set_text(note, row_line(row));
    lv_obj_set_pos(note, left, (row_h - nh - lh) / 2 + nh);
    y += row_h;
  }
  // The card as tall as its rows, up to the glass's own limit; more rows than that scroll.
  const int pad = std::max(0, body_y - detail_bar::metrics().y), panel_h = std::min(body_y + y + pad / 2, overlay_card::screen_height() * 86 / 100);
  lv_obj_set_height(panel, panel_h);
  lv_obj_set_height(body, std::max(1, panel_h - body_y - pad / 2));
  ESP_LOGI(TAG, "the list: %u rows, card %d high", (unsigned) rows.size(), panel_h);
  lv_obj_center(panel);
}
}  // namespace

void bind_speaker(esphome::speaker::Speaker *s) {
#ifdef USE_SPEAKER
  speaker_out = s;
  player.set_speaker(s);
#else
  (void) s;
#endif
}

void open_list() {
  close_list();
  const int w = overlay_card::screen_width(), h = overlay_card::screen_height();
  list = plain(lv_layer_top());
  lv_obj_set_size(list, lv_pct(100), lv_pct(100));
  lv_obj_set_style_bg_opa(list, LV_OPA_50, 0);
  lv_obj_set_style_bg_color(list, theme::color(theme::CAMERA_PAGE), 0);
  lv_obj_add_flag(list, LV_OBJ_FLAG_CLICKABLE);
  const int panel_w = std::min(w - ui::px(40), ui::px(ui::large() ? 640 : 460)), panel_h = std::min(h - ui::px(40), h * 86 / 100);
  auto *panel = plain(list);
  lv_obj_set_size(panel, panel_w, panel_h);
  lv_obj_center(panel);
  lv_obj_set_style_radius(panel, ui::px(ui::large() ? 28 : 18), 0);
  lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(panel, theme::color(theme::CARD), 0);
  const int pad = ui::px(ui::large() ? 24 : 14), d = key_d();
  auto *title = lv_label_create(panel);
  if (title_font()) lv_obj_set_style_text_font(title, title_font(), 0);
  lv_obj_set_style_text_color(title, theme::color(theme::INK), 0);
  lv_label_set_text(title, screen_text::tr(screen_text::txt::call_title));
  lv_obj_align(title, LV_ALIGN_TOP_LEFT, pad, pad + (d - (title_font() ? lv_font_get_line_height(title_font()) : 24)) / 2);
  auto *x = round_key(panel, panel_w - pad - d, pad, d, theme::hex(theme::KEY), CLOSE, [](lv_event_t *) { lv_async_call([](void *) { close_list(); }, nullptr); });
  lv_obj_set_style_text_color(lv_obj_get_child(x, 0), theme::color(theme::INK), 0);
  auto *body = plain(panel);
  lv_obj_set_pos(body, pad, pad + d + pad / 2);
  lv_obj_set_size(body, panel_w - 2 * pad, panel_h - pad - d - pad);
  // Thirty screens do not fit a card: the rows scroll under the title, whose close key stays.
  lv_obj_add_flag(body, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_scroll_dir(body, LV_DIR_VER);
  lv_obj_set_scrollbar_mode(body, LV_SCROLLBAR_MODE_ACTIVE);
  rows.clear();  // what the list held the last time is not drawn: the answer comes within a moment
  say("list");
}

void on_contacts(const std::string &text_rows, bool append, bool more) {
  // A house with many screens comes in parts (`p`, `more`: one message holds about a dozen rows); the list is drawn once.
  if (!append) rows.clear();
  JsonDocument doc;
  if (deserializeJson(doc, text_rows)) return;
  for (JsonObject o : doc.as<JsonArray>()) {
    Row r;
    r.id = o["id"] | "";
    r.name = o["n"] | "";
    r.icon = o["i"] | "";
    r.state = o["s"] | "free";
    r.sound = (o["a"] | 0) == 1;
    r.video = (o["v"] | 0) == 1;
    r.missed = o["m"] | 0;
    rows.push_back(r);
  }
  if (!more) fill_list();
}

void on_call(const std::string &state, const std::string &key, const std::string &name, const std::string &icon, bool video,
             const std::string &new_link, const std::string &talk, bool films, const std::string &why) {
  ESP_LOGI(TAG, "%s %s", state.c_str(), name.c_str());
  if (state != "ring") ring_stop();
  if (state == "end") {
    if (call_key != key && !key.empty() && stage == Stage::NONE && why.empty()) return;
    call_key = key;
    peer_name = name.empty() ? peer_name : name;
    end_why = why;
    const bool was_live = stage == Stage::LIVE;
    stage = Stage::ENDED;
    leave_call();
    close_list();
    if (was_live) camera_close();
    show_end();
    return;
  }
  call_key = key;
  peer_name = name;
  if (!icon.empty()) peer_icon = icon;
  with_video = video;
  peer_films = films;
  if (state == "out") {
    stage = Stage::OUT;
    claim_audio();
    show_out();
  } else if (state == "ring") {
    if (plugin_host::wake) plugin_host::wake("call");
    settings_screen::close();
    close_list();
    stage = Stage::RING;
    last_ring = 0;
    ring_since = esphome::millis();
#ifdef USE_SPEAKER
    if (volume_get && volume_set && ring_volume_restore < 0.0f && (!ring_on || ring_on())) {
      ring_volume_restore = volume_get();
      if (ring_volume_restore < ring_top) volume_set(ring_top);
    }
#endif
    show_ring();
    claim_audio();
  } else if (state == "live") {
    const bool again = stage == Stage::LIVE && camera_root;
    bool changed = new_link != stream_link;
    stream_link = new_link;
    talk_link = talk;
    on_hold = false;
    if (!again) live_since = esphome::millis();
    stage = Stage::LIVE;
    if (again && !changed) {
      talk_uplink::set_muted(mic_off);
      if (!camera_muted) live_view::mute(camera.stream.handle, false);
      return;
    }
    open_live_view();
  } else if (state == "held") {
    on_hold = true;
    talk_uplink::set_muted(true);
    if (camera_root) live_view::mute(camera.stream.handle, true);
  }
}

bool shown() { return stage == Stage::LIVE; }
bool holds() { return stage != Stage::NONE; }
live_view::Rect area() { return room; }
const std::string &link() { return stream_link; }
void sound_changed() { paint_keys(); }

void build(lv_obj_t *root, const std::string &name) {
  forget_view_parts();
  const auto m = detail_bar::metrics();
  const int w = overlay_card::screen_width(), h = overlay_card::screen_height(), d = key_d(), gap = m.gap * 2;
  const bool lying = w * 10 > h * 12;
  const int keys = with_video ? 4 : 3;
  if (with_video) {
    // The other's picture in the room beside or above the keys (the doorbell's way, until the overlay of the next step).
    if (lying) room = {m.x, m.y, w - 3 * m.x - d, h - 2 * m.y};
    else room = {m.x, m.y, w - 2 * m.x, h - 3 * m.y - d};
    timer_label = lv_label_create(root);
    if (detail_font) lv_obj_set_style_text_font(timer_label, detail_font, 0);
    lv_obj_set_style_text_color(timer_label, theme::color(theme::CAMERA_NOTE), 0);
    lv_label_set_text(timer_label, "0:00");
    KeySpots at = lying ? KeySpots{w - m.x - d, h - m.y - keys * d - (keys - 1) * gap, 0, d + gap}
                        : KeySpots{(w - keys * d - (keys - 1) * gap) / 2, h - m.y - d, d + gap, 0};
    lay_keys(root, at, d);
    if (lying) lv_obj_set_pos(timer_label, w - m.x - d, m.y);
    else lv_obj_set_pos(timer_label, m.x, h - m.y - d - ui::px(4));
  } else {
    // A call with sound alone: its stream brings no pictures, and the app asks a room of at least 64 pixels a side.
    room = {w - 64, h - 64, 64, 64};
    const int dd = ui::px(ui::large() ? 150 : 84), cy = h * 40 / 100;
    disc(root, w / 2 - dd / 2, cy - dd / 2, dd, theme::hex(theme::CAMERA_TRACK), disc_glyph(), big_icon_font ? big_icon_font : mini_icon_font, theme::hex(theme::ON_ACCENT));
    const lv_font_t *big = title_font();
    const int y = cy + dd / 2 + dd / 4;
    text(root, name, big, theme::hex(theme::CAMERA_INK), y);
    timer_label = text(root, "0:00", detail_font, theme::hex(theme::CAMERA_NOTE), y + (big ? lv_font_get_line_height(big) : 28) + ui::px(4));
    const KeySpots at{(w - keys * d - (keys - 1) * gap) / 2, h - 2 * m.y - d, d + gap, 0};
    lay_keys(root, at, d);
  }
  if (camera_spinner) lv_obj_add_flag(camera_spinner, LV_OBJ_FLAG_HIDDEN);
  tick(esphome::millis());
}

void closing() {
  // A view that goes while the call stands (a doorbell's ring): the app's `held` says how; the voice stops with it.
  if (stage == Stage::LIVE) talk_uplink::stop();
  forget_view_parts();
}

void tick(uint32_t now) {
#ifdef USE_SPEAKER
  player.loop();
#endif
  // The add-on ends a ring after 45 s; if it went away meanwhile nobody says so, and a ring must not go on by itself.
  if (stage == Stage::RING && now - ring_since > RING_GONE_MS) {
    ESP_LOGW(TAG, "the ring was never ended");
    ring_stop();
    leave_call();
    free_card();
    stage = Stage::NONE;
    call_key.clear();
  }
  if (stage == Stage::RING && (!last_ring || now - last_ring >= RING_EVERY_MS)) {
    last_ring = now;
    ring_once();
  }
  if (stage == Stage::ENDED && now - end_at >= END_SHOWN_MS) {
    free_card();
    stage = Stage::NONE;
    call_key.clear();
    release_audio();
    live_since = 0;
  }
  talk_uplink::state();  // reaps a talk that ended by itself
  if (stage == Stage::LIVE && timer_label) {
    const std::string t = timer_text();
    if (t != timer_said) { timer_said = t; lv_label_set_text(timer_label, t.c_str()); }
  }
}

void dial(const std::string &to, bool video) { say("dial", to, video); }
void bench_dial(const std::string &to, bool video) { say("dial", to, video); }
void bench_answer() { say("answer"); }
void bench_end() { say(stage == Stage::RING ? "decline" : stage == Stage::OUT ? "cancel" : "end"); }

}  // namespace call
}  // namespace runtime_tiles
#endif
