// The question of every owner as the firmware builds it (picture_question.h, tile_picture.h), printed for
// tests/test_pictures.py: one line each, `name<TAB>json<TAB>old fields as a JSON object`. That test reads the JSON as the
// app reads a question (picture_question.parse) and the old fields as it reads an older screen's (picture_legacy.read),
// and both must give the same question. Built by that test; no test of its own (tests/*.cpp are).
#include "../../components/smart_display/picture_question.h"
#include "../../components/smart_display/tile_picture.h"
#include <cstdio>
#include <string>

using namespace picture_question;

static void print(const char *name, const Question &q) {
  std::string old = "{";
  bool first = true;
  for (const auto &f : legacy(q)) {
    old += (first ? "" : ",") + quoted(f.first) + ":" + quoted(f.second);
    first = false;
  }
  std::printf("%s\t%s\t%s}\n", name, json(q).c_str(), old.c_str());
}

static tile_picture::Ask tile_ask() {
  tile_picture::Ask a;
  a.index = 3;
  a.entity = "camera.porch";
  a.frame = tile_picture::frame(240, 160, 12, 0, 0x202020, 0x000000);
  a.circle = 48;
  a.every = 15000;
  return a;
}

static tile_picture::Ask plugin_ask(const char *entity) {
  tile_picture::Ask a;
  a.index = 5;
  a.entity = entity;
  std::vector<tile_picture::Part> parts(2);
  parts[0] = {0, 10, 90, 140, 6, "https://image.tmdb.org/t/p/w342/a.jpg", false, 2, true};
  parts[1] = {105, 0, 90, 156, 6, "cover:media_player.tv", true, 0, false};
  tile_picture::set_parts(a, parts, 0x101010);
  return a;
}

static Place place(int x, int y, int w, int h, int radius, uint32_t ground) {
  Place p;
  p.x = x, p.y = y, p.w = w, p.h = h, p.radius = radius, p.ground = ground;
  return p;
}

int main() {
  print("camera tile", tile_picture::question(tile_ask()));
  {
    tile_picture::Ask a = tile_ask();
    a.dark = true;
    a.frame = tile_picture::frame(240, 240, 12, 170, 0x1C1C1E, 0x000000);
    a.entity = "media_player.kitchen";
    print("cover tile, dark", tile_picture::question(a));
  }
  print("plugin tile", tile_picture::question(plugin_ask("plugin:cinema.films"), Owner::PLUGIN_TILE, "plugin:cinema.films"));
  print("plugin card", tile_picture::question(plugin_ask("plugin:cinema.film"), Owner::PLUGIN_CARD, "plugin:cinema.film", "media_player.tv"));
  print("plugin saver", tile_picture::question(plugin_ask("plugin:cinema.film"), Owner::PLUGIN_SAVER, "plugin:cinema.film", "media_player.tv"));
  // The whole glass, as runtime_tiles::camera_request asks for it: one place over the box, its fit and effects.
  {
    Question q;
    q.owner = Owner::VIEW;
    q.sources = {camera_source("camera.porch")};
    q.w = 1280, q.h = 800;
    q.cap = 2u << 20;
    q.pace = 4000;
    Place p = place(0, 0, 1280, 800, 0, 0);
    p.fit = Fit::SHRINK;
    q.places = {p};
    print("camera full view", q);
    q.live_w = 1280, q.live_h = 715, q.sound = true;
    print("camera full view, live", q);
  }
  {
    Question q;
    q.owner = Owner::VIEW;
    q.of = "person.sam";
    q.dark = true;
    q.w = 480, q.h = 480;
    q.sources = {map_source(4, "person.alex", "2,1,-1")};
    Place p = place(0, 0, 480, 480, 0, 0);
    p.fit = Fit::EXACT;
    q.places = {p};
    q.formats = {"bmp8", "bmp24"};
    print("map opened", q);
  }
  {
    Question q;
    q.owner = Owner::SAVER;
    q.w = 480, q.h = 480;
    q.formats = {"bmp8", "bmp24"};
    Place p = place(0, 0, 480, 480, 0, 0);
    p.fit = Fit::SAVER;
    p.dim = 30;
    q.places = {p};
    q.sources = {cover_source("media_player.kitchen")};
    print("screensaver cover", q);
    p.fit = Fit::COVER;
    q.places = {p};
    q.pace = 15000;
    q.sources = {camera_source("camera.porch")};
    print("screensaver camera", q);
    p.fit = Fit::AUTO;
    p.dim = 0;
    p.move = 8;
    q.places = {p};
    q.pace = 0;
    q.sources = {PHOTOS_SOURCE};
    q.of = "saver.photos";
    print("screensaver photos", q);
  }
  {
    Question q;
    q.owner = Owner::CARD;
    q.sources = {cover_source("media_player.kitchen")};
    q.w = q.h = 240;
    q.places = {place(0, 0, 240, 240, 20, 0x1C1C1E)};
    print("media card cover", q);
    // As module_vacuum_card's map_request asks for it.
    q.sources = {vacuum_source("vacuum.robot")};
    q.w = 400, q.h = 260, q.dark = true;
    Place map = place(0, 0, 400, 260, 0, 0x1C1C1E);
    map.fit = Fit::EXACT;
    q.places = {map};
    q.formats = {"bmp8", "bmp24"};
    print("vacuum map", q);
  }
  {
    Question q;
    q.owner = Owner::LIBRARY;
    q.sources = {library_source("media_player.kitchen", 7), library_source("media_player.kitchen", 12)};
    q.w = 200, q.h = 96;
    q.places = {place(0, 0, 96, 96, 8, 0xF2F2F7), place(104, 0, 96, 96, 8, 0xF2F2F7)};
    print("library page", q);
  }
  return 0;
}
