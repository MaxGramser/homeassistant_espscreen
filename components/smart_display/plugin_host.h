#pragma once
// The core's side of the plugin API (plugin_api.h, docs/PLUGINS.md): a plugin tile in a card, its moments, and what the
// screen says about its plugins. plugin_host.cpp holds it, apart from main.cpp, as energy_view.cpp does.
#include <cstdint>
#include <string>
#include <ArduinoJson.h>
#include "tile_picture.h"

namespace runtime_tiles {
struct Widgets;
struct Tile;
}

namespace plugin_host {
struct Card;  // one plugin tile in one card: the plugin's object and what it was made for
// What a tile of a plugin this screen does not have costs of the layout memory (the add-on's PLACEHOLDER_BYTES).
constexpr uint16_t PLACEHOLDER_BYTES = 64;

// Whether this screen has the tile type of `t` (plugin:<plugin>.<tile>).
bool known(const runtime_tiles::Tile &t);
// Draws the plugin tile into the slot's extra layer, `width` x `height` (the card's content).
void render(runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, int width, int height);
// The card shows something else, or goes: its plugin tile goes with it.
void release(runtime_tiles::Widgets &w);
// A tap on a plugin tile's card, with the finger's place on the glass (-1,-1 unknown): the tile reads it in its own
// pixels through tessera::tap_point().
void tap(runtime_tiles::Widgets &w, int x, int y);
// Once a second: every plugin card on the glass.
void tick_cards(uint32_t epoch);
// A plugin's card over the page (key: plugin:<plugin>.<card>). False when this screen has no such card.
bool open_card(const std::string &key, const std::string &entity, int tile, const std::string &title);
// The plugin card that is open closes; every way Tessera's own cards close calls it (hide_detail).
void close_card();
bool card_open();
// A tile whose tap is a plugin's tap action (plugin:<plugin>.<action>): run it. False when this screen lacks it.
bool tap_action(size_t index);
// An answer of the app for a plugin (op "plugin"): to its on_message.
void message(const std::string &plugin, JsonObjectConst body);
// What one tile costs of the layout memory: the plugin's own number, or the placeholder's.
uint16_t bytes(const std::string &entity);

// A plugin tile's pictures (plugin API 0.10, tile_picture.h "parts"): the places on its card that have an address.
// Whether the card has a place with an address: it asks for a picture, as a pictured tile does.
bool pictured(const runtime_tiles::Widgets &w);
// What the card asks for: every place with an address that lies within the card, as the parts of one picture; false
// when there is none. Each place keeps the piece it takes in that picture, for picture_place.
bool picture_ask(const runtime_tiles::Widgets &w, const runtime_tiles::Tile &t, tile_picture::Ask &a);
// The card's picture (an lv_image_dsc_t of the store, or nullptr for none) onto its places, each its own piece; a
// place whose piece is not in it shows its block again.
void picture_place(runtime_tiles::Widgets &w, void *picture);
// The picture the card's places draw now (its last atlas), nullptr for none: while the next one comes, a card whose
// addresses changed keeps showing it (tile_picture_place), as a tile's own picture keeps its last.
const void *picture_drawn(const runtime_tiles::Widgets &w);
// Whether a place of the card draws this picture (the store frees nothing a card draws).
bool picture_draws(const runtime_tiles::Widgets &w, const void *picture);
// The places let go of this picture (nullptr: of every picture): another layout, or the store takes it off a page out
// of sight. True when one did.
bool picture_let_go(runtime_tiles::Widgets &w, const void *picture);
// Pictures on a plugin's card over the page (plugin API 0.13): what the open card wants this round (pictures_round), the
// app's answer to its question ("pcard", with the question's number), whether a number is its last question's, whether
// its places draw this picture (the store frees nothing a card draws), and the full view's download going away (a board
// without the store draws from it).
void card_picture_want();
void card_picture_answer(const std::string &card, const std::string &url, uint32_t number);
bool card_question(uint32_t number);
bool card_draws(const void *picture);
void card_letgo(const void *download);

// The moments of every plugin.
void ready();
// Every 250 ms; `dimmed`: the screen is in standby (a change of it is on_standby).
void tick(uint32_t now_ms, bool dimmed);
void standby(bool dark);
void before_update();
// plugin_api and plugins ([{id, version, tiles}]) in the screen's answer to the add-on's hello.
void hello(JsonObject root);
}  // namespace plugin_host
