// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_tile_picture.cpp -o /tmp/test_tile_picture && /tmp/test_tile_picture
#include "../components/smart_display/tile_picture.h"
#include <cassert>
#include <cstdio>
#include <map>
#include <string>

using namespace tile_picture;

static Ask ask(size_t index, const std::string &entity, int w, int h, const std::string &mark = "") {
  Ask a;
  a.index = index;
  a.entity = entity;
  a.mark = mark;
  a.frame = frame(w, h, 12, 0, 0x101010, 0x000000);
  a.circle = 48;
  return a;
}

int main() {
  // A picture within the cap is its place's own pixels, with its corners and ground (GitHub #183: a 2x2 camera on the
  // 10-inch glass, whatever else the page holds).
  {
    const Frame f = frame(504, 316, 18, 0, 0x202020, 0x000000);
    assert(f.w == 504 && f.h == 316 && f.radius == 18 && f.shade == 0 && f.ground == 0x202020);
    // A shade is 0 or what the app takes (170); a corner never more than half the shorter side.
    const Frame g = frame(40, 40, 30, 99, 0x202020, 0x000000);
    assert(g.shade == 0 && g.radius == 20 && frame(40, 40, 4, SHADE, 0, 0).shade == SHADE);
  }
  // A place over the cap (a camera over the whole 10-inch page) is asked smaller, in its proportions, on the dark.
  {
    const Frame f = frame(1248, 760, 24, 0, 0x202020, 0x0A0A0A);
    assert(f.w <= picture_store::MAX_SIDE && size_t(f.w) * f.h * 2 <= picture_store::MAX_BYTES);
    assert(f.w < 1248 && f.h < 760 && f.ground == 0x0A0A0A && f.radius < 24);
    assert(std::abs(double(f.w) / f.h - 1248.0 / 760.0) < 0.01);
  }
  // A board whose store has the room takes the place's own pixels (GitHub #183): the 32 MB of the P4 boards keep 6 MB,
  // so a camera over the whole 10-inch page comes whole; a board with 8 MB (a store of 1.2 MB) keeps the common cap.
  {
    const auto large = picture_store::cap_for(6u << 20), small = picture_store::cap_for(1196u << 10);
    assert(large.side == picture_store::LARGE_SIDE && large.bytes == (6u << 20) / 3);
    assert(small.side == picture_store::MAX_SIDE && small.bytes == picture_store::MAX_BYTES);
    const Frame whole = frame(1248, 760, 24, 0, 0x202020, 0x0A0A0A, large);
    assert(whole.w == 1248 && whole.h == 760 && whole.ground == 0x202020 && whole.radius == 24);
    assert(frame(1248, 760, 24, 0, 0x202020, 0x0A0A0A, small).w < 1248);
  }
  // The key: the place (tile, entity, frame, ground, look) and the mark. Another track is the same place, another
  // picture; another frame, another look or another tile is another place.
  {
    const Ask a = ask(3, "media_player.kitchen", 200, 200, "abc"), b = ask(3, "media_player.kitchen", 200, 200, "def");
    assert(key(a) != key(b) && place_of(key(a)) == place_of(key(b)) && place_of(key(a)) == place(a));
    assert(place_of(key(a)) != place_of(key(ask(3, "media_player.kitchen", 201, 200, "abc"))));
    assert(place_of(key(a)) != place_of(key(ask(4, "media_player.kitchen", 200, 200, "abc"))));
    Ask dark = a;
    dark.dark = true;
    assert(place_of(key(dark)) != place_of(key(a)));
    // A camera has no mark: its next picture keeps the key.
    assert(key(ask(1, "camera.door", 100, 60)) == key(ask(1, "camera.door", 100, 60)));
    // A key with bars in its mark still has its place; what is no tile picture's key has none.
    assert(place_of(key(ask(3, "media_player.kitchen", 200, 200, "a|b"))) == place(a));
    assert(place_of("cover|media_player.kitchen|abc|200|000000").empty() && place_of("tile|3").empty());
    // A card keeps a key only while it shows that tile and entity.
    assert(belongs(key(a), 3, "media_player.kitchen") && !belongs(key(a), 13, "media_player.kitchen"));
    assert(!belongs(key(a), 3, "media_player.kitchen_2") && !belongs("", 3, "media_player.kitchen"));
  }
  // The question is a page of one tile, as every app since 0.3.8 reads it (camera_feed.live_request, tile_art.parse):
  // its entity, its index, a circle within LIVE_SIZES, its ground and one frame at the top left.
  {
    Ask a = ask(7, "camera.drive", 504, 316);
    a.frame.shade = SHADE;
    a.circle = 205;
    a.dark = true;
    std::map<std::string, std::string> f;
    for (const auto &field : fields(a)) f[field.first] = field.second;
    assert(f.size() == 6 && f["tiles"] == "camera.drive" && f["idx"] == "7" && f["size"] == "160");
    assert(f["bg"] == "101010" && f["dark"] == "1" && f["atlas"] == "[[0,0,504,316,12,170]]");
    a.circle = 4;
    for (const auto &field : fields(a)) f[field.first] = field.second;
    assert(f["size"] == "24");
    assert(tag(7) == "tile|7" && tag(7) != tag(17));
  }
  // A plugin tile's places (plugin API 0.10): the parts of one picture, an atlas from the card's top left to the
  // farthest edge of them, each piece where its place lies; the addresses and fits go with the frames, in order.
  {
    Ask a;
    std::vector<Part> parts;
    parts.push_back({10, 8, 60, 90, 6, "https://image.tmdb.org/t/p/w342/a.jpg", false});
    parts.push_back({80, 8, 60, 90, 6, "https://image.tmdb.org/t/p/w342/b.jpg", true});
    set_parts(a, parts, 0x202020);
    a.index = 4;
    a.entity = "plugin:films.tonight";
    assert(a.frame.w == 140 && a.frame.h == 98 && a.frame.ground == 0x202020 && a.scale == picture_store::SCALE_ONE);
    assert(a.drawn && !a.every && a.parts.size() == 2 && a.mark.size() == 16);
    std::map<std::string, std::string> f;
    for (const auto &field : fields(a)) f[field.first] = field.second;
    assert(f.size() == 8 && f["tiles"] == "plugin:films.tonight" && f["idx"] == "4" && f["bg"] == "202020");
    assert(f["atlas"] == "[[10,8,60,90,6,0],[80,8,60,90,6,0]]");
    assert(f["src"] == "[\"https://image.tmdb.org/t/p/w342/a.jpg\",\"https://image.tmdb.org/t/p/w342/b.jpg\"]");
    assert(f["fit"] == "[\"cover\",\"contain\"]");
    // Another address, a place that moved or grew, another fit: another picture of the same place.
    Ask b = a;
    parts[1].url = "https://image.tmdb.org/t/p/w342/c.jpg";
    set_parts(b, parts, 0x202020);
    assert(key(a) != key(b) && place_of(key(a)) == place_of(key(b)));
    parts[1].url = a.parts[1].url;
    parts[1].x = 81;
    set_parts(b, parts, 0x202020);
    assert(key(a) != key(b));
    parts[1].x = 80;
    parts[1].contain = false;
    set_parts(b, parts, 0x202020);
    assert(key(a) != key(b));
    parts[1].contain = true;
    set_parts(b, parts, 0x202020);
    assert(key(a) == key(b) && belongs(key(a), 4, "plugin:films.tonight"));
    // A turn and a reflection (0.10) go with the frames only when a place asks for them, and make another picture.
    parts[0].turn = 2;
    parts[1].mirror = true;
    set_parts(b, parts, 0x202020);
    assert(key(a) != key(b));
    std::map<std::string, std::string> g;
    for (const auto &field : fields(b)) g[field.first] = field.second;
    assert(g.size() == 10 && g["turn"] == "[\"right\",\"\"]" && g["mirror"] == "[0,1]");
    parts[0].turn = 0;
    parts[1].mirror = false;
    // A card over the cap: every piece comes smaller alike, and the frames still do not overlap.
    std::vector<Part> wide;
    for (int i = 0; i < 4; ++i) wide.push_back({i * 400, 0, 400, 760, 24, "https://image.tmdb.org/x" + std::to_string(i) + ".jpg", false});
    set_parts(b, wide, 0x202020, picture_store::cap_for(1196u << 10));
    assert(b.scale < picture_store::SCALE_ONE && b.frame.w <= picture_store::MAX_SIDE);
    int right = 0;
    for (const auto &p : b.parts) { const Piece f = piece(p, b.scale); assert(f.x >= right); right = f.x + f.w; assert(f.radius < 24); }
    assert(right <= b.frame.w);
    // A quote or a backslash in an address stays a JSON string; a control character goes.
    assert(quoted("a\"b\\c\n") == "\"a\\\"b\\\\c\"");
    assert(digest("a") != digest("b") && digest("a") == digest("a"));
  }
  // Answers find their tile by the question's number; only a tile's last question counts.
  {
    Questions q;
    const uint32_t first = q.ask(2), other = q.ask(5);
    assert(first != other && q.answered(first) == 2 && q.answered(other) == 5);
    const uint32_t again = q.ask(2);  // the tile moved on (another track) and asked again
    assert(q.answered(first) == -1 && q.answered(again) == 2 && q.answered(other) == 5 && q.answered(0) == -1);
    q.clear();  // another layout
    assert(q.answered(again) == -1 && q.answered(other) == -1);
    assert(q.answered(q.ask(2)) == 2);
  }
  // A plugin's card over the page (plugin API 0.13): its places as a tile's parts, under a key of its own that no tile's
  // key, place or tag is, with the card and the entity it shows in its question.
  {
    Ask a;
    Part cover;
    cover.x = 200; cover.y = 0; cover.w = 160; cover.h = 160; cover.url = "https://cdn.example.org/a.jpg";
    set_parts(a, {cover}, 0x101010);
    a.index = 3;
    a.entity = "plugin:music.release";
    const std::string key = card_key(a, "plugin:music.release", "media_player.kitchen");
    assert(key.rfind("pcard|plugin:music.release|media_player.kitchen|360x160", 0) == 0);
    assert(place_of(key).empty() && !belongs(key, 3, "plugin:music.release") && key != tile_picture::key(a));
    assert(card_tag("plugin:music.release") == "pcard|plugin:music.release" && card_tag("plugin:music.release") != tag(3));
    // Another address is another picture, in the same layout: the places keep the last one until the next is here.
    Ask b = a;
    Part next = cover;
    next.url = "https://cdn.example.org/b.jpg";
    set_parts(b, {next}, 0x101010);
    assert(card_key(b, "plugin:music.release", "media_player.kitchen") != key);
    assert(layout_of(a.parts) == layout_of(b.parts));
    next.x = 0;
    set_parts(b, {next}, 0x101010);
    assert(layout_of(a.parts) != layout_of(b.parts));
    const auto f = card_fields(a, "media_player.kitchen");
    bool card = false, of = false, src = false;
    for (const auto &field : f) {
      card = card || (field.first == "card" && field.second == "1");
      of = of || (field.first == "for" && field.second == "media_player.kitchen");
      src = src || (field.first == "src" && field.second == "[\"https://cdn.example.org/a.jpg\"]");
    }
    assert(card && of && src);
  }
  printf("test_tile_picture: ok\n");
  return 0;
}
