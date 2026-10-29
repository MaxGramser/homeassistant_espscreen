// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_picture_question.cpp -o /tmp/test_picture_question && /tmp/test_picture_question
// The one question every owner asks (picture_question.h): its JSON as the app reads it, its old fields exactly as each
// owner asked before (tile_picture::fields and card_fields, and the full view's, the cover's, the library's, the vacuum
// map's and the screensaver's fields of firmware 0.57), and the numbers answers find their owner by.
#include "../components/smart_display/picture_question.h"
#include "../components/smart_display/tile_picture.h"
#include <cassert>
#include <cstdio>
#include <map>
#include <string>

using namespace picture_question;

static std::map<std::string, std::string> as_map(const Fields &fields) {
  std::map<std::string, std::string> out;
  for (const auto &f : fields) {
    assert(out.count(f.first) == 0);  // no field twice
    out[f.first] = f.second;
  }
  return out;
}

static tile_picture::Ask tile_ask() {
  tile_picture::Ask a;
  a.index = 3;
  a.entity = "camera.porch";
  a.frame = tile_picture::frame(240, 160, 12, 0, 0x202020, 0x000000);
  a.circle = 48;
  a.dark = true;
  a.every = 15000;
  return a;
}

static tile_picture::Ask plugin_ask() {
  tile_picture::Ask a;
  a.index = 5;
  a.entity = "plugin:cinema.films";
  std::vector<tile_picture::Part> parts(2);
  parts[0] = {0, 10, 90, 140, 6, "https://image.tmdb.org/t/p/w342/a.jpg", false, 2, true};
  parts[1] = {105, 0, 90, 156, 6, "https://image.tmdb.org/t/p/w342/b.jpg", true, 0, false};
  tile_picture::set_parts(a, parts, 0x101010);
  return a;
}

int main() {
  // A tile's own picture: the JSON names the tile, its entity and its source, the frame and the look.
  {
    const Question q = tile_picture::question(tile_ask());
    const std::string text = json(q);
    assert(text.find("\"o\":\"tile\"") != std::string::npos);
    assert(text.find("\"i\":3") != std::string::npos);
    assert(text.find("\"for\":\"camera.porch\"") != std::string::npos);
    assert(text.find("\"src\":[\"tile:3\"]") != std::string::npos);
    assert(text.find("\"box\":[240,160]") != std::string::npos);
    assert(text.find("\"at\":[[0,0,240,160,12,0]]") != std::string::npos);
    assert(text.find("\"bg\":[\"202020\"]") != std::string::npos);
    assert(text.find("\"look\":\"d\"") != std::string::npos);
    assert(text.find("\"fmt\":[\"bmp8\",\"bmp24\"]") != std::string::npos);
    assert(text.find("\"pace\":15000") != std::string::npos);
    assert(text.find("\"live\"") == std::string::npos && text.find("\"cap\"") == std::string::npos);
    // Its old fields are exactly what tile_picture::fields sent.
    assert(as_map(legacy(q)) == as_map(tile_picture::fields(tile_ask())));
  }
  // A live tile on a P4 adds its card's room and the sound, the old way too.
  {
    Question q = tile_picture::question(tile_ask());
    q.live_w = 240, q.live_h = 160, q.sound = true;
    const auto old = as_map(legacy(q));
    assert(old.at("live") == "240x160" && old.at("sound") == "1");
    assert(json(q).find("\"live\":[240,160],\"sound\":1") != std::string::npos);
  }
  // A plugin tile's places: the addresses, the fits, the turn and the reflection, as tile_picture::fields sent them.
  {
    const tile_picture::Ask a = plugin_ask();
    const Question q = tile_picture::question(a, Owner::PLUGIN_TILE, a.entity);
    assert(as_map(legacy(q)) == as_map(tile_picture::fields(a)));
    const std::string text = json(q);
    assert(text.find("\"o\":\"plugin_tile\",\"i\":5,\"p\":\"plugin:cinema.films\"") != std::string::npos);
    assert(text.find("\"fit\":[\"cover\",\"within\"]") != std::string::npos);
    assert(text.find("\"fx\":[{\"turn\":\"right\",\"mirror\":1},{}]") != std::string::npos);
  }
  // A plugin's card and its screensaver: card_fields, and the screensaver's with `saver` for `card`.
  {
    tile_picture::Ask a = plugin_ask();
    a.entity = "plugin:cinema.film";  // a card's ask names the card (plugin_host card_ask)
    const Question card = tile_picture::question(a, Owner::PLUGIN_CARD, "plugin:cinema.film", "media_player.tv");
    auto expected = tile_picture::card_fields(a, "media_player.tv");
    assert(as_map(legacy(card)) == as_map(expected));
    const Question saver = tile_picture::question(a, Owner::PLUGIN_SAVER, "plugin:cinema.film", "media_player.tv");
    for (auto &f : expected) if (f.first == "card") f.first = "saver";
    assert(as_map(legacy(saver)) == as_map(expected));
  }
  // The full view of a camera on a P4 with a larger cap, streaming with its sound.
  {
    Question q;
    q.owner = Owner::VIEW;
    q.sources = {camera_source("camera.porch")};
    q.w = 1280, q.h = 800;
    q.cap = 2u << 20;
    q.live_w = 1280, q.live_h = 715, q.sound = true;
    const auto old = as_map(legacy(q));
    const std::map<std::string, std::string> want{{"entity", "camera.porch"}, {"size", ""}, {"bg", ""}, {"cap", "2097152"},
                                                  {"live", "1280x715"}, {"sound", "1"}};
    assert(old == want);
  }
  // A map tile's full view: its entity, its tile, the look, the person a finger picked and the keys' moves.
  {
    Question q;
    q.owner = Owner::VIEW;
    q.of = "person.sam";
    q.dark = true;
    q.sources = {map_source(4, "person.alex", "2,1,-1")};
    assert(q.sources[0] == "map:4?focus=person.alex&move=2,1,-1");
    const std::map<std::string, std::string> want{{"entity", "person.sam"}, {"size", ""}, {"bg", ""}, {"idx", "4"},
                                                  {"dark", "1"}, {"focus", "person.alex"}, {"move", "2,1,-1"}};
    assert(as_map(legacy(q)) == want);
  }
  // The screensaver's cover, camera and photo.
  {
    Question q;
    q.owner = Owner::SAVER;
    q.sources = {cover_source("media_player.kitchen")};
    assert(as_map(legacy(q)).at("saver") == "media" && as_map(legacy(q)).at("entity") == "media_player.kitchen");
    q.sources = {camera_source("camera.porch")};
    assert(as_map(legacy(q)).at("saver") == "camera");
    q.sources = {PHOTOS_SOURCE};
    q.of = "screen.photos";
    assert(as_map(legacy(q)).at("saver") == "photos" && as_map(legacy(q)).at("entity") == "screen.photos");
  }
  // A media card's cover and a vacuum card's map.
  {
    Question q;
    q.owner = Owner::CARD;
    q.sources = {cover_source("media_player.kitchen")};
    q.w = q.h = 240;
    Place p;
    p.w = p.h = 240;
    p.radius = 20;
    p.ground = 0x1C1C1E;
    q.places = {p};
    const std::map<std::string, std::string> cover{{"entity", "media_player.kitchen"}, {"size", "240"}, {"bg", "1C1C1E"}};
    assert(as_map(legacy(q)) == cover);
    q.sources = {vacuum_source("vacuum.robot")};
    q.w = 400, q.h = 260, q.dark = true;
    const std::map<std::string, std::string> map{{"entity", "vacuum.robot"}, {"vmap", "400x260"}, {"bg", "1C1C1E"}, {"dark", "1"}};
    assert(as_map(legacy(q)) == map);
  }
  // A page of a player's library: the items by their numbers, the frames and the page's colour.
  {
    Question q;
    q.owner = Owner::LIBRARY;
    q.sources = {library_source("media_player.kitchen", 7), library_source("media_player.kitchen", 12)};
    Place a, b;
    a.w = a.h = b.w = b.h = 96;
    b.x = 104;
    a.radius = b.radius = 8;
    a.ground = b.ground = 0xF2F2F7;
    q.places = {a, b};
    const std::map<std::string, std::string> want{{"entity", "media_player.kitchen"}, {"lib", "7,12"},
                                                  {"atlas", "[[0,0,96,96,8,0],[104,0,96,96,8,0]]"}, {"bg", "F2F2F7"}};
    assert(as_map(legacy(q)) == want);
    assert(json(q).find("\"src\":[\"library:media_player.kitchen/7\",\"library:media_player.kitchen/12\"]") != std::string::npos);
  }
  // Sources: kind, reference and a query's value.
  assert(kind_of("camera:camera.porch") == "camera" && ref_of("camera:camera.porch") == "camera.porch");
  assert(kind_of("https://x.org/a.jpg").empty() && kind_of("/local/a.png").empty());
  assert(ref_of("map:4?focus=person.alex") == "4" && param_of("map:4?focus=person.alex&move=1", "move") == "1");
  assert(param_of("map:4", "focus").empty());
  // A text with quotes stays one JSON string.
  assert(quoted("a\"b\\c\n") == "\"a\\\"b\\\\c\"");
  // Numbers: one count for every owner; an answer finds how it was asked; the oldest are forgotten.
  {
    Numbers n;
    const uint32_t a = n.ask("cover", "media_player.kitchen", 7);
    const uint32_t b = n.ask("live", "camera.porch", 2);
    assert(a != b);
    assert(n.find(a)->kind == "cover" && n.find(a)->own == 7 && n.find(b)->entity == "camera.porch");
    assert(n.find(b + 1) == nullptr);
    for (size_t i = 0; i < Numbers::KEPT; ++i) n.ask("full", "camera.x", static_cast<uint32_t>(i));
    assert(n.find(a) == nullptr);
  }
  puts("PASS: the question's JSON, its old fields as every owner asked before, sources and numbers");
  return 0;
}
