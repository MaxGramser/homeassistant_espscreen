#pragma once
#include "runtime_tiles.h"
#ifdef USE_SCREEN_AUDIO_TEST
#include "audio_test_capture.h"
#endif
#include "chunk_transport.h"
#include "esphome/components/text/text.h"
#include "esphome/core/component.h"
namespace esphome::smart_display {
// Command transport, not a stored JSON state. HA states stay well below 255 chars.
class DashboardInbox : public text::Text, public Component {
 public:
  void setup() override { this->publish_state("Ready for tile configuration"); }
 protected:
  runtime_tiles::Chunks chunks_;
  void control(const std::string &value) override {
    if (!chunks_.accept(value, millis())) { this->publish_state("Error: incomplete message"); return; }
    if (!chunks_.complete) return;
    std::string decoded(chunks_.data.size() * 3 / 4 + 1, '\0');
    size_t length = base64_decode(chunks_.data, reinterpret_cast<uint8_t *>(decoded.data()), decoded.size());
    chunks_.reset();
    if (length == 0 || length > 4096) { this->publish_state("Error: invalid encoding"); return; }
    decoded.resize(length);
    this->publish_state(runtime_tiles::receive(decoded));
  }
};
}
