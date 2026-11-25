#pragma once
// The preview probe (tests/fixtures/plugins/preview_probe/tessera-plugin.yaml): a tile and a card that say what only
// this code can say, for web/wasm/test_plugin_module.mjs.
#include "esphome/core/component.h"
#include "esphome/components/smart_display/plugin_api.h"

namespace esphome::preview_probe {

class PreviewProbe : public Component, public tessera::Plugin {
 public:
  void setup() override;
  float get_setup_priority() const override { return setup_priority::DATA; }
};

}  // namespace esphome::preview_probe
