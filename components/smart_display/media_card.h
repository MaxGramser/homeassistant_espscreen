#pragma once
// The media card (firmware 0.2.64+): where its parts go and what its texts say. Pure arithmetic, free of LVGL and
// ESPHome, so tests/test_media_card.cpp checks every shape on a PC; runtime_tiles.h draws it.
//
// The card is a "now playing" view like a phone's: the album art (or a placeholder with the player's icon), the title,
// the artist and the album, a progress bar with the elapsed and total time, three round keys (previous, play or pause,
// next) and a volume row (volume down, a slider, volume up and the player's own keys). Two forms share one recipe: a tall area (the Guition's
// card, 480 wide under its top bar) stacks everything under the art; a wide area (the CYD's card, a tile over the whole
// page) puts the art at the left with the texts, the bar and the keys beside it. The volume row always runs along the
// bottom. What does not fit goes: first the artist line, then the times beside the bar, and the art shrinks last.
//
// A board that draws no pictures (one without PSRAM, such as the CYD: camera_supported) never gets a cover, so it gets no
// square for one either (firmware 0.46.0): the words, the bar and the keys stand together in the middle of the room, a
// hand's width at most, as a phone's player does for a track without art. Before, it showed an empty square with the
// player's icon in it, which people took for a cover that failed to load.
//
// On glass wider than a hand (a ten-inch panel) two rules of overlay_card apply: the cover is a picture and grows
// with the glass, while the texts, the keys and the volume row keep a hand's width and stand together in the middle.
// Before that the cover stayed a thumbnail in the left corner and the volume slider ran from edge to edge, nineteen
// centimetres of it (firmware 0.2.82).
//
// The volume row (firmware 0.39.0, GitHub #146) is a row of round keys as tall as previous and next: volume down at
// the left, then the slider, volume up, and at the right end the keys of what the player has besides (its inputs, its
// library), which stood in the card's top bar before; the top bar's right corner is the power key's now, where every
// other card has it. Before that the row was a bare mute key, the slider and the percentage.
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
  bool art = true;     // the board draws pictures, so the card has a place for the cover (above)
  int clock_w = 0;     // the widest time beside the bar as the small font writes it ("1:02:45"), 0 for time_w()
  int title_h = 32;    // the title's font (the card heading font)
  int artist_h = 25;   // the artist line (the control font)
  int small_h = 19;    // the times and the percentage (the small font)
  int key_h() const { return ui::px(large ? 52 : 34); }      // previous and next
  int play_h() const { return ui::px(large ? 64 : 40); }     // play or pause, the biggest key: a thumb finds it without looking
  int key_gap() const { return ui::px(large ? 28 : 14); }    // between the keys, less when the row has no room
  int min_gap() const { return ui::px(large ? 12 : 8); }
  int mute_h() const { return ui::px(large ? 32 : 22); }    // shuffle and repeat, bare at the ends of the keys
  int slider_h() const { return ui::px(large ? 20 : 12); }
  // The volume slider's round knob, the slider and its padding (runtime_tiles::media_slider), and the seek knob on the
  // bar: both stand centred on the end of their fill, so at either end half of it reaches past the line.
  int knob_h() const { return slider_h() + 2 * ui::px(large ? 4 : 3); }
  int bar_h() const { return ui::px(large ? 6 : 4); }
  int seek_knob_h() const { return bar_h() + ui::px(large ? 14 : 10); }
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
  int time_w() const { return ui::px(large ? 48 : 34); }     // "12:34" beside the bar
  // The times' place beside the bar: as wide as the longest time the track has, never narrower than "12:34" takes
  // (firmware 0.46.0). A fixed place cut a track of an hour or more to "1:02:..." (a podcast, an audiobook, a mix).
  int times_w() const { return std::max(time_w(), clock_w); }
};
struct Layout {
  bool wide = false;    // the art at the left, everything else beside it
  bool times = false;   // the elapsed and total time at the ends of the bar
  bool artist = true;   // the artist line (a tile over a CYD page has no room for it)
  bool sides = false;   // shuffle and repeat at the ends of the keys' row (firmware 0.24.0+), where it has room
  Rect art, title, artist_line, bar, elapsed, total, prev, play, next;
  // The volume row: volume down, the slider, volume up, and `ends` of the player's own keys at the right end, ends[0]
  // the outermost.
  Rect minus, volume, plus;
  Rect ends[2];
  Rect shuffle, repeat;
  // Where a finger takes the bar to seek (firmware 0.24.0+): the bar's length, and a finger's height round its line.
  Rect seek;
  int art_radius = 0;   // the corner the art is rounded with (baked into the picture by the app)
};

inline int radius_for(int art) { return std::max(4, art / 12); }

// The card's parts inside an area of `width` × `height` whose top left is (0, 0), with the volume row's keys
// `volume_h` tall (layout() below chooses).
inline Layout layout_with(const Metrics &m, int width, int height, int ends, int volume_h) {
  Layout l;
  const int g = m.gap(), margin = m.margin();
  // The volume row along the bottom, whatever the form: a slider is dragged, so it never runs wider than a hand
  // spans, and on wider glass it stands in the middle.
  const int row_w = std::min(width - 2 * margin, m.reach()), row_x = (width - row_w) / 2, row_y = height - volume_h;
  ends = std::clamp(ends, 0, 2);
  int right = row_x + row_w;
  for (int i = 0; i < ends; ++i) {
    right -= volume_h;
    l.ends[i] = {right, row_y, volume_h, volume_h};
    right -= g;
  }
  l.minus = {row_x, row_y, volume_h, volume_h};
  l.plus = {right - volume_h, row_y, volume_h, volume_h};
  // The knob at 0 or 100 % keeps a gap's air to volume down and up instead of touching them (firmware 0.52.0).
  const int knob_reach = g + m.knob_h() / 2, slider_x = l.minus.right() + knob_reach;
  l.volume = {slider_x, row_y + (volume_h - m.slider_h()) / 2, std::max(1, l.plus.x - knob_reach - slider_x), m.slider_h()};
  const int above = height - volume_h - g;  // room for the rest
  // The wide form is for an area too short to stack: a tile over a CYD page. Glass wider than a hand with room
  // for a full cover and the stack takes the tall form instead, the "now playing" a phone draws, and the cover
  // grows with the glass. Every area the two first boards have is too narrow or too short for that, so they
  // keep the form they had.
  const int stack_min = m.max_art() + m.title_h + m.artist_h + 3 * g + m.small_h + m.play_h();
  l.wide = width * 4 > height * 5 && !(width > m.reach() && above >= stack_min);
  const int row_min = 2 * m.key_h() + m.play_h() + 2 * m.min_gap();
  // The bar's row: the elapsed time at the left, the total at the right, the bar between them, on one small line. The
  // seek knob at either end keeps half a gap's air to the times (firmware 0.52.0).
  auto bar_row = [&](int x, int w, int y, bool with_times) {
    const int tw = with_times && w >= 4 * m.times_w() ? m.times_w() : 0;  // no room for times on a very narrow row
    l.times = tw > 0;
    const int row_h = l.times ? m.small_h : m.bar_h();
    l.elapsed = {x, y, tw, m.small_h};
    l.total = {x + w - tw, y, tw, m.small_h};
    const int side = tw ? tw + g / 2 + m.seek_knob_h() / 2 : 0;
    const int bar_x = x + side, bar_w = std::max(1, w - 2 * side);
    l.bar = {bar_x, y + (row_h - m.bar_h()) / 2, bar_w, m.bar_h()};
    return row_h;
  };
  auto keys = [&](int x, int w, int y) {
    // Shuffle and repeat (firmware 0.24.0+) stand at the ends of the row as bare keys, the size of the mute key, and
    // only where the row has room for them beside its three keys at their own gaps: on the CYD the three keep it.
    const int side = m.mute_h(), with_sides = 2 * m.key_h() + m.play_h() + 2 * m.key_gap() + 2 * (side + m.key_gap());
    l.sides = w >= with_sides;
    const int inner = l.sides ? w - 2 * (side + m.key_gap()) : w;
    const int gap = std::clamp((inner - 2 * m.key_h() - m.play_h()) / 2, m.min_gap(), m.key_gap());
    const int row_w = 2 * m.key_h() + m.play_h() + 2 * gap, row_x = x + (w - row_w) / 2;
    l.prev = {row_x, y + (m.play_h() - m.key_h()) / 2, m.key_h(), m.key_h()};
    l.play = {row_x + m.key_h() + gap, y, m.play_h(), m.play_h()};
    l.next = {l.play.right() + gap, l.prev.y, m.key_h(), m.key_h()};
    if (l.sides) {
      l.shuffle = {l.prev.x - m.key_gap() - side, l.play.cy() - side / 2, side, side};
      l.repeat = {l.next.right() + m.key_gap(), l.shuffle.y, side, side};
    } else {
      l.shuffle = l.repeat = Rect{};
    }
  };
  if (!m.art) {
    // No pictures on this board: no cover and no square for one. The words, the bar and the keys stand together in the
    // middle of the room above the volume row, as wide as the card leaves them and a hand's width at most; the keys'
    // row has the card's whole width, so shuffle and repeat fit where the cover used to take their room.
    l.wide = false;
    const int text_w = std::min(width - 2 * margin, m.reach()), text_x = (width - text_w) / 2;
    int stack = m.title_h + m.artist_h + g + m.small_h + g + m.play_h();
    l.artist = stack <= above;
    if (!l.artist) stack -= m.artist_h;
    const bool with_times = stack <= above;
    if (!with_times) stack -= m.small_h - m.bar_h();
    int y = std::max(0, (above - stack) / 2);
    l.title = {text_x, y, text_w, m.title_h}; y += m.title_h;
    if (l.artist) { l.artist_line = {text_x, y, text_w, m.artist_h}; y += m.artist_h; }
    y += g;
    y += bar_row(text_x, text_w, y, with_times);
    keys(0, width, y + g);
  } else if (!l.wide) {
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
  l.art_radius = radius_for(l.art.w);
  // The bar takes a finger as tall as a key, round its own line; the keys and the words over it keep theirs.
  const int reach = std::max(m.bar_h(), ui::px(m.large ? 32 : 22));
  l.seek = {l.bar.x, l.bar.cy() - reach / 2, l.bar.w, reach};
  return l;
}
// The card's parts inside an area of `width` × `height` whose top left is (0, 0): the room under the top bar of a
// card, or under the head of a tile over the whole page. `ends` keys (0 to 2) close the volume row at the right.
// The volume row's keys are as big as previous and next where the area has the room; where they would push the
// artist line out (a tile over a whole page under its head) they are the size of shuffle and repeat, the height
// the row had before.
inline Layout layout(const Metrics &m, int width, int height, int ends = 0) {
  const Layout l = layout_with(m, width, height, ends, m.key_h());
  if (!m.art) return l.artist ? l : layout_with(m, width, height, ends, m.mute_h());
  if (!l.wide || l.artist) return l;
  return layout_with(m, width, height, ends, m.mute_h());
}

// ---- Seeking (firmware 0.24.0+) ----
// The seconds a place on the bar stands for: `x` from the bar's left end, the bar `width` long.
inline uint32_t seek_seconds(int x, int width, uint32_t duration) {
  if (width <= 0 || !duration) return 0;
  return static_cast<uint32_t>(static_cast<uint64_t>(std::clamp(x, 0, width)) * duration / width);
}
// A seek sent stands on the bar until Home Assistant reports the player near it, the track changes, or this long has
// passed: Spotify answers a seek with a state of before it, and the knob jumped back and forth.
constexpr uint32_t SEEK_HOLD_MS = 6000;
constexpr uint32_t SEEK_NEAR_S = 3;
struct Seek {
  bool held = false;
  uint32_t seconds = 0, since = 0;   // where it was sent to, and when (millis)
  uint32_t epoch = 0;                // that moment on Home Assistant's clock, for the bar to run on from
  std::string track;                 // the title it was sent for
  void send(uint32_t to, uint32_t now_ms, uint32_t now_epoch, const std::string &title) { held = true; seconds = to; since = now_ms; epoch = now_epoch; track = title; }
  // Home Assistant's word on the player: whether the seek still holds.
  bool holds(uint32_t reported, uint32_t reported_at, uint32_t now_ms, uint32_t now_epoch, bool playing, const std::string &title) {
    if (!held) return false;
    const uint32_t here = playing && now_epoch > reported_at && reported_at ? reported + (now_epoch - reported_at) : reported;
    const uint32_t wanted = playing && now_epoch > epoch ? seconds + (now_epoch - epoch) : seconds;
    const uint32_t off = here > wanted ? here - wanted : wanted - here;
    if (title != track || now_ms - since >= SEEK_HOLD_MS || off <= SEEK_NEAR_S) held = false;
    return held;
  }
};

// ---- The card's ground (firmware 0.24.0+) ----
// The colour the app read from the cover; false without it, and the card keeps its neutral ground (theme::MEDIA_GROUND).
// One colour (firmware 0.52.0): the app has sent the same colour twice, "RRGGBB,RRGGBB", since a gradient between two
// dark colours showed as bands on 16-bit glass (GitHub #135), and it keeps that form for the firmware of before, which
// reads nothing else. This one reads the first colour, and a lone "RRGGBB" as well.
inline bool ground(const std::string &text, uint32_t &colour) {
  if (text.size() != 6 && (text.size() != 13 || text[6] != ',')) return false;
  for (size_t i = 0; i < text.size(); ++i) {
    if (i == 6) continue;
    const char c = text[i];
    if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f'))) return false;
  }
  colour = static_cast<uint32_t>(std::stoul(text.substr(0, 6), nullptr, 16));
  return true;
}
// The repeat key's next step, as Spotify's and Home Assistant's own player cycle it: off, all, one.
inline const char *next_repeat(const std::string &repeat) {
  if (repeat == "off") return "all";
  if (repeat == "all") return "one";
  return "off";
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
