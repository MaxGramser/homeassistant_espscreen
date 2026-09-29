#pragma once
// The media card (firmware 0.2.64+): where its parts go and what its texts say. Pure arithmetic, free of LVGL and
// ESPHome, so tests/test_media_card.cpp checks every shape on a PC; runtime_tiles.h draws it.
//
// The card is a "now playing" view like a phone's: the album art (or a placeholder with the player's icon), the title,
// the artist and the album, a progress bar with the elapsed and total time, three round keys (previous, play or pause,
// next) and a volume row (a mute key, a slider, the percentage). Two forms share one recipe: a tall area (the Guition's
// card, 480 wide under its top bar) stacks everything under the art; a wide area (the CYD's card, a tile over the whole
// page) puts the art at the left with the texts, the bar and the keys beside it. The volume row always runs along the
// bottom. What does not fit goes: first the artist line, then the times beside the bar, and the art shrinks last.
//
// On glass wider than a hand (a ten-inch panel) two rules of overlay_card apply: the cover is a picture and grows
// with the glass, while the texts, the keys and the volume row keep a hand's width and stand together in the middle.
// Before that the cover stayed a thumbnail in the left corner and the volume slider ran from edge to edge, nineteen
// centimetres of it (firmware 0.2.82).
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include "screen_text.h"
#include "ui_scale.h"

namespace media_card {
struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  int cx() const { return x + w / 2; }
  int cy() const { return y + h / 2; }
  int right() const { return x + w; }
  int bottom() const { return y + h; }
};
// What the board brings: its size class and the line heights of the fonts the card writes with.
struct Metrics {
  bool large = true;   // the Guition: big keys and a big cover; the CYD gets the small numbers
  int title_h = 32;    // the title's font (the card heading font)
  int artist_h = 25;   // the artist line (the control font)
  int small_h = 19;    // the times and the percentage (the small font)
  int key_h() const { return ui::px(large ? 52 : 34); }      // previous and next
  int play_h() const { return ui::px(large ? 64 : 40); }     // play or pause, the biggest key: a thumb finds it without looking
  int key_gap() const { return ui::px(large ? 28 : 14); }    // between the keys, less when the row has no room
  int min_gap() const { return ui::px(large ? 12 : 8); }
  int mute_h() const { return ui::px(large ? 32 : 22); }
  int slider_h() const { return ui::px(large ? 20 : 12); }
  int bar_h() const { return ui::px(large ? 6 : 4); }
  int gap() const { return ui::px(large ? 12 : 6); }
  int margin() const { return ui::px(large ? 24 : 10); }
  int max_art() const { return ui::px(large ? 200 : 120); }
  // The largest cover ESP Screen Manager serves: `camera_feed.COVER_SIZES[1]`, guarded by tests/test_media_card.py.
  // The app cuts and rounds a player's picture to exactly the size the card asks for and the screen draws what comes
  // back one to one, so a square the app will not serve is a square that stays empty: an add-on that does not know
  // the size answers nothing at all, and an older add-on than this firmware never will. Raising it is a change in
  // both, and in that order.
  static int cover_max() { return 320; }
  // A cover is a picture: on glass with room to spare it grows past the look's own size, up to a third of the width
  // or half the height, and never past what the app will hand over. Every board so far stays on max_art().
  int art_cap(int width, int height) const {
    return std::min(cover_max(), std::max(max_art(), std::min(width / 3, height / 2)));
  }
  // The widest a row a finger works may get (overlay_card::reach, without pulling LVGL in here).
  int reach() const { return ui::control_max_width(); }
  int percent_w() const { return ui::px(large ? 52 : 34); }
  int time_w() const { return ui::px(large ? 48 : 34); }     // "12:34" beside the bar
};
struct Layout {
  bool wide = false;    // the art at the left, everything else beside it
  bool times = false;   // the elapsed and total time at the ends of the bar
  bool artist = true;   // the artist line (a tile over a CYD page has no room for it)
  Rect art, title, artist_line, bar, elapsed, total, prev, play, next, mute, volume, percent;
  int art_radius = 0;   // the corner the art is rounded with (baked into the picture by the app)
};

inline int radius_for(int art) { return std::max(4, art / 12); }

// The card's parts inside an area of `width` × `height` whose top left is (0, 0): the room under the top bar of a
// card, or under the head of a tile over the whole page.
inline Layout layout(const Metrics &m, int width, int height) {
  Layout l;
  const int g = m.gap(), margin = m.margin();
  // The volume row along the bottom, whatever the form: a slider is dragged, so it never runs wider than a hand
  // spans, and on wider glass it stands in the middle.
  const int volume_h = std::max(m.mute_h(), m.slider_h());
  const int row_w = std::min(width - 2 * margin, m.reach()), row_x = (width - row_w) / 2;
  l.mute = {row_x, height - volume_h + (volume_h - m.mute_h()) / 2, m.mute_h(), m.mute_h()};
  l.percent = {row_x + row_w - m.percent_w(), height - volume_h + (volume_h - m.small_h) / 2, m.percent_w(), m.small_h};
  const int slider_x = l.mute.right() + g;
  l.volume = {slider_x, height - volume_h + (volume_h - m.slider_h()) / 2, std::max(1, l.percent.x - g - slider_x), m.slider_h()};
  const int above = height - volume_h - g;  // room for the rest
  // The wide form is for an area too short to stack: a tile over a CYD page. Glass wider than a hand with room
  // for a full cover and the stack takes the tall form instead, the "now playing" a phone draws, and the cover
  // grows with the glass. Every area the two first boards have is too narrow or too short for that, so they
  // keep the form they had.
  const int stack_min = m.max_art() + m.title_h + m.artist_h + 3 * g + m.small_h + m.play_h();
  l.wide = width * 4 > height * 5 && !(width > m.reach() && above >= stack_min);
  const int row_min = 2 * m.key_h() + m.play_h() + 2 * m.min_gap();
  // The bar's row: the elapsed time at the left, the total at the right, the bar between them, on one small line.
  auto bar_row = [&](int x, int w, int y, bool with_times) {
    const int tw = with_times && w >= 4 * m.time_w() ? m.time_w() : 0;  // no room for times on a very narrow row
    l.times = tw > 0;
    const int row_h = l.times ? m.small_h : m.bar_h();
    l.elapsed = {x, y, tw, m.small_h};
    l.total = {x + w - tw, y, tw, m.small_h};
    const int bar_x = x + (tw ? tw + g / 2 : 0), bar_w = std::max(1, w - 2 * (tw ? tw + g / 2 : 0));
    l.bar = {bar_x, y + (row_h - m.bar_h()) / 2, bar_w, m.bar_h()};
    return row_h;
  };
  auto keys = [&](int x, int w, int y) {
    const int gap = std::clamp((w - 2 * m.key_h() - m.play_h()) / 2, m.min_gap(), m.key_gap());
    const int row_w = 2 * m.key_h() + m.play_h() + 2 * gap, row_x = x + (w - row_w) / 2;
    l.prev = {row_x, y + (m.play_h() - m.key_h()) / 2, m.key_h(), m.key_h()};
    l.play = {row_x + m.key_h() + gap, y, m.play_h(), m.play_h()};
    l.next = {l.play.right() + gap, l.prev.y, m.key_h(), m.key_h()};
  };
  if (!l.wide) {
    // Tall: the art on top, the texts, the bar and the keys under it, all centred.
    const int keys_y = above - m.play_h();
    const int stack = m.title_h + m.artist_h + g + m.small_h + g;  // between the art and the keys: the bar row is one small line
    int art = std::min(m.art_cap(width, above), keys_y - g - stack - g);
    art = std::max(32, art);
    // The words and the bar are read, not dragged, but a line that runs the width of a ten-inch panel is no
    // easier to read than the cover is to reach: they keep a hand's width too, in the middle of the card.
    const int text_w = std::min(width - 2 * margin, m.reach()), text_x = (width - text_w) / 2;
    const int stack_y = keys_y - g - stack;
    l.art = {(width - art) / 2, std::max(0, (stack_y - g - art) / 2), art, art};
    l.title = {text_x, stack_y, text_w, m.title_h};
    l.artist_line = {text_x, l.title.bottom(), text_w, m.artist_h};
    bar_row(text_x, text_w, l.artist_line.bottom() + g, true);
    keys(0, width, keys_y);
  } else {
    // Wide: the art at the left, a column beside it, centred on the art and never taller than the room; the column's
    // own gaps are half the card's, so a tile's head leaves room for the artist line. The column keeps a hand's
    // width, and the art and the column together stand in the middle of the glass.
    int art = std::min({m.art_cap(width, above), above, width - 2 * margin - 2 * g - row_min});
    art = std::max(32, art);
    const int h = g / 2;
    int column = m.title_h + m.artist_h + h + m.small_h + h + m.play_h();
    l.artist = column <= above;
    if (!l.artist) column -= m.artist_h;
    bool with_times = column <= above;
    if (!with_times) column -= m.small_h - m.bar_h();
    const int w = std::max(1, std::min(width - 2 * margin - 2 * g - art, m.reach()));
    l.art = {std::max(margin, (width - art - 2 * g - w) / 2), std::max(0, (above - art) / 2), art, art};
    const int x = l.art.right() + 2 * g;
    int y = std::clamp(l.art.y + (art - column) / 2, 0, std::max(0, above - column));
    l.title = {x, y, w, m.title_h}; y += m.title_h;
    if (l.artist) { l.artist_line = {x, y, w, m.artist_h}; y += m.artist_h; }
    y += h;
    y += bar_row(x, w, y, with_times);
    keys(x, w, y + h);
  }
  // The 640x180 strip cannot stack full-size playback keys above volume.
  // Put the two controls beside each other under the title and progress bar.
  if (height <= 140 && width >= 560 && width >= 3 * height) {
    l.wide = true;
    l.artist = false;
    l.times = false;
    const int art = std::max(32, std::min(height, ui::px(64)));
    l.art = {margin, 0, art, art};
    const int x = l.art.right() + 2 * g, w = std::max(1, width - x - margin);
    l.title = {x, 0, w, m.title_h};
    const int bar_y = m.title_h + g / 2;
    l.bar = {x, bar_y, w, m.bar_h()};
    const int key_y = bar_y + m.bar_h() + g / 2;
    const int play = std::min(m.play_h(), height - key_y - 2);
    const int side = std::max(m.key_h(), ui::touch_min());
    const int key_gap = m.min_gap();
    const int key_x = x;
    l.prev = {key_x, key_y + (play - side) / 2, side, side};
    l.play = {key_x + side + key_gap, key_y, play, play};
    l.next = {l.play.right() + key_gap, l.prev.y, side, side};
    const int row_x = l.next.right() + 2 * g;
    const int row_w = std::max(1, width - margin - row_x);
    const int row_h = std::max(m.mute_h(), m.slider_h());
    const int row_y = key_y + (play - row_h) / 2;
    l.mute = {row_x, row_y + (row_h - m.mute_h()) / 2, m.mute_h(), m.mute_h()};
    l.percent = {row_x + row_w - m.percent_w(), row_y + (row_h - m.small_h) / 2, m.percent_w(), m.small_h};
    const int volume_x = l.mute.right() + g;
    l.volume = {volume_x, row_y + (row_h - m.slider_h()) / 2,
                std::max(1, l.percent.x - g - volume_x), m.slider_h()};
  }
  l.art_radius = radius_for(l.art.w);
  return l;
}

// Home Assistant reports where the track was (media_position) and when it said so (media_position_updated_at);
// while playing the position runs on from that moment.
inline uint32_t elapsed_seconds(uint32_t position, uint32_t position_at, uint32_t now, bool playing, uint32_t duration) {
  uint32_t elapsed = position;
  if (playing && position_at && now > position_at) elapsed += now - position_at;
  if (duration && elapsed > duration) elapsed = duration;
  return elapsed;
}
// Per mille of the track, or -1 without a duration.
inline int progress(uint32_t position, uint32_t position_at, uint32_t now, bool playing, uint32_t duration) {
  if (!duration) return -1;
  return static_cast<int>(elapsed_seconds(position, position_at, now, playing, duration) * 1000ULL / duration);
}
// "3:07", "1:02:45": the way every player writes a time.
inline std::string clock_text(uint32_t seconds) {
  char b[24];
  if (seconds >= 3600) snprintf(b, sizeof(b), "%u:%02u:%02u", (unsigned) (seconds / 3600), (unsigned) (seconds / 60 % 60), (unsigned) (seconds % 60));
  else snprintf(b, sizeof(b), "%u:%02u", (unsigned) (seconds / 60), (unsigned) (seconds % 60));
  return b;
}
// The second line: "Artist · Album", or whichever of the two there is.
inline std::string subtitle(const std::string &artist, const std::string &album) {
  if (!artist.empty() && !album.empty()) return artist + " · " + album;
  return artist.empty() ? album : artist;
}
// What the card says instead of a title when nothing plays.
inline const char *idle_text(const std::string &state) {
  if (state == "off") return screen_text::tr(screen_text::txt::ha_off);
  if (state == "standby") return screen_text::tr(screen_text::txt::ha_media_standby);
  if (state == "buffering") return screen_text::tr(screen_text::txt::media_loading);
  if (state == "unavailable") return screen_text::tr(screen_text::txt::ha_unavailable);
  return screen_text::tr(screen_text::txt::media_not_playing);
}
inline bool playing(const std::string &state) { return state == "playing" || state == "buffering"; }
inline bool has_track(const std::string &state) { return state == "playing" || state == "paused" || state == "buffering"; }
}  // namespace media_card
