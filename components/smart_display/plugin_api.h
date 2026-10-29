#pragma once
// The plugin API (docs/PLUGINS.md): what an ESPHome component of someone else may use to add a tile type and to hear
// about the screen's moments, without the core knowing that plugin exists.
//
// A plugin is a component of its own (`components/<name>/` in its repository) that derives from tessera::Plugin and
// registers its tile types in setup(), never in its constructor: the code generation hands it its id after it is made
// (set_identity), and a tile type is keyed by that id. The core keeps a list; nothing in the core names a plugin.
// A tile of a plugin is `plugin:<plugin>.<tile>` in a layout. The core gives it a card's drawing area while its page is
// on the glass, hands it what the add-on sent for it, ticks it once a second and lets it go when the card shows
// something else. A tile type the screen does not have (the plugin is not, or no longer, on this screen) is drawn by
// the core as a plain card with the tile's name: never an error, never a restart.
//
// Drawing follows the rules of the rest of the screen: sizes through ui::mm()/ui::px(), colours by a theme role, only
// the screen's fixed fonts, and nothing exists while the tile is not on the glass (docs/PLUGINS.md, "Drawing").
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
#include <ArduinoJson.h>
#include "lvgl.h"
#include "audio_owner.h"
#include "hw.h"
#include "roomy.h"
#include "theme.h"
#include "ui_scale.h"

namespace tessera {

// Major.minor (plugin_manifest.PLUGIN_API in the add-on and PLUGIN_API in __init__.py are the same; a test keeps them
// equal, and docs/PLUGINS.md names the same number). A plugin's manifest names the API it was written for
// (`api: "0.2"`); its component checks it when it is built, so a core that is too old says so in one sentence instead
// of a compiler error. A plugin builds on every core with the same major and at least its minor.
// From 1.0 on that is a promise: a minor only adds, and only a break raises the major. Major 0 is the time before
// the API is promised to anyone: a minor may still change a name or a signature while the API settles, and Tessera's
// own plugins move with it in the same release. A minor may take a form away: a plugin that still uses it fails its
// build with the compiler's error at that call (0.24). PLUGIN_API_BREAKS (__init__.py, plugin_manifest.py) is for a
// minor after which an older plugin would still build but work wrongly (0.4, where on_tick changed its meaning): such a
// plugin is refused in one sentence. What each minor brought and took away: the plugins repository's
// docs/FIRMWARE_API.md, "Versions".
constexpr uint8_t PLUGIN_API_MAJOR = 0, PLUGIN_API_MINOR = 24;

// The screen's fixed fonts, largest first. A tile takes the largest that fits; a plugin brings no font of its own.
// VALUE is the big number of a watch card, HEADLINE a card's large words, TITLE a card's name, BODY its second line,
// BODY_LARGE the words on a key, ICON a tile's icon, ICON_SMALL the icons of the top bar. Every text font has the same
// letters (Latin with the accents of the screen's languages, digits and common signs); the icon fonts have Tessera's
// icon set only. DIGITS (0.9) is the largest: a climate card's setpoint, with the digits and - . , ° % alone, so a
// tile takes it only for a value ui::covers() and steps down to VALUE for any other (a word, a unit, a letter).
enum class Font : uint8_t { VALUE, HEADLINE, TITLE, BODY_LARGE, BODY, ICON, ICON_SMALL, DIGITS };
// What came of a place's picture (0.17, on_picture): SHOWN, it is on its place; NONE, the app has no picture at that
// address now (it asks again later, each time after a longer while); FAILED, it did not come (the download broke off).
enum class PictureState : uint8_t { SHOWN, NONE, FAILED };

// What a tile gets when its card is made. It is valid during create() only: `name`, `entity` and `options` point into
// the core's own storage and the JSON document of the call, so a tile copies what it needs into members of its own.
struct TileContext {
  lv_obj_t *parent;          // the card's drawing area: everything the tile makes goes in here, and dies with it
  int width, height;         // that area in pixels (the card's own padding is already off)
  uint8_t columns, rows;     // the cells of the grid the tile covers
  const char *name;          // the name given to the tile in the editor, "" for none (copy it)
  const char *entity;        // its Home Assistant entity (plugin_entity), "" for none (copy it)
  int tile;                  // its index in the layout, for tessera::open_card from on_tap
  // The tile's options as the editor set them (the manifest's `options`, its defaults filled in); gone after create().
  // A text, number or toggle is that value, a choice its value. A list option (0.12, `multiple`) is an array: of texts,
  // or for a choice of picks, {"value": "...", "label": "..."} with the words the person saw in the list; a choice found
  // by searching (`search`) without `multiple` is one pick (or "" while none is chosen).
  JsonObjectConst options;
};

// Memory for what a plugin keeps (0.10). The memory inside the chip is small and Wi-Fi needs it; a board with PSRAM has
// megabytes there, and a plain std::string, std::vector or `new` never lands in it (the boards build with
// CONFIG_SPIRAM_USE_CAPS_ALLOC). Keep texts and lists a tile holds as Text and List: PSRAM first, the ordinary heap on a
// board without it, and otherwise a std::string and a std::vector: data(), size(), c_str(), +=, == against another Text
// or a quoted text; roomy::same() compares it with a std::string, roomy::plain() makes one of it, roomy::text() the
// other way. ui::set_text takes a std::string: ui::set_text(label, roomy::plain(text)), or keep a short text you show in
// a char array. A Tile and a Card are made in PSRAM by themselves (their operator new), so fixed
// members (numbers, char arrays, pointers) are there already.
using Text = roomy::Text;
template <class T> using List = roomy::List<T>;
// The operator new of a plugin's objects: PSRAM first; aborts only when no memory has room, as `new` does.
struct InPsram {
  static void *operator new(size_t size) {
    void *p = roomy::allocate(size);
    if (!p) std::abort();
    return p;
  }
  static void operator delete(void *p) { roomy::release(p); }
};

// A tile type's card. One object per card on the glass; a page switch on a board without PSRAM makes a new one.
class Tile : public InPsram {
 public:
  virtual ~Tile() = default;
  // Make the parts, in context.parent. Called once per card, before anything else.
  virtual void create(const TileContext &context) = 0;
  // What the add-on sent for this tile: for a tile with `data: <fetch>` the mapped answer ({"items": [...]} or the
  // fields of one object), plus "stale": true while the add-on shows its last good answer and "wait": "<why>" while it
  // has none (not_filled, asking, failed, too_large). A tile with an entity also gets "state", "name" and "attributes"
  // (the ones its manifest names; a moment named ..._at, ..._time or ...date as seconds since 1970), and is sent again
  // when that entity changes in Home Assistant. Called after create(), and again when the card is drawn after the
  // data changed (a card off the glass catches up when its page comes back).
  virtual void on_state(JsonObjectConst data) {}
  // Once a second while the card is on the glass, with the screen's clock (seconds since 1970, 0 until it is set).
  virtual void on_tick(uint32_t epoch) {}
  // The screen went light or dark: set the colours again (theme roles have another value now).
  virtual void on_theme() {}
  // A tap on the tile that the touch filter let through (tap_point() says where).
  virtual void on_tap() {}
  // What came of the picture of one of its places (0.17): once when it is on its place, or when it did not come, and
  // again when that changes (a new address, a picture that comes after all). A place shows its block, or nothing (its
  // Placeholder), until then: show something of your own where it stays NONE or FAILED.
  virtual void on_picture(lv_obj_t *place, PictureState state) {}
};

// What a card gets when it opens. A card is a screen of its own over the page: Tessera draws its frame (the page's
// ground, a round back key at the top left, the title in the middle), the card draws everything under it.
struct CardContext {
  lv_obj_t *parent;          // the room under the card's top bar: everything the card makes goes in here
  int width, height;         // that room in pixels
  const char *entity;        // the entity it was opened for (a tap action on a tile, a plugin tile's entity), "" for none
  int tile;                  // the layout's tile it was opened from, -1 for none
};

// A card of a plugin: opened by a tap action, a plugin tile (tessera::open_card in its on_tap) or a settings row.
// One is open at a time; it closes with Back, standby, Back to page 1 or another card, as every card does. A card may
// close itself (tessera::close_card) or open another (tessera::open_card) from any of its own calls: it leaves the
// glass at once, gets no call after that one, and is deleted only once that call has returned.
class Card : public InPsram {
 public:
  virtual ~Card() = default;
  virtual void open(const CardContext &context) = 0;
  // The tile it was opened from changed: a plugin tile's data (as Tile::on_state), or {"state", "name"} of an entity.
  virtual void on_state(JsonObjectConst data) {}
  // Once a second while it is open, with the screen's clock.
  virtual void on_tick(uint32_t epoch) {}
  virtual void on_theme() {}
  // Back was pressed: true keeps the card open (it went back a step of its own), false lets it close.
  virtual bool on_back() { return false; }
  // A tap on the card's room (CardContext::parent) that the touch filter let through (0.12): a finger that moved or
  // was too short never comes, a bounce on the same spot within 600 ms is one tap, a tap on another spot is its own.
  // tap_point() says where, in the card's own pixels, so a list knows its row. The objects of tessera::ui take no taps,
  // so a tap on them comes here; an LVGL object of the plugin's own that is clickable takes the tap itself. Back is
  // on_back, never this. The card may close itself or open another from here.
  virtual void on_tap() {}
  // What came of the picture of one of its places (0.17), as Tile::on_picture.
  virtual void on_picture(lv_obj_t *place, PictureState state) {}
};

// How a part moves (0.18, ui::animate). PULSE: its opacity goes from full to a fifth and back. SPIN: it turns around its
// middle (a ring with one side drawn, an icon). RIPPLE: it grows to half again its size while it fades out, as a ripple
// on water, and starts again.
enum class Motion : uint8_t { PULSE, SPIN, RIPPLE };

// How wide a popup is (0.18): ALERT, as an alert's card on this glass and at least two fifths of the glass's width (for
// words, a question and its answer); WIDE, the glass less its edge on each side (a list, a row of keys).
enum class PopupWidth : uint8_t { ALERT, WIDE };

// What a popup gets when it shows (0.18): the room inside its card. The card is as high as what the popup puts in the
// room, up to `height`: lay the parts out from the top, and the card follows when they grow or shrink (a part that is
// hidden takes no room). What lies below `height` is cut off; a part that moves (ui::animate) may reach out over the
// room's edge into the card's.
struct PopupContext {
  lv_obj_t *parent;          // the card's room, inside its edge: everything the popup makes goes in here
  int width, height;         // the room's width, and the most it may grow to on this glass, in pixels
  int key;                   // the close key's size: it stands in the room's top right corner, as high as a first row
                             // of that size (a disc, an icon) at the top left, on the same line and as far in
  int corner;                // how far the first row keeps from the right for it: the key and a gap
};

// A popup of a plugin (0.18, docs/PLUGINS.md "A popup"): the card an alert of Home Assistant shows (its width on this
// glass, its corners and colours, in the middle over the dimmed screen), as high as what the plugin draws in it, for a
// moment that wants the eye now: a voice assistant that listens, thinks and answers, a timer that went off, a question.
// Its top right corner holds the round close key of every card's top bar (PopupContext::corner). It lies over the page,
// a card, the settings and the screensaver, and under an alert. One shows at a time, of any plugin, and showing one
// lights a dark screen (as wake() does), also one that Home Assistant's Sleep put out. It goes when its plugin closes it
// (tessera::close_popup) or shows another, and by itself on its close key, a tap beside the card, when the screen goes
// dark, before an update and when an alert comes: then it hears on_dismiss first. It may close itself from any of its
// own calls; it leaves the glass at once and is deleted once that call returned. It shows no pictures (ui::picture).
class Popup : public InPsram {
 public:
  virtual ~Popup() = default;
  virtual void open(const PopupContext &context) = 0;
  // Every 250 ms while it shows, with millis(): for what moves on by itself (words that come one by one).
  virtual void on_interval(uint32_t now_ms) {}
  // Once a second while it shows, with the screen's clock.
  virtual void on_tick(uint32_t epoch) {}
  virtual void on_theme() {}
  // A tap on the card through the touch filter, as Card::on_tap: tap_point() says where, in the room's pixels.
  virtual void on_tap() {}
  // It goes by itself (its close key, a tap beside it, the screen going dark, an update, an alert, another plugin's
  // popup): the last call before it is deleted. Not when its own plugin closed it or showed another.
  virtual void on_dismiss() {}
};

// A tap action on a tile of Home Assistant's own (a thermostat that opens the plugin's schedule): what it was tapped on.
// One step of a value under the finger, for on_step (0.11): `direction` +1 towards the larger end of its range, -1
// towards the smaller, 0 when not known (a held key); `edge` when it reached either end, for a firmer click there.
struct Step {
  int8_t direction;
  bool edge;
};

struct TapContext {
  const char *entity;        // the tile's entity
  const char *name;          // the tile's name
  int tile;                  // its index in the layout
};

// The rows a plugin adds to the screen's settings page (hold the top bar): Settings > Plugins > the plugin's page,
// drawn exactly as Tessera's own rows. A value lives where the plugin keeps it, usually an ESPHome entity of its
// plugin.yaml (a switch, a number, a select), so Home Assistant and the app show and change the same thing.
class SettingsPage {
 public:
  struct Item {
    enum Kind : uint8_t { TOGGLE, NUMBER, CHOICE, ACTION, INFO, CARD } kind;
    std::string label, confirm, icon, card;
    int low = 0, high = 0, step = 1;
    std::string unit;
    std::vector<std::string> options;
    std::function<int()> read;
    std::function<void(int)> write;
    std::function<void()> run;
    std::function<std::string()> text;
    std::function<bool()> active;
  };
  // A switch: on or off.
  SettingsPage &toggle(const char *label, std::function<bool()> read, std::function<void(bool)> write);
  // A number between low and high in steps, with - and + keys and a unit straight after it ("%", " min").
  SettingsPage &number(const char *label, int low, int high, int step, const char *unit, std::function<int()> read,
                       std::function<void(int)> write);
  // One of a few words; a tap takes the next.
  SettingsPage &choice(const char *label, std::vector<std::string> options, std::function<int()> read,
                       std::function<void(int)> write);
  // A row that does something on a tap; with `confirm` it asks once ("Tap again to ...") as Restart does. With `text`
  // it says how it is going on its right ("Playing", "3 s"), read again every second while the page shows (0.3).
  SettingsPage &action(const char *label, const char *icon, std::function<void()> run, const char *confirm = nullptr,
                       std::function<std::string()> text = nullptr);
  // The action added last runs now while `running` says so: its row is lit in the accent, as a row that asks is, and a
  // tap on it is the plugin's to stop it (0.3). `page.action(...).active([this] { return testing_; });`
  SettingsPage &active(std::function<bool()> running);
  // A line that only says something ("Version 1.1.0").
  SettingsPage &info(const char *label, std::function<std::string()> text);
  // A row that opens a card of this plugin (by its id in the manifest).
  SettingsPage &card(const char *label, const char *icon, const char *card);
  std::string title, icon;   // the page's title (the plugin's name when left empty) and its row's icon
  std::vector<Item> items;
};

// What an item of a plugin in the top bar shows now: an icon of Tessera's set and a short text, or nothing.
// The colour of a top bar item's icon (0.8), by what it means: the core picks the colour, in both looks. NORMAL is the
// bar's own grey; ACCENT the screen's blue (it listens, it is on); BUSY Home Assistant's amber (it works on something);
// ALERT its red (a camera that streams, something that went wrong). GOOD (0.9) its green (a level that is fine, a full
// battery). The same tones colour a tile's labels (ui::set_tone) and its blocks (ui::set_fill), a bar or a dot.
enum class Tone : uint8_t { NORMAL, ACCENT, BUSY, ALERT, GOOD };
// How a picture fills its place (0.10): COVER fills the place and cuts away what is over (a poster in a poster's
// frame), CONTAIN shows the whole picture within it, on the card's own colour (a logo, a map).
enum class Fit : uint8_t { COVER, CONTAIN };
// How a picture turns in its place (0.10), as the covers beside the middle one of a cover flow turn to face it: the app
// draws the whole picture in perspective within the place, its near edge the place's height and its far edge 70 % of
// it. LEFT faces the left (its left edge far: a cover right of the middle), RIGHT faces the right (a cover left of it).
enum class Turn : uint8_t { NONE, LEFT, RIGHT };
// What a place shows until its picture is there (0.17, ui::picture): BLOCK, the soft block of a key's colour (TRACK);
// NONE, nothing, so what lies under the place shows (places that lie over each other, a reflection that reaches past
// its picture).
enum class Placeholder : uint8_t { BLOCK, NONE };
// A reflection under a picture (0.10, ui::set_picture's `mirror`): it takes this share of the picture's height under it,
// within the place, so a place for a picture of height h with its reflection is h * (100 + MIRROR_PERCENT) / 100 high.
constexpr int MIRROR_PERCENT = 30;
struct BarItem {
  bool shown = false;
  uint32_t icon = 0;         // a codepoint of Tessera's icon set (0xF00E7), 0 for none
  std::string text;          // a few words ("Tomorrow: paper"), "" for an icon alone; a person may show the icon alone
  Tone tone = Tone::NORMAL;  // the icon's colour; the words keep the bar's
};

class Plugin;
struct BarItemType {
  Plugin *plugin;
  std::string id, key;       // the item's id in the manifest, and plugin:<plugin>.<item>
  std::function<BarItem()> read;
};
struct CardType {
  Plugin *plugin;
  std::string id, key;       // the card's id in the manifest, and plugin:<plugin>.<card>
  bool wide;                 // as wide as the glass (a picture, a timeline), else a hand's width like Tessera's cards
  std::function<Card *()> make;
};
struct TapAction {
  Plugin *plugin;
  std::string id, key;       // the action's id in the manifest, and plugin:<plugin>.<action>
  std::function<void(const TapContext &)> run;
};
// ---- A screensaver (0.14, docs/PLUGINS.md "A screensaver") ----
// The screensaver is a list of steps the person orders in the editor: the music that plays, the photos of a folder, a
// camera, the clock, and steps of plugins. ESP Screen Manager picks the first that has something to show; the screen
// shows it over the whole glass while Auto standby dims it, at the standby or night level. Tessera decides WHEN a step
// shows (and takes it away when a finger wakes the screen, an alert comes, an update starts, or the level goes to 0); a
// plugin decides HOW it looks. A plugin's saver is either a face of one of Tessera's steps (`step` CLOCK, MEDIA or
// PHOTOS: it draws from what that step knows, the same data Tessera's own face has) or a step of its own (OWN: it draws
// from its fetch and its entity, as a plugin tile, and its manifest's `when` says when it has something to show).
enum class SaverStep : uint8_t { CLOCK, MEDIA, PHOTOS, OWN };
// What a saver gets when it comes on the glass. Valid during show() only (copy what you keep).
struct SaverContext {
  lv_obj_t *parent;          // the whole glass, black, on LVGL's top layer: everything the saver makes goes in here
  int width, height;         // the glass in pixels
  SaverStep step;
  uint8_t level;             // the backlight's level in percent (the standby or the night level; never 0)
  bool night;                // the night levels hold now: a face may go darker still
  JsonObjectConst options;   // the saver's options as the person set them in the editor (the manifest's `options`)
};
// A face of the music or the photos whose manifest says `backdrop: true` has the step's own picture under it: the cover
// or the photo over the whole glass, moving slowly where the person chose so for the photos, as Tessera's own face shows
// it but without its words and keys. The saver's glass is then clear, and it draws only what goes over the picture (a
// clock over the photos); it needs no place of its own for that picture.
// A screensaver of a plugin: one object while it is on the glass, deleted when it leaves. It never exists off the glass.
// It is drawn in the dark look whatever the screen's look, as Tessera's own clock: theme roles (ui::color, ui::label)
// give their dark values in every call of a saver, on the black glass, so the glass gives as little light as it can.
// Tessera moves the whole saver up to a millimetre every minute so nothing stands on the same pixels for hours, unless
// the manifest says `moves: true` (the saver moves itself, as a clock that turns or a picture that changes).
class Saver : public InPsram {
 public:
  virtual ~Saver() = default;
  // Make the parts, in context.parent. Called once, before anything else.
  virtual void show(const SaverContext &context) = 0;
  // What the step knows (the contract of its step in docs/PLUGINS.md "A screensaver"): for MEDIA the player and what it
  // plays, for CLOCK the temperature and the row of entities, for PHOTOS the photo, for OWN the fetch's answer and the
  // entity, as a tile's on_state. Called after show(), and again whenever it changed (a wish of the finger shows here
  // at once, wish()). Fields only come to it; none is renamed or taken away within major 0.
  virtual void on_state(JsonObjectConst data) {}
  // Once a second while it is on the glass, with the screen's clock (seconds since 1970, 0 until it is set). Paint what
  // changed, never the whole saver: the glass draws only the boxes that changed.
  virtual void on_tick(uint32_t epoch) {}
  // A tap on a part made with ui::takes_taps, through the touch guard every key passes; tap_point() says where, in the
  // glass's pixels. The screen stays in standby. A tap anywhere else wakes the screen and the saver goes.
  virtual void on_tap() {}
  // A finger held on such a part for a second and a half (as volume down held mutes on Tessera's own player face).
  virtual void on_hold() {}
  // What came of the picture of one of its places (0.17), as Tile::on_picture.
  virtual void on_picture(lv_obj_t *place, PictureState state) {}
};
struct SaverType {
  Plugin *plugin;
  std::string id, key;       // the saver's id in the manifest, and plugin:<plugin>.<saver>
  SaverStep step;
  std::function<Saver *()> make;
};
// What wish() can change (0.14), the fields of Tessera's own controls (optimistic.h): the player's play and pause ("1"
// playing, "0" not), its mute ("1", "0"), and an entity's on and off ("on", "off").
enum class Wish : uint8_t { PLAYING, MUTED, ON_OFF };

struct TileType {
  Plugin *plugin;
  std::string id, key;       // the tile's id in the manifest, and plugin:<plugin>.<tile> (its entity in a layout)
  std::function<Tile *()> make;
};

class Plugin {
 public:
  Plugin();
  virtual ~Plugin() = default;
  // The plugin's id and version, from its manifest (set by smart_display.register_plugin() in its __init__.py).
  const char *plugin_id() const { return id_; }
  const char *plugin_version() const { return version_; }
  // The screen's interface is up and its first page is on the glass. It comes after every component's setup(), also
  // one of priority LATE; so do settings() and the first on_interval.
  virtual void on_ready() {}
  // Every 250 ms, the screen's own interval, with millis() (0.4; on_tick before it). Keep it short: the screen draws
  // and takes taps in the same loop. A tile's or a card's on_tick is another thing: once a second, with the clock.
  virtual void on_interval(uint32_t now_ms) {}
  // The screen dimmed or went dark (true), or woke up again (false).
  virtual void on_standby(bool dark) {}
  // An update of the firmware starts: let go of large buffers.
  virtual void before_update() {}
  // The cards closed (Back, standby, Back to page 1, another card), 0.2.
  virtual void on_cards_closed() {}
  // An alert is about to show (a doorbell), 0.2.
  virtual void on_alert() {}
  // A finger came down on something that takes a tap or a drag: a tile, a key, a slider, a row of the settings, the
  // top bar. At once, before the screen knows whether it becomes a tap, a hold or a swipe, so a click answers the finger
  // (0.11). Not for the push that wakes a dimmed screen, nor between the tiles. Runs inside the touch: start a sound,
  // never wait for one.
  virtual void on_press() {}
  // A value under the finger stepped (0.11): a dragged slider, dial or seek bar passed a step (every 5 % of its range, or
  // every position of one with 20 or fewer), or a held key stepped once more. Once for every step, two at most at once,
  // as a detent clicks; not for the jump of a slider to where the finger lands. For a detent you can hear or feel:
  // SoundPlayer::add() spaces a run of clicks evenly. The moments of touch_feedback.h (docs/PLUGINS.md, "Touch feedback").
  virtual void on_step(const Step &step) {}
  // Rows on the screen's settings page. Called once when the interface is up; true when the plugin added some.
  virtual bool settings(SettingsPage &page) { return false; }
  // An answer from the app to tessera::send(): {"re": <the number send returned>, "ok": true, "result": ...} or
  // {"re": ..., "ok": false, "error": "<why>"}. At most 4 KB; a long answer comes shortened (lists and texts cut).
  virtual void on_message(JsonObjectConst message) {}

  // A tile type of this plugin, by its id in the manifest. Call it in setup(). `make` returns a new card; the core
  // deletes it.
  void add_tile(const char *id, std::function<Tile *()> make);
  // A card of this plugin, by its id in the manifest (`cards`). `wide`: it takes the whole width of the glass.
  void add_card(const char *id, std::function<Card *()> make, bool wide = false);
  // A tap action for tiles of Home Assistant's own (manifest `tap_actions`): a tile whose tap is set to it in the
  // editor runs `run` on a short tap instead of its own action.
  void add_tap_action(const char *id, std::function<void(const TapContext &)> run);
  // An item for the top bar (manifest `bar_items`), placed on a page's bar in the editor. `read` says what it shows now;
  // the screen asks again every few seconds and draws the bar again when that changed.
  void add_bar_item(const char *id, std::function<BarItem()> read);
  // A screensaver of this plugin (manifest `savers`, 0.14), by its id; `step` must be the manifest's. Call it in setup().
  void add_saver(const char *id, SaverStep step, std::function<Saver *()> make);
  // Set by the code generation (smart_display.register_plugin() in the plugin's __init__.py), from the plugin's
  // manifest and its translations/<language>.json (part "screen", in the language the screen is built with).
  void set_identity(const char *id, const char *version) { id_ = id; version_ = version; }
  void set_text(const char *key, const char *text) { texts_.push_back({key, text}); }
  void set_memory(const char *tile, uint16_t bytes) { memory_.push_back({tile, bytes}); }
  // A screensaver of the manifest's `moves: true` (0.14): it moves itself, and the host leaves it where it draws.
  void set_moves(const char *saver) { moving_.push_back(saver); }
  bool moves(const std::string &saver) const {
    for (const char *id : moving_) if (saver == id) return true;
    return false;
  }
  // A screensaver of the manifest's `backdrop: true` (0.14): the screen shows the step's own picture under it.
  void set_backdrop(const char *saver) { backdrops_.push_back(saver); }
  bool backdrop(const std::string &saver) const {
    for (const char *id : backdrops_) if (saver == id) return true;
    return false;
  }
  // A screensaver of the manifest's `taps: true` (0.14): its parts may take taps (ui::takes_taps).
  void set_taps(const char *saver) { tapping_.push_back(saver); }
  bool taps(const std::string &saver) const {
    for (const char *id : tapping_) if (saver == id) return true;
    return false;
  }
  // A text of the plugin's own, "" when it has none by that key.
  const char *text(const char *key) const;
  // What one tile of this type costs of the layout memory (the manifest's `memory`), 1024 when it was not set.
  uint16_t memory(const std::string &tile) const;

 private:
  std::vector<std::pair<const char *, const char *>> texts_;
  std::vector<std::pair<const char *, uint16_t>> memory_;
  std::vector<const char *> moving_, tapping_, backdrops_;
  const char *id_ = "", *version_ = "";
};

// The register. Each list is made on first use, so the order components are made in does not matter.
std::vector<Plugin *> &plugins();
std::vector<TileType> &tile_types();
const TileType *tile_type(const std::string &key);
std::vector<CardType> &card_types();
std::vector<TapAction> &tap_actions();
std::vector<BarItemType> &bar_items();
std::vector<SaverType> &saver_types();

// ---- What the core offers a plugin ----
// The screen's clock: seconds since 1970, 0 until Home Assistant set it.
uint32_t epoch();
// A moment in the screen's own time zone (the one Home Assistant gave it).
struct LocalTime {
  int year, month, day;          // 2026, 1 to 12, 1 to 31
  int hour, minute, second;      // 0 to 23, 0 to 59, 0 to 59
  int weekday;                   // 1 Sunday to 7 Saturday
};
LocalTime local_time(uint32_t epoch);
// A time of day as the screen writes it (12 or 24 hours, as its settings say): "14:05" or "2:05 PM".
std::string clock_text(uint32_t epoch);
// "{n}" in `text` replaced by `n`; with "one | more" in `text` (Tessera's plural form), the part that fits `n`.
std::string format(const char *text, long n);
// How many days from today a moment is on the screen's own calendar: 0 today, 1 tomorrow, -1 yesterday. A large
// negative number (INT32_MIN) while the clock is not set.
int32_t days_from_today(uint32_t epoch);
// A day as the top bar writes it in the screen's language: "Fri 9 Oct", "vr 9 okt".
std::string date_text(uint32_t epoch);
// "Tomorrow", "In 3 days" in the screen's language; "" for today and the past (a plugin has its own word for today).
std::string days_text(int32_t days);
// "{name}" in `text` replaced by `value`, wherever the language put it.
std::string fill(const char *text, const char *name, const std::string &value);
// Open a card of this plugin (`card`: its id in the manifest; plugin_id: the plugin's own). `title`: the words in its
// top bar ("" for the tile's name). False when the plugin has no such card.
bool open_card(const char *plugin_id, const char *card, const std::string &entity = "", int tile = -1,
               const std::string &title = "");
// Close the card that is open, as Back does.
void close_card();
// Show a popup of this plugin over the glass (0.18), made by `make` (the core deletes it), in place of the popup shown
// now. A dark screen lights up first, as wake() does: a popup is something to see. Call it from the plugin's own calls
// (the screen's loop). False when nothing could show (`make` returned none).
bool show_popup(const Plugin *plugin, std::function<Popup *()> make, PopupWidth width = PopupWidth::ALERT);
// Close this plugin's popup, if it shows one (it hears no on_dismiss).
void close_popup(const Plugin *plugin);
// Whether a popup of this plugin shows.
bool popup_shown(const Plugin *plugin);
// Where the finger of a tile's on_tap was (0.10), in the pixels of the tile's drawing area (TileContext::parent: 0,0
// its top left, width and height as create() got them), so a tile with a list or a row of posters knows which one was
// tapped; or of a card's on_tap (0.12), in the pixels of its room (CardContext::parent). Valid during on_tap; -1,-1
// when the screen could not say.
struct Point {
  int x = -1, y = -1;
};
Point tap_point();
// Where Tessera's slow circle against burn-in stands this minute (0.14): an offset of at most a millimetre, another every
// minute of the day ({0, 0} without a clock). A screensaver of `moves: true` that moves only some of its parts uses it, as
// a clock over a photo that fills the glass: the photo stays put, the clock walks the circle.
Point drift(uint32_t epoch);
// Ask the app something on this plugin's behalf: a Home Assistant command its manifest names under
// permissions.ha_commands, such as {"ask": "call_service:calendar.get_events", "data": {"entity_id": "calendar.waste",
// "duration": {"days": 28}}}. Returns the number the answer carries as "re" (0 when it could not be sent: no app, or a
// request over 512 bytes). The answer arrives in on_message, also when it failed.
uint32_t send(const Plugin *plugin, JsonObjectConst request);
// The card on the glass draws again in its next pass (after a change made outside on_state or on_tick).
void refresh();
// Wake the screen as Home Assistant's Wake button does (0.16), for a plugin that senses someone come (motion in front of
// a camera, a light coming on): the one way every wake takes that is not a finger on the glass. A dimmed screen lights
// up at its brightness, also at night, its screensaver goes and a Sleep is over; it goes back to page 1 at once when
// that time ran out during standby. A screen that is on only counts its standby time from now. It is no tap: Back to
// page 1 keeps counting from the last touch, so waking on every motion holds no card or page 2 up. The log names the
// plugin. Call it from the plugin's own calls (the screen's loop, as every call here), never from a task of its own,
// and at most once a second or two while what it senses goes on. A plugin that wakes the screen by what it senses has
// a setting for it, off until someone turns it on (docs/PLUGINS.md, "Waking the screen").
void wake(const Plugin *plugin);
// What a plugin captures on the screen itself (0.17): its own camera, watched (CAMERA: someone sees what it sees), or
// for sensing alone (SENSING, 0.20: a light level, motion, and no picture leaves the screen or reaches a person), or
// its microphone, heard (SOUND, 0.23: someone hears what it hears, as a viewer of its video with sound or a call).
enum class Capture : uint8_t { CAMERA, SENSING, SOUND };
// A plugin uses the screen's own camera on the screen itself (0.17, docs/PICTURES.md "Capture"): true while it does,
// false once it stops, for each Capture on its own. The core shows a dot in the glass's top right corner, on top of
// everything, while anything uses the camera, and no plugin or setting can take it away: solid while anyone watches
// (a plugin's CAMERA, or Home Assistant taking pictures or a stream of the camera, `ts_camera`, which the core sees by
// itself), a ring while the camera only senses (SENSING, 0.20). What a plugin does on the screen it must say here.
// SOUND (0.23) changes no dot: the screen squeezes its live tiles to a quarter while someone hears the microphone
// (pressure.h, heard), since a conversation goes before the tiles on the sending side too; on a reTerminal D1001 four
// live tiles beside its own video stalled the uplink and the sound reached its viewer in bursts a second late.
// Call it from the plugin's own calls (the screen's loop).
void capturing(const Plugin *plugin, Capture what, bool on);
// The work a busy screen may squeeze (0.21, docs/PLATFORM_PLAN.md 4.10), in the order it gives up: the screen's own
// camera's picture leaving it (its video), its sensing (a light level, motion), and work in the background (anything
// done ahead for later).
enum class Work : uint8_t { OWN_CAMERA = 4, SENSING = 5, BACKGROUND = 6 };
// How much of it to give up now: 0 none, 1 half (every other frame, sample or item), 2 three quarters. The screen sets
// it from what it measures (the panel running dry, the main loop held up, the wake word falling behind) and while a
// finger is on the glass; it goes back by itself. Any task may ask, at any moment, and nothing waits on it. A plugin
// that gives up frames of a video leaves them out before it encodes them, so its stream stays whole.
uint8_t squeeze(Work work);
// The screen's own camera on a live tile of its own (0.22, docs/PLATFORM_PLAN.md 4.11). A plugin that has the camera's
// frames offers them once, in its setup: the screen's hello then says so, and the app answers a live tile of this
// screen's own camera with no link but this. While such a tile is on the glass, own_tile_wants() is true, and the plugin
// hands each frame to own_frame() on its camera's task, as the camera gave it: the core takes what it needs before it
// returns (a copy of the part it shows, at its pace), never waits, and lets a frame it cannot take go by.
enum class FrameFormat : uint8_t { RGB565, YUV420 };  // YUV420: the P4's packed layout (ISP, encoder), BT.601 limited
struct OwnFrame {
  const uint8_t *data = nullptr;
  uint16_t width = 0, height = 0;
  FrameFormat format = FrameFormat::RGB565;
};
void offer_own_frames();
bool own_tile_wants();
void own_frame(const OwnFrame &frame);
// How far the screen's own camera turns its picture to stand upright (0.19), 0 or 180: half way round when the board
// mounts its sensor upside down against the glass (its CAMERA_ORIENTATION), and half way again while the screen is
// turned half way round from lying down. A quarter turn (a screen stood up) changes nothing; the picture stays lying
// down. Read it now and then from the plugin's own calls (it follows the screen's rotation, which the app changes
// without a build) and turn the sensor's picture by it, so every picture of the camera stands the same way.
int camera_turn();
// Who may play and who may listen (0.19, audio_owner.h; docs/PLATFORM_PLAN.md 3.4). The screen has one loudspeaker and
// one microphone; a plugin that plays more than a short sound, or listens, claims a side first, as an app asks iOS for
// its audio session. The roles, highest first: DOORBELL, VOICE (a wake word, a voice session), CAMERA_SOUND, MEDIA. A
// higher role takes a side from a lower one and the lower hears `lost` (stop at once); when the higher one releases,
// the lower hears `regained` if it gave one (play or listen again), else it is forgotten. A lower role is refused and
// may try again later. Short sounds (tessera::Sound, the tap) and Home Assistant's announcements never claim: they mix.
// `id` tells two claims of one role apart. Call it from the plugin's own calls (the screen's loop), as every call here.
namespace audio {
using Role = audio_owner::Role;
using Side = audio_owner::Side;
inline bool claim(Side side, Role role, uint32_t id, std::function<void()> lost, std::function<void()> regained = {}) {
  audio_owner::Claim c;
  c.role = role;
  c.id = id;
  c.lost = std::move(lost);
  c.regained = std::move(regained);
  return audio_owner::the().claim(side, c);
}
inline void release(Side side, Role role, uint32_t id = 0) { audio_owner::the().release(side, role, id); }
// Whether a claim in `role` would get `side` now: what a plugin asks before it speaks or listens, without claiming.
inline bool open(Side side, Role role) { return audio_owner::the().would_grant(side, role); }
// Who holds a side now (held() says whether anyone does).
inline bool held(Side side) { return audio_owner::the().held(side); }
inline Role holder(Side side) { return audio_owner::the().holder(side); }
}  // namespace audio
// A Home Assistant action on an entity, as a tile's tap sends it: action("light.toggle", entity), or with fields of any
// JSON type, a JSON object of up to 16 fields, together at most 1 KB:
//   JsonDocument d;
//   d["media_id"] = title; d["media_type"] = "album"; d["artist"] = artist;
//   tessera::action("music_assistant.play_media", player, d);
// The screen must be allowed to perform actions. The plugin's manifest names every action it calls under
// permissions.home_assistant_actions so that a person can read what it does before adding it; the screen does not check
// that list (code built into the firmware can do what the firmware can), the manifest is the plugin's own word.
// A text arrives as the text ("1989" stays a text), a number as a number, true and false as themselves, a list or an
// object whole, and nothing in it is ever run as a template. `entity` is the action's entity_id, whose tiles wait for
// the answer as for a tap; "" when the fields name their own target (an "entity_id" list of several speakers, an
// area_id) or the action has none. False when it was not sent: no object, a field name that is not a-z, 0-9 and _,
// entity_id given twice, too many or too much (the log says which).
bool action(const char *service, const std::string &entity, JsonVariantConst fields = JsonVariantConst());
// A value a finger changed (0.14, docs/OPTIMISTIC.md): it shows at once on every tile and card of the entity and on the
// screensaver (a saver's on_state gets it), the action goes out at once (taps while it is on its way fold into one), and
// Home Assistant's reports, answers and silence square it: a refusal or no answer puts the old value back. Use it for
// every control that changes what an entity shows (play and pause, mute, on and off), never a value of your own that you
// write before the action. wish(entity, Wish::PLAYING, "0") pauses a player. False when it was not sent (no such field
// for that domain, or the screen may not perform actions now). A step (volume up and down) has nothing to show and goes
// as an action().
bool wish(const std::string &entity, Wish field, const std::string &value);

namespace ui {
// Sizes: a physical size in millimetres of glass, or a size of the reference look in this board's pixels.
inline int mm(int millimetres) { return ::ui::mm(millimetres); }
inline int px(int pixels) { return ::ui::px(pixels); }
// The large look (4 inches and up) or the compact one (the CYD).
inline bool large() { return ::ui::large(); }
inline lv_color_t color(theme::Role role) { return theme::color(role); }
const lv_font_t *font(Font font);
inline int line_height(Font f) { const lv_font_t *face = font(f); return face ? lv_font_get_line_height(face) : 0; }
int text_width(const std::string &text, Font font);
// True when the font has a glyph for every character of `text` (0.9): a character it lacks draws as nothing.
bool covers(const std::string &text, Font font);
// A label in `parent`, in this font and colour, one line, cut with dots when it is too long for the width it gets. It is
// one line of its font high (0.9; before, LVGL's own height let a long text wrap onto a second line), and set_font keeps
// it so; a label given a height of its own keeps that.
lv_obj_t *label(lv_obj_t *parent, Font font, theme::Role role = theme::INK);
// Set what a label shows, its font or its colour only when that differs (a repaint that finds nothing new is free).
void set_text(lv_obj_t *label, const std::string &text);
void set_font(lv_obj_t *label, Font font);
void set_color(lv_obj_t *label, theme::Role role);
// A label in a tone (0.8), the colours a top bar item's icon takes; NORMAL takes `normal`.
void set_tone(lv_obj_t *label, Tone tone, theme::Role normal);
// A block's fill in a tone (0.9): a bar, a dot or a badge in the colour of what it means, in both looks; NORMAL takes
// `normal`. Changed only when it differs, as set_color.
void set_fill(lv_obj_t *block, Tone tone, theme::Role normal);
// The colour of a tone in this look (0.9), for a part ui::set_tone and set_fill do not reach (a line of a chart).
lv_color_t tone_color(Tone tone, theme::Role normal);
// A rounded block (a line number's badge, a bar): no border, the radius of a key.
lv_obj_t *block(lv_obj_t *parent, theme::Role fill);
// The UTF-8 of an icon of Tessera's set by its codepoint (0xF0B5E), for a label in Font::ICON or ICON_SMALL.
std::string icon(uint32_t codepoint);
// A part of a screensaver a finger may tap without waking the screen (0.14): its taps go to Saver::on_tap (and a hold to
// on_hold), through the touch guard every key passes; a press gives the plugins their on_press. Every other part of a
// saver lets the finger through to the glass, which wakes. A saver of the manifest's `taps: true` only; call it in show().
void takes_taps(lv_obj_t *part);
// A label of several lines (0.10): wraps at its width and is cut with dots at its height, both the plugin's to set
// (lv_obj_set_size); for a description, a sentence, a title that may take two lines. ui::set_text and the rest apply.
lv_obj_t *text(lv_obj_t *parent, Font font, theme::Role role = theme::INK);

// ---- Pictures on a tile (0.10) and on a card (0.13) ----
// A tile lays out places for pictures and names an address for each; the core does the rest, the way every picture
// of the screen comes: the card asks the app for all its places as one picture (an atlas of their frames, one
// download, one entry in the picture store), the app fetches each address once, cuts or fits it to its place, and the
// card draws each place its frame. Pictures come only while the tile is on the glass or on a kept page, and leave the
// store when the tile does. An address is on a host the plugin's manifest names under permissions.network, or a
// picture of Home Assistant's own for a tile of an entity (its entity_picture: /api/image/serve/..., /api/image_proxy/...,
// /local/...), or (0.17) one of the core's own sources for a place of that entity: `cover:<entity>` what a media player
// plays (through Home Assistant's own proxy for it, as the media card's cover), `camera:<entity>` a camera's or image
// entity's still, `entity:<entity>` an entity's own picture (a person's); and `step:` the screensaver step's own picture
// (docs/PICTURES.md "Sources"). The app fetches nothing else. The manifest's `pictures` of the tile says how many places
// it has at most.
// A card (0.13) does the same in its room (CardContext::parent): its places, made in open(), come as one picture while it
// is open, the way Tessera's own media card shows its cover, and leave the store when it closes. The manifest's
// `pictures` of the card says how many it has; Home Assistant's own pictures only for a card opened for an entity. The
// same address as on a tile (the cover the tile shows) is a picture the app has already: it only paints it larger.
// Whether this screen shows pictures at all: a board without the memory for them (the CYD, the Waveshare 3.5-inch,
// the Hosyond 4-inch) shows none, and a tile lays itself out without the places, as it does without a picture.
bool pictures();
// A place for a picture in `parent`, sized and placed by the plugin as any object (lv_obj_set_size, lv_obj_set_pos):
// a soft block (theme::TRACK) until its picture is there. Its corners are a key's; a radius of the plugin's own
// (lv_obj_set_style_radius) is taken over by the picture. Call it in create() of a tile or open() of a card, as every
// object. The place is the core's: size and place it, never style it (0.17: Placeholder::NONE for a place without its
// block, which stays so whatever comes of its picture).
lv_obj_t *picture(lv_obj_t *parent, Placeholder placeholder = Placeholder::BLOCK);
// The picture a place shows, by its address, COVER or CONTAIN (Fit). The same address again does nothing (call it on
// every on_state for free); another address asks the app again; "" takes the picture away and shows the block. A
// place that lies outside the card, or has no size, gets no picture.
// Turned in perspective (Turn) and with a reflection fading out under it (`mirror`: the place's lower part,
// MIRROR_PERCENT of the picture's height, holds it). Places may overlap: they are layers, a place made later lies over
// one made earlier, and the app paints them so (a cover flow, a stack of photos). An older app draws them flat.
void set_picture(lv_obj_t *place, const std::string &url, Fit fit = Fit::COVER, Turn turn = Turn::NONE, bool mirror = false);
// Slide every place of the tile `dx` pixels sideways over `ms` (0.10), and keep them there until the tile's next
// picture is here: then they are back where the tile laid them out, with it, in the same frame. Call it beside the
// set_picture calls of a change (a cover flow that turns), so the change shows which way it goes while the next picture
// comes. Call it in any call of the tile or the card (on_state, on_tap, on_tick).
void slide_pictures(int dx, uint32_t ms = 300);
// The part moves once every `period_ms`, again and again, starting `delay_ms` from now (three dots that pulse one after
// the other, two ripples half a period apart), until ui::still or until the part is deleted. For a popup, whose moment
// is short (a microphone that listens, a ring that turns while it thinks); a tile, a card and a screensaver stand
// still, since the screen draws the part again in every frame while it moves. Keep a part that moves small: it is drawn
// anew each frame, and a part that spins or ripples through a layer of its own.
void animate(lv_obj_t *part, Motion motion, uint32_t period_ms, uint32_t delay_ms = 0);
// The part stops moving and shows as it was laid out: whole, upright, at its size.
void still(lv_obj_t *part);
// A tile's place shows its camera live (0.17): a place whose address is `camera:<entity>` of the tile's own entity
// streams on a screen that streams (the ESP32-P4 boards) while it is on the glass, the page stands still and nothing
// lies over it, exactly as a camera tile set to Live does (docs/PICTURES.md); everywhere else, and until its first live
// picture, it shows its stills. Lay nothing over a live place (a label, another place): LVGL's drawing there stops the
// stream. Only on a tile's places; a card's and a saver's places show stills. Call it in create() or on_state.
void live(lv_obj_t *place, bool on = true);
}  // namespace ui

}  // namespace tessera
