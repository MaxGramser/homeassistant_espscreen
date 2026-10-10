#include "host_probe.h"
#include "esphome/core/log.h"
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
  ~ProbeTile() override { ESP_LOGI(TAG, "tile=%d destroy", tile_); }

  void create(const tessera::TileContext &c) override {
    tile_ = c.tile;
    word_ = c.options["word"] | "";   // copied: the context is gone after this call
    ESP_LOGI(TAG, "tile=%d create %dx%d cells=%ux%u name=[%s] word=[%s] entity=[%s]", tile_, c.width, c.height,
             (unsigned) c.columns, (unsigned) c.rows, c.name, word_.c_str(), c.entity);
    // The moments of boot, which came before anyone listened to the log, and how often before_update was heard.
    ESP_LOGI(TAG, "status ready=%d settings=%u interval=%d updates=%d early=%d", (int) plugin_->ready_, plugin_->rows_,
             (int) plugin_->interval_, (int) plugin_->updates_, plugin_->early_);
    badge_ = ui::block(c.parent, theme::ACCENT);
    lv_obj_set_size(badge_, std::max(1, c.width / 2), ui::line_height(Font::TITLE) + ui::px(4));
    lv_obj_set_pos(badge_, 0, 0);
    label_ = ui::label(badge_, Font::TITLE, theme::ON_ACCENT);
    ui::set_text(label_, word_);
    lv_obj_center(label_);
    number_ = ui::label(c.parent, Font::VALUE, theme::INK);
    lv_obj_set_width(number_, c.width);
    lv_obj_set_pos(number_, 0, lv_obj_get_height(badge_) + ui::px(4));
    plugin_->ask_once();
  }
  void on_state(JsonObjectConst data) override {
    n_ = data["n"] | -1;
    // A tile of an entity gets its lists whole when they fit (0.5): how many prices of each day arrived.
    JsonObjectConst attributes = data["attributes"];
    ESP_LOGI(TAG, "tile=%d state n=%d wait=[%s] today=%u tomorrow=%u", tile_, n_, data["wait"] | "",
             (unsigned) attributes["today"].size(), (unsigned) attributes["tomorrow"].size());
  }
  void on_tick(uint32_t epoch) override {
    ESP_LOGI(TAG, "tile=%d tick epoch=%u n=%d", tile_, (unsigned) epoch, n_);
    ui::set_text(number_, std::to_string(n_));
  }
  void on_theme() override {
    ESP_LOGI(TAG, "tile=%d theme dark=%d", tile_, (int) theme::dark);
    lv_obj_set_style_bg_color(badge_, ui::color(theme::ACCENT), 0);
    ui::set_color(label_, theme::ON_ACCENT);
    ui::set_color(number_, theme::INK);
  }
  void on_tap() override {
    ESP_LOGI(TAG, "tile=%d tap", tile_);
    tessera::open_card(plugin_->plugin_id(), "detail", "", tile_, "Probe card");
  }

 private:
  HostProbe *plugin_;
  int tile_ = -1, n_ = -1;
  std::string word_;
  lv_obj_t *badge_{}, *label_{}, *number_{};
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
  }
  void on_state(JsonObjectConst data) override { ESP_LOGI(TAG, "card state n=%d", data["n"] | -1); }
  void on_tick(uint32_t epoch) override { ESP_LOGI(TAG, "card tick epoch=%u", (unsigned) epoch); }
  void on_theme() override { ESP_LOGI(TAG, "card theme dark=%d", (int) theme::dark); }
  bool on_back() override { ESP_LOGI(TAG, "card back"); return false; }

 private:
  lv_obj_t *words_{}, *foot_{};
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

void HostProbe::setup() {
  set_up_ = true;
  add_tile("probe", [this]() { return new ProbeTile(this); });
  add_card("detail", []() { return new ProbeCard(); });
  add_card("closer", []() { return new ProbeCloser(); });
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
void HostProbe::on_touch() { ESP_LOGI(TAG, "touch"); }

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

void HostProbe::on_message(JsonObjectConst message) {
  // A message of the harness that asks for a closer: {"do": "<mode>", "tile": <the layout's tile it opens from>}.
  const char *what = message["do"] | "";
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
