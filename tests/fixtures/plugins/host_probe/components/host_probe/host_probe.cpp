#include "esphome/components/smart_display/plugin_host.h"
#include "host_probe.h"
#include "esphome/core/log.h"
#include <algorithm>
#include <string>

namespace esphome::host_probe {

static const char *const TAG = "probe";
using tessera::Font;
namespace ui = tessera::ui;

// The tile: its word in a badge, the number the data carries large under it. Every moment is one log line with the
// tile's index, so the harness follows each card of the layout on its own.
class ProbeTile : public tessera::Tile {
 public:
  explicit ProbeTile(HostProbe *plugin) : plugin_(plugin) {}
  ~ProbeTile() override {
    if (tile_ == 0 && plugin_->tile0_mark_ == mark_) plugin_->tile0_mark_ = nullptr;
    ESP_LOGI(TAG, "tile=%d destroy", tile_);
  }

  void create(const tessera::TileContext &c) override {
    tile_ = c.tile;
    room_ = c.parent;
    word_ = c.options["word"] | "";   // copied: the context is gone after this call
    ESP_LOGI(TAG, "tile=%d create %dx%d cells=%ux%u name=[%s] word=[%s] entity=[%s]", tile_, c.width, c.height,
             (unsigned) c.columns, (unsigned) c.rows, c.name, word_.c_str(), c.entity);
    // The list options (0.12): an array of texts, and an array of picks with the words the person saw.
    std::string words, picks;
    for (JsonVariantConst w : c.options["words"].as<JsonArrayConst>()) words += std::string(words.empty() ? "" : ",") + (w | "");
    for (JsonVariantConst p : c.options["picks"].as<JsonArrayConst>())
      picks += std::string(picks.empty() ? "" : ",") + (p["value"] | "") + ":" + (p["label"] | "");
    ESP_LOGI(TAG, "tile=%d lists words=[%s] picks=[%s]", tile_, words.c_str(), picks.c_str());
    // The moments of boot, which came before anyone listened to the log, and how often before_update was heard.
    ESP_LOGI(TAG, "status ready=%d settings=%u interval=%d updates=%d early=%d", (int) plugin_->ready_, plugin_->rows_,
             (int) plugin_->interval_, (int) plugin_->updates_, plugin_->early_);
    badge_ = ui::block(c.parent, theme::ACCENT);
    lv_obj_set_size(badge_, std::max(1, c.width / 2), ui::line_height(Font::TITLE) + ui::px(4));
    lv_obj_set_pos(badge_, 0, 0);
    label_ = ui::label(badge_, Font::TITLE, theme::ON_ACCENT);
    ui::set_text(label_, word_);
    lv_obj_center(label_);
    // The part the plugin paints from its own moments (on_interval): hidden, so no picture of the probe changes.
    if (tile_ == 0) {
      mark_ = ui::label(c.parent, Font::TITLE, theme::INK);
      lv_obj_add_flag(mark_, LV_OBJ_FLAG_HIDDEN);
      plugin_->tile0_mark_ = mark_;
      plugin_->tile0_ink_ = 0;
    }
    // The large digits (0.9): taller than VALUE, with the digits of a value and without the letters of a word.
    ESP_LOGI(TAG, "tile=%d fonts digits=%d value=%d covers=%d,%d", tile_, ui::line_height(Font::DIGITS),
             ui::line_height(Font::VALUE), (int) ui::covers("-21,5°", Font::DIGITS), (int) ui::covers("open", Font::DIGITS));
    // The tones for a block (0.9): the badge in GOOD's green, and the four tones' colours, each its own.
    ui::set_fill(badge_, tessera::Tone::GOOD, theme::ACCENT);
    ESP_LOGI(TAG, "tile=%d tones good=%06X busy=%06X alert=%06X normal=%06X fill=%06X", tile_,
             (unsigned) lv_color_to_u32(ui::tone_color(tessera::Tone::GOOD, theme::INK)) & 0xFFFFFF,
             (unsigned) lv_color_to_u32(ui::tone_color(tessera::Tone::BUSY, theme::INK)) & 0xFFFFFF,
             (unsigned) lv_color_to_u32(ui::tone_color(tessera::Tone::ALERT, theme::INK)) & 0xFFFFFF,
             (unsigned) lv_color_to_u32(ui::tone_color(tessera::Tone::NORMAL, theme::INK)) & 0xFFFFFF,
             (unsigned) lv_color_to_u32(lv_obj_get_style_bg_color(badge_, LV_PART_MAIN)) & 0xFFFFFF);
    number_ = ui::label(c.parent, Font::DIGITS, theme::INK);
    // One line of its font high (0.9), and so after set_font too.
    ESP_LOGI(TAG, "tile=%d label height=%d line=%d", tile_, (int) lv_obj_get_style_height(number_, LV_PART_MAIN),
             ui::line_height(Font::DIGITS));
    lv_obj_set_width(number_, c.width);
    lv_obj_set_pos(number_, 0, lv_obj_get_height(badge_) + ui::px(4));
    // Two places for pictures (0.10) at the card's foot, a poster's proportions, and a label of several lines beside
    // them: the harness sends an address in the data and answers the card's question with an atlas of both.
    const bool pictures = ui::pictures();
    ESP_LOGI(TAG, "tile=%d pictures=%d", tile_, (int) pictures);
    if (pictures) {
      const int h = std::max(ui::px(24), c.height / 3), w = h * 2 / 3;
      for (int i = 0; i < 2; ++i) {
        places_[i] = ui::picture(c.parent);
        lv_obj_set_size(places_[i], w, h);
        lv_obj_set_pos(places_[i], i * (w + ui::px(4)), c.height - h);
      }
      words_ = ui::text(c.parent, Font::BODY, theme::MUTED);
      lv_obj_set_pos(words_, 2 * (w + ui::px(4)), c.height - h);
      lv_obj_set_width(words_, std::max(1, c.width - 2 * (w + ui::px(4))));
      ui::set_text(words_, "A label of several lines that wraps and ends in dots");
    }
    plugin_->ask_once();
  }
  void on_state(JsonObjectConst data) override {
    n_ = data["n"] | -1;
    // The pictures (0.10): the first place takes the address as it is, the second the same picture whole (contain);
    // without an address the places show their blocks.
    const std::string picture = data["picture"] | "";
    if (places_[0]) ui::set_picture(places_[0], picture);
    if (places_[1]) ui::set_picture(places_[1], picture, tessera::Fit::CONTAIN);
    if (!picture.empty()) ESP_LOGI(TAG, "tile=%d picture set %s", tile_, picture.c_str());
    // Where the first place lies on the glass, so the render can look at its pixels.
    if (places_[0] && !picture.empty()) {
      lv_obj_update_layout(places_[0]);
      lv_area_t a;
      lv_obj_get_coords(places_[0], &a);
      ESP_LOGI(TAG, "tile=%d place0 %d,%d,%d,%d", tile_, (int) a.x1, (int) a.y1, (int) a.x2, (int) a.y2);
    }
    // The card's own colour (0.26): the data names one, and "none" gives the card back. What the card wears after
    // the pass that follows is in the tick's line.
    const std::string card = data["card"] | "";
    if (!card.empty()) {
      const tessera::CardColor colour = card == "green" ? tessera::CardColor::GREEN : card == "red" ? tessera::CardColor::RED
                                      : card == "instrument" ? tessera::CardColor::INSTRUMENT : tessera::CardColor::NONE;
      ui::set_card_color(colour);
      ESP_LOGI(TAG, "tile=%d card set %s own=%06X named=%06X", tile_, card.c_str(),
               (unsigned) (lv_color_to_u32(ui::card_color()) & 0xFFFFFF), (unsigned) (lv_color_to_u32(ui::card_color(colour)) & 0xFFFFFF));
    }
    // A tile of an entity gets its lists whole when they fit (0.5): how many prices of each day arrived.
    JsonObjectConst attributes = data["attributes"];
    ESP_LOGI(TAG, "tile=%d state n=%d wait=[%s] today=%u tomorrow=%u", tile_, n_, data["wait"] | "",
             (unsigned) attributes["today"].size(), (unsigned) attributes["tomorrow"].size());
  }
  void on_tick(uint32_t epoch) override {
    ESP_LOGI(TAG, "tile=%d tick epoch=%u n=%d ground=%06X", tile_, (unsigned) epoch, n_,
             (unsigned) (lv_color_to_u32(lv_obj_get_style_bg_color(lv_obj_get_parent(room_), LV_PART_MAIN)) & 0xFFFFFF));
    const std::string number = std::to_string(n_);
    ui::set_font(number_, ui::covers(number, Font::DIGITS) ? Font::DIGITS : Font::VALUE);
    ui::set_text(number_, number);
  }
  void on_theme() override {
    ESP_LOGI(TAG, "tile=%d theme dark=%d", tile_, (int) theme::dark);
    ui::set_fill(badge_, tessera::Tone::GOOD, theme::ACCENT);
    ui::set_color(label_, theme::ON_ACCENT);
    ui::set_color(number_, theme::INK);
  }
  void on_tap() override {
    // Where the finger was (0.10), in the tile's own pixels.
    const tessera::Point at = tessera::tap_point();
    ESP_LOGI(TAG, "tile=%d tap at=%d,%d", tile_, at.x, at.y);
    // An action of several fields of any JSON type (0.12): texts as they are, also one that looks like a number or a
    // template, and a number, a toggle, a list and an object that Home Assistant reads back into their types.
    JsonDocument d;
    d["media_id"] = "1989";
    d["media_type"] = "album";
    d["artist"] = "{{ states('lock.door') }}";
    d["volume"] = 0.4;
    d["radio_mode"] = false;
    JsonArray ids = d["ids"].to<JsonArray>();
    ids.add("a");
    ids.add("{% b %}");
    d["extra"]["none"] = nullptr;
    const bool sent = tessera::action("music_assistant.play_media", "media_player.probe", d);
    // What does not fit is not sent: entity_id twice.
    JsonDocument twice;
    twice["entity_id"] = "media_player.other";
    const bool refused = !tessera::action("music_assistant.play_media", "media_player.probe", twice);
    ESP_LOGI(TAG, "tile=%d action sent=%d refused=%d", tile_, (int) sent, (int) refused);
    tessera::open_card(plugin_->plugin_id(), "detail", "", tile_, "Probe card");
  }

 private:
  HostProbe *plugin_;
  int tile_ = -1, n_ = -1;
  std::string word_;
  lv_obj_t *room_{}, *badge_{}, *label_{}, *number_{}, *words_{}, *mark_{};
  lv_obj_t *places_[2]{};
};

class ProbeCard : public tessera::Card {
 public:
  ~ProbeCard() override { ESP_LOGI(TAG, "card destroy"); }
  void open(const tessera::CardContext &c) override {
    ESP_LOGI(TAG, "card open %dx%d tile=%d entity=[%s]", c.width, c.height, c.tile, c.entity);
    words_ = ui::label(c.parent, Font::BODY_LARGE, theme::INK);
    lv_obj_set_width(words_, c.width);
    ui::set_text(words_, "Probe card");
    // A word at the foot of the card's room: the render shows the whole room reaches the glass (GitHub #226).
    foot_ = ui::label(c.parent, Font::BODY_LARGE, theme::INK);
    ui::set_text(foot_, "Foot");
    lv_obj_align(foot_, LV_ALIGN_BOTTOM_MID, 0, 0);
    // A place for a picture on the card (0.13), a square of a third of the room at its top right, with an address of
    // its own; a board without pictures lays out without it.
    const bool pictures = ui::pictures();
    ESP_LOGI(TAG, "card pictures=%d", (int) pictures);
    if (pictures) {
      const int side = std::max(ui::px(24), std::min(c.width, c.height) / 3);
      cover_ = ui::picture(c.parent);
      lv_obj_set_size(cover_, side, side);
      lv_obj_set_pos(cover_, c.width - side, 0);
      ui::set_picture(cover_, "https://image.tmdb.org/t/p/w342/probe-card.jpg");
    }
    // Where the card's room lies on the glass, so the harness taps it (0.12), and where its place is (0.13).
    lv_obj_update_layout(c.parent);
    lv_area_t a;
    lv_obj_get_coords(c.parent, &a);
    ESP_LOGI(TAG, "card room %d,%d,%d,%d", (int) a.x1, (int) a.y1, (int) a.x2, (int) a.y2);
    if (cover_) {
      lv_obj_get_coords(cover_, &a);
      ESP_LOGI(TAG, "card place %d,%d,%d,%d", (int) a.x1, (int) a.y1, (int) a.x2, (int) a.y2);
    }
  }
  // A tap on the card's room (0.12), where in its own pixels.
  void on_tap() override {
    const tessera::Point at = tessera::tap_point();
    ESP_LOGI(TAG, "card tap at=%d,%d", at.x, at.y);
  }
  void on_state(JsonObjectConst data) override { ESP_LOGI(TAG, "card state n=%d", data["n"] | -1); }
  void on_tick(uint32_t epoch) override { ESP_LOGI(TAG, "card tick epoch=%u", (unsigned) epoch); }
  void on_theme() override { ESP_LOGI(TAG, "card theme dark=%d", (int) theme::dark); }
  bool on_back() override { ESP_LOGI(TAG, "card back"); return false; }

 private:
  lv_obj_t *words_{}, *foot_{}, *cover_{};
};

// A card that closes itself, or opens another card in its place, from inside one of its own calls, as the harness's
// message says (on_message, "do"). The host must not touch it again once it closed, and must not delete it before the
// call returns: "closer gone" (its destructor) comes after the call's own "end" line, and nothing of it after that.
class ProbeCloser : public tessera::Card {
 public:
  static std::string mode;  // what the next closer does: close_in_open, close_in_state, close_in_tick,
                            // close_on_change, close_in_theme or back_opens
  ProbeCloser() : mode_(mode) {}
  ~ProbeCloser() override {
    ESP_LOGI(TAG, "closer gone mode=%s", mode_.c_str());
    alive_ = 0;
  }
  void open(const tessera::CardContext &c) override {
    parent_ = c.parent;
    ESP_LOGI(TAG, "closer open mode=%s from=%d", mode_.c_str(), c.tile);
    if (mode_ == "close_in_open") tessera::close_card();
    ESP_LOGI(TAG, "closer open end alive=%d", (int) (alive_ == ALIVE));
  }
  void on_state(JsonObjectConst data) override {
    const int n = data["n"] | -1;
    ESP_LOGI(TAG, "closer state n=%d", n);
    // close_on_change: the data the card opened with is kept; new data of its tile, which tick_card hands over, closes it.
    if (mode_ == "close_in_state" || (mode_ == "close_on_change" && first_n_ != -2 && n != first_n_)) tessera::close_card();
    if (first_n_ == -2) first_n_ = n;
    ESP_LOGI(TAG, "closer state end alive=%d", (int) (alive_ == ALIVE));
  }
  void on_tick(uint32_t epoch) override {
    ESP_LOGI(TAG, "closer tick");
    if (mode_ == "back_opens" && !back_said_) {
      // Where the core put the back key of this card (the first child of the card's root), for the harness's finger.
      back_said_ = true;
      lv_obj_t *root = lv_obj_get_parent(parent_);
      lv_obj_update_layout(root);
      lv_area_t a;
      lv_obj_get_coords(lv_obj_get_child(root, 0), &a);
      ESP_LOGI(TAG, "closer back_key x=%d y=%d", (int) ((a.x1 + a.x2) / 2), (int) ((a.y1 + a.y2) / 2));
    }
    if (mode_ == "close_in_tick") tessera::close_card();
    ESP_LOGI(TAG, "closer tick end alive=%d", (int) (alive_ == ALIVE));
  }
  void on_theme() override {
    ESP_LOGI(TAG, "closer theme dark=%d", (int) theme::dark);
    if (mode_ == "close_in_theme") tessera::close_card();
    ESP_LOGI(TAG, "closer theme end alive=%d", (int) (alive_ == ALIVE));
  }
  bool on_back() override {
    ESP_LOGI(TAG, "closer back");
    // Another card in this one's place, then false: the host must close neither the new card nor this one twice.
    if (mode_ == "back_opens") tessera::open_card("host_probe", "detail", "back", -1, "Probe card");
    ESP_LOGI(TAG, "closer back end alive=%d", (int) (alive_ == ALIVE));
    return false;
  }

 private:
  static constexpr uint32_t ALIVE = 0xC105E;
  uint32_t alive_ = ALIVE;
  std::string mode_;
  lv_obj_t *parent_{};
  int first_n_ = -2;
  bool back_said_ = false;
};
std::string ProbeCloser::mode;

// A screensaver (plugin API 0.14): every moment one line with its id, so the harness follows a face of the music, a face
// of the clock and a step of its own. The deck lays out a place for the step's cover and one key that takes taps.
class ProbeSaver : public tessera::Saver {
 public:
  explicit ProbeSaver(const char *id) : id_(id) {}
  ~ProbeSaver() override { ESP_LOGI(TAG, "saver=%s destroy", id_); }
  void show(const tessera::SaverContext &c) override {
    ESP_LOGI(TAG, "saver=%s show %dx%d step=%d level=%u night=%d dark=%d", id_, c.width, c.height, (int) c.step,
             (unsigned) c.level, (int) c.night, (int) theme::dark);
    words_ = ui::label(c.parent, Font::HEADLINE, theme::INK);
    lv_obj_set_width(words_, c.width / 2);
    lv_obj_set_pos(words_, ui::px(16), ui::px(16));
    if (c.step == tessera::SaverStep::MEDIA) {
      if (ui::pictures()) {
        const int side = std::min(c.width, c.height) / 2;
        cover_ = ui::picture(c.parent);
        lv_obj_set_size(cover_, side, side);
        lv_obj_set_pos(cover_, c.width - side - ui::px(16), ui::px(16));
      }
      key_ = ui::block(c.parent, theme::ACCENT);
      lv_obj_set_size(key_, ui::px(64), ui::px(64));
      lv_obj_set_pos(key_, ui::px(16), c.height - ui::px(80));
      ui::takes_taps(key_);
      lv_obj_update_layout(c.parent);
      lv_area_t a;
      lv_obj_get_coords(key_, &a);
      ESP_LOGI(TAG, "saver=%s key %d,%d,%d,%d", id_, (int) a.x1, (int) a.y1, (int) a.x2, (int) a.y2);
    }
  }
  void on_state(JsonObjectConst data) override {
    entity_ = data["entity"] | "";
    playing_ = std::string(data["state"] | "") == "playing";
    std::string all;
    serializeJson(data, all);
    ESP_LOGI(TAG, "saver=%s state %.200s", id_, all.c_str());
    ui::set_text(words_, std::string(data["title"] | (data["temperature"] | (data["album"] | (data["name"] | "")))));
    if (cover_) ui::set_picture(cover_, data["picture"] | "");
  }
  void on_tick(uint32_t epoch) override {
    if (ticked_) return;
    ticked_ = true;
    ESP_LOGI(TAG, "saver=%s tick epoch=%u", id_, (unsigned) epoch);
  }
  void on_tap() override {
    const tessera::Point at = tessera::tap_point();
    const bool sent = !entity_.empty() && tessera::wish(entity_, tessera::Wish::PLAYING, playing_ ? "0" : "1");
    ESP_LOGI(TAG, "saver=%s tap at=%d,%d wish=%d", id_, at.x, at.y, (int) sent);
  }
  void on_hold() override { ESP_LOGI(TAG, "saver=%s hold", id_); }

 private:
  const char *id_;
  std::string entity_;
  bool playing_ = false, ticked_ = false;
  lv_obj_t *words_{}, *cover_{}, *key_{};
};

void HostProbe::setup() {
  set_up_ = true;
  add_tile("probe", [this]() { return new ProbeTile(this); });
  add_card("detail", []() { return new ProbeCard(); });
  add_card("closer", []() { return new ProbeCloser(); });
  add_saver("deck", tessera::SaverStep::MEDIA, []() { return new ProbeSaver("deck"); });
  add_saver("dial", tessera::SaverStep::CLOCK, []() { return new ProbeSaver("dial"); });
  add_saver("alarm", tessera::SaverStep::OWN, []() { return new ProbeSaver("alarm"); });
  add_saver("frame", tessera::SaverStep::PHOTOS, []() { return new ProbeSaver("frame"); });
  add_tap_action("open", [this](const tessera::TapContext &c) {
    ESP_LOGI(TAG, "tap_action entity=[%s] name=[%s] tile=%d", c.entity, c.name, c.tile);
    tessera::open_card(plugin_id(), "detail", c.entity, c.tile);
  });
  add_bar_item("mark", [this]() {
    if (!bar_said_) { bar_said_ = true; ESP_LOGI(TAG, "bar read"); }
    tessera::BarItem item;
    item.shown = true;
    item.icon = 0xF0A66;
    item.text = text("hello");
    return item;
  });
}

void HostProbe::on_ready() {
  ready_ = true;
  if (!set_up_) ++early_;
  ESP_LOGI(TAG, "ready id=%s version=%s setup=%d", plugin_id(), plugin_version(), (int) set_up_);
}
void HostProbe::on_interval(uint32_t now_ms) {
  interval_ = true;
  if (!set_up_) ++early_;
  // A role painted onto a tile's part from the plugin's own moment: said whenever the colour it got changes.
  if (tile0_mark_) {
    ui::set_color(tile0_mark_, theme::INK);
    const uint32_t ink = lv_color_to_u32(lv_obj_get_style_text_color(tile0_mark_, LV_PART_MAIN)) & 0xFFFFFF;
    if (ink != tile0_ink_) {
      tile0_ink_ = ink;
      ESP_LOGI(TAG, "interval painted tile=0 ink=%06X", (unsigned) ink);
    }
  }
  if (interval_said_) return;
  interval_said_ = true;
  ESP_LOGI(TAG, "interval first=%u", (unsigned) now_ms);
}
void HostProbe::on_standby(bool dark) { ESP_LOGI(TAG, "standby dark=%d", (int) dark); }
void HostProbe::before_update() {
  ++updates_;
  ESP_LOGI(TAG, "before_update");
}
void HostProbe::on_cards_closed() { ESP_LOGI(TAG, "cards_closed"); }
void HostProbe::on_alert() { ESP_LOGI(TAG, "alert"); }
void HostProbe::on_press() { ESP_LOGI(TAG, "press"); }
void HostProbe::on_step(const tessera::Step &step) { ESP_LOGI(TAG, "step %d%s", step.direction, step.edge ? " edge" : ""); }

bool HostProbe::settings(tessera::SettingsPage &page) {
  if (!set_up_) ++early_;
  rows_ = 5;
  page.toggle("Probe toggle", [this]() { return toggle_; }, [this](bool on) { toggle_ = on; });
  page.number("Probe number", 0, 10, 1, "", [this]() { return number_; }, [this](int v) { number_ = v; });
  page.info("Probe info", [this]() { return std::string(plugin_version()); });
  page.action("Probe action", "\U000F0A66", []() { ESP_LOGI(TAG, "action run"); });
  page.card("Probe card", "\U000F0A66", "detail");
  ESP_LOGI(TAG, "settings rows=%u", (unsigned) page.items.size());
  return true;
}

void HostProbe::ask_once() {
  if (asked_) return;
  asked_ = true;
  JsonDocument doc;
  doc["ask"] = "call_service:calendar.get_events";
  doc["data"]["entity_id"] = "calendar.test";
  const uint32_t re = tessera::send(this, doc.as<JsonObjectConst>());
  ESP_LOGI(TAG, "sent re=%u", (unsigned) re);
}

// The popup (0.18): a status line and a label of several lines in its room, each moment a log line. `closes` asks it to
// close itself in its own on_tap, so the harness sees the host delete it only after that call returned.
class ProbePopup : public tessera::Popup {
 public:
  explicit ProbePopup(bool closes, bool place = false) : closes_(closes), place_(place) {}
  ~ProbePopup() override { ESP_LOGI(TAG, "popup destroy"); }
  void open(const tessera::PopupContext &c) override {
    // Where the room lies on the glass, for the harness's taps on the card and beside it.
    lv_obj_update_layout(c.parent);
    lv_area_t room;
    lv_obj_get_coords(c.parent, &room);
    ESP_LOGI(TAG, "popup open %dx%d at=%d,%d", c.width, c.height, (int) room.x1, (int) room.y1);
    title_ = ui::label(c.parent, Font::TITLE, theme::INK);
    ui::set_text(title_, "Listening");
    ui::animate(title_, tessera::Motion::PULSE, 1200);   // a part that moves while it shows (0.18)
    words_ = ui::text(c.parent, Font::BODY, theme::INK_SOFT);
    lv_obj_set_pos(words_, 0, ui::line_height(Font::TITLE) + ui::px(8));
    lv_obj_set_width(words_, c.width);
    ui::set_text(words_, "A popup of a plugin, the card an alert shows, over everything but an alert");
    // A popup without an id of the manifest's `popups` may make a place, but it has no pictures: nothing is asked.
    if (place_ && ui::pictures()) {
      lv_obj_t *place = ui::picture(c.parent);
      lv_obj_set_size(place, c.width, ui::px(60));
      lv_obj_set_pos(place, 0, ui::px(120));
      ui::set_picture(place, "https://image.tmdb.org/t/p/w342/probe-no-id.jpg");
      ESP_LOGI(TAG, "popup place without an id");
    }
  }
  void on_interval(uint32_t now_ms) override {
    if (said_interval_) return;
    said_interval_ = true;
    ESP_LOGI(TAG, "popup interval");
  }
  void on_tick(uint32_t) override {
    if (said_tick_) return;
    said_tick_ = true;
    ESP_LOGI(TAG, "popup tick");
  }
  void on_theme() override { ESP_LOGI(TAG, "popup theme"); }
  void on_tap() override {
    const auto at = tessera::tap_point();
    ESP_LOGI(TAG, "popup tap at=%d,%d", at.x, at.y);
    if (closes_) {
      tessera::close_popup(plugin);
      ESP_LOGI(TAG, "popup tap end");
    }
  }
  void on_dismiss() override { ESP_LOGI(TAG, "popup dismiss"); }
  static HostProbe *plugin;

 private:
  bool closes_, place_, said_interval_ = false, said_tick_ = false;
  lv_obj_t *title_{}, *words_{};
};
HostProbe *ProbePopup::plugin = nullptr;

// A popup with an id of the manifest's `popups` (plugin API 0.27): a place for a picture, which the harness answers as
// the app does, and on an instrument's ground (the roles that stay dark in both looks) a mark turned along a course.
class ProbePicturePopup : public tessera::Popup {
 public:
  explicit ProbePicturePopup(bool closes = false) : closes_(closes) {}
  ~ProbePicturePopup() override { ESP_LOGI(TAG, "picture popup destroy"); }
  void open(const tessera::PopupContext &c) override {
    face_ = ui::block(c.parent, theme::INSTRUMENT);
    lv_obj_set_size(face_, c.width, ui::px(60));
    mark_ = ui::label(face_, Font::ICON, theme::INSTRUMENT_GLOW);
    ui::set_text(mark_, ui::icon(0xF001D));   // airplane
    lv_obj_set_pos(mark_, ui::px(8), ui::px(4));
    ui::rotate(mark_, 90);
    ui::rotate(mark_, 450);                   // the same course again: nothing changes
    const int turned = (int) lv_obj_get_style_transform_rotation(mark_, LV_PART_MAIN);
    // Its turn holds through a pulse and ui::still (a plane's icon that blinks keeps its course).
    ui::animate(mark_, tessera::Motion::PULSE, 800);
    const int pulsed = (int) lv_obj_get_style_transform_rotation(mark_, LV_PART_MAIN);
    ui::still(mark_);
    const int stilled = (int) lv_obj_get_style_transform_rotation(mark_, LV_PART_MAIN);
    ESP_LOGI(TAG, "instrument ground=%06X ink=%06X turned=%d pulsed=%d stilled=%d",
             (unsigned) (lv_color_to_u32(ui::color(theme::INSTRUMENT)) & 0xFFFFFF),
             (unsigned) (lv_color_to_u32(ui::color(theme::INSTRUMENT_INK)) & 0xFFFFFF), turned, pulsed, stilled);
    if (!ui::pictures()) {
      ESP_LOGI(TAG, "picture popup open pictures=0");
      return;
    }
    place_ = ui::picture(c.parent);
    lv_obj_set_size(place_, c.width, ui::px(120));
    lv_obj_set_pos(place_, 0, ui::px(70));
    ui::set_picture(place_, "https://image.tmdb.org/t/p/w342/probe-popup.jpg");
    if (closes_) {  // a second place: a popup that closed on the first must not hear of it
      second_ = ui::picture(c.parent);
      lv_obj_set_size(second_, c.width / 2, ui::px(40));
      lv_obj_set_pos(second_, 0, ui::px(200));
      ui::set_picture(second_, "https://image.tmdb.org/t/p/w342/probe-popup-2.jpg");
    }
    ESP_LOGI(TAG, "picture popup open pictures=1");
  }
  void on_picture(lv_obj_t *place, tessera::PictureState state) override {
    ESP_LOGI(TAG, "picture popup heard place=%d state=%d", place == place_ ? 1 : place == second_ ? 2 : 0, (int) state);
    if (closes_) {
      ESP_LOGI(TAG, "picture popup closes in on_picture");
      tessera::close_popup(ProbePopup::plugin);
      return;
    }
    if (place != place_ || state != tessera::PictureState::SHOWN) return;
    lv_obj_update_layout(place_);
    lv_area_t a;
    lv_obj_get_coords(place_, &a);
    ESP_LOGI(TAG, "picture popup shown %d,%d,%d,%d", (int) a.x1, (int) a.y1, (int) a.x2, (int) a.y2);
  }

 private:
  bool closes_;
  lv_obj_t *face_{}, *mark_{}, *place_{}, *second_{};
};

void HostProbe::on_message(JsonObjectConst message) {
  // A message of the harness that asks for a closer: {"do": "<mode>", "tile": <the layout's tile it opens from>}.
  const char *what = message["do"] | "";
  // {"do": "wake"}: the plugin wakes the screen (plugin API 0.16), as one that senses someone come does.
  if (std::string(what) == "wake") {
    ESP_LOGI(TAG, "wake");
    tessera::wake(this);
    return;
  }
  // {"do": "camera_turn"}: how far the screen's camera turns its picture (plugin API 0.19), 0 on a board without one.
  if (std::string(what) == "camera_turn") {
    ESP_LOGI(TAG, "camera_turn=%d", tessera::camera_turn());
    return;
  }
  // {"do": "popup"} (or "popup_self", one that closes itself on a tap), {"do": "popup_close"}: plugin API 0.18.
  if (std::string(what) == "popup" || std::string(what) == "popup_self") {
    ProbePopup::plugin = this;
    const bool closes = std::string(what) == "popup_self";
    ESP_LOGI(TAG, "do %s shown=%d", what, (int) tessera::show_popup(this, [closes]() { return new ProbePopup(closes); }));
    return;
  }
  if (std::string(what) == "popup_picture" || std::string(what) == "popup_picture_close") {
    ProbePopup::plugin = this;
    const bool closes = std::string(what) == "popup_picture_close";
    ESP_LOGI(TAG, "do %s shown=%d", what, (int) tessera::show_popup(this, "shot", [closes]() { return new ProbePicturePopup(closes); }));
    return;
  }
  // {"do": "turns"}: what a part's turn (ui::rotate) does through ui::animate and ui::still, on parts made for it: one
  // turned to 90 that pulses, one that spins and is stilled, one turned again while it spins, one never turned; and how
  // many turns the host keeps after 300 turned parts were made and deleted (none of theirs may stay).
  if (std::string(what) == "turns") {
    lv_obj_t *parent = lv_layer_top();
    auto turn = [](lv_obj_t *o) { return (int) lv_obj_get_style_transform_rotation(o, LV_PART_MAIN); };
    lv_obj_t *pulse = lv_obj_create(parent), *spin = lv_obj_create(parent), *again = lv_obj_create(parent), *plain = lv_obj_create(parent);
    ui::rotate(pulse, 90);
    ui::animate(pulse, tessera::Motion::PULSE, 800);
    const int pulsing = turn(pulse);
    ui::still(pulse);
    const int pulsed = turn(pulse);
    ui::rotate(spin, 90);
    ui::animate(spin, tessera::Motion::SPIN, 800);
    ui::still(spin);
    const int spun = turn(spin);
    ui::rotate(again, 90);
    ui::animate(again, tessera::Motion::SPIN, 800);
    ui::rotate(again, 180);
    ui::still(again);
    const int turned_again = turn(again);
    ui::animate(plain, tessera::Motion::SPIN, 800);
    ui::still(plain);
    const int unturned = turn(plain);
    const size_t before = plugin_host::turns_kept();
    for (int i = 0; i < 300; ++i) {
      lv_obj_t *o = lv_obj_create(parent);
      ui::rotate(o, 45 + i);
      lv_obj_delete(o);
    }
    const size_t after = plugin_host::turns_kept();
    for (lv_obj_t *o : {pulse, spin, again, plain}) lv_obj_delete(o);
    ESP_LOGI(TAG, "turns pulsing=%d pulsed=%d spun=%d again=%d unturned=%d kept=%u,%u,%u", pulsing, pulsed, spun, turned_again,
             unturned, (unsigned) before, (unsigned) after, (unsigned) plugin_host::turns_kept());
    return;
  }
  // {"do": "popup_place"}: a popup without an id that makes a place for a picture (it has none, plugin API 0.27).
  if (std::string(what) == "popup_place") {
    ProbePopup::plugin = this;
    ESP_LOGI(TAG, "do popup_place shown=%d", (int) tessera::show_popup(this, []() { return new ProbePopup(false, true); }));
    return;
  }
  if (std::string(what) == "popup_close") {
    ESP_LOGI(TAG, "do popup_close shown=%d", (int) tessera::popup_shown(this));
    tessera::close_popup(this);
    ESP_LOGI(TAG, "popup shown=%d", (int) tessera::popup_shown(this));
    return;
  }
  if (*what) {
    ProbeCloser::mode = what;
    ESP_LOGI(TAG, "do %s", what);
    tessera::open_card(plugin_id(), "closer", "", message["tile"] | -1, "Closer");
    return;
  }
  std::string result;
  serializeJson(message["result"], result);
  // An answer the manifest maps (`answers`, 0.5) comes as its fields: a day of prices as one list of numbers.
  ESP_LOGI(TAG, "message re=%u ok=%d prices=%u result=%.120s", message["re"] | 0u, (int) (message["ok"] | false),
           (unsigned) message["result"]["prices"].size(), result.c_str());
}

}  // namespace esphome::host_probe
