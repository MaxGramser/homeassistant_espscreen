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
    ESP_LOGI(TAG, "status ready=%d settings=%u interval=%d updates=%d", (int) plugin_->ready_, plugin_->rows_,
             (int) plugin_->interval_, (int) plugin_->updates_);
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
  }
  void on_state(JsonObjectConst data) override { ESP_LOGI(TAG, "card state n=%d", data["n"] | -1); }
  void on_tick(uint32_t epoch) override { ESP_LOGI(TAG, "card tick epoch=%u", (unsigned) epoch); }
  void on_theme() override { ESP_LOGI(TAG, "card theme dark=%d", (int) theme::dark); }
  bool on_back() override { ESP_LOGI(TAG, "card back"); return false; }

 private:
  lv_obj_t *words_{};
};

void HostProbe::setup() {
  add_tile("probe", [this]() { return new ProbeTile(this); });
  add_card("detail", []() { return new ProbeCard(); });
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
  ESP_LOGI(TAG, "ready id=%s version=%s", plugin_id(), plugin_version());
}
void HostProbe::on_interval(uint32_t now_ms) {
  interval_ = true;
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
  std::string result;
  serializeJson(message["result"], result);
  // An answer the manifest maps (`answers`, 0.5) comes as its fields: a day of prices as one list of numbers.
  ESP_LOGI(TAG, "message re=%u ok=%d prices=%u result=%.120s", message["re"] | 0u, (int) (message["ok"] | false),
           (unsigned) message["result"]["prices"].size(), result.c_str());
}

}  // namespace esphome::host_probe
