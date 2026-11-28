#include "preview_probe.h"
#include <string>

namespace esphome::preview_probe {
namespace {

// "<hello in the screen's language> <the tile's word> <the value of its data>", and under it the ticks it counted.
class NoteTile : public tessera::Tile {
 public:
  explicit NoteTile(const tessera::Plugin *plugin) : plugin_(plugin) {}
  void create(const tessera::TileContext &context) override {
    tile_ = context.tile;
    word_ = context.options["word"] | "";
    line_ = tessera::ui::label(context.parent, tessera::Font::TITLE);
    lv_obj_set_width(line_, context.width);
    count_ = tessera::ui::label(context.parent, tessera::Font::BODY, theme::MUTED);
    lv_obj_set_width(count_, context.width);
    lv_obj_set_y(count_, tessera::ui::line_height(tessera::Font::TITLE));
    said();
  }
  void on_state(JsonObjectConst data) override {
    value_ = data["value"] | "";
    said();
  }
  void on_tick(uint32_t) override {
    ticks_ += 1;
    tessera::ui::set_text(count_, tessera::format(plugin_->text("ticks"), ticks_));
  }
  void on_tap() override { tessera::open_card(plugin_->plugin_id(), "more", "", tile_); }

 private:
  void said() { tessera::ui::set_text(line_, std::string(plugin_->text("hello")) + " " + word_ + " " + value_); }
  const tessera::Plugin *plugin_;
  lv_obj_t *line_ = nullptr, *count_ = nullptr;
  std::string word_, value_;
  int tile_ = -1;
  long ticks_ = 0;
};

class MoreCard : public tessera::Card {
 public:
  explicit MoreCard(const tessera::Plugin *plugin) : plugin_(plugin) {}
  void open(const tessera::CardContext &context) override {
    lv_obj_t *line = tessera::ui::label(context.parent, tessera::Font::TITLE);
    lv_obj_set_width(line, context.width);
    tessera::ui::set_text(line, plugin_->text("more"));
  }

 private:
  const tessera::Plugin *plugin_;
};

}  // namespace

void PreviewProbe::setup() {
  add_tile("note", [this]() -> tessera::Tile * { return new NoteTile(this); });
  add_card("more", [this]() -> tessera::Card * { return new MoreCard(this); });
}

}  // namespace esphome::preview_probe
