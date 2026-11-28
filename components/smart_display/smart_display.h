#pragma once
#include "runtime_tiles.h"
#include "chunk_transport.h"
#include "loop_record.h"
#include "ppa_trace.h"
#include "heap_watch.h"
#include "abort_record.h"
#include "hw.h"
#include "hw_hello.h"
#include "audio_owner.h"
#include "esphome/components/text/text.h"
#include "esphome/core/component.h"
namespace esphome::smart_display {
// Command transport, not a stored JSON state. HA states stay well below 255 chars.
class DashboardInbox : public text::Text, public Component {
 public:
  void setup() override {
    loop_record::take();  // what the main loop was doing when the last task watchdog restarted the screen, if one did
    ppa_trace::take();    // the last calls to the PPA, and the one that never came back if one did (a P4 screen)
    abort_record::take();  // what the last abort or failed assert said, if one restarted it
    heap_watch::setup();  // the internal RAM's lowest and its failed allocations, of the previous boot and this one
    // Who may play and listen (audio_owner.h): every change of hands is one INFO line, the proof of the ranking on glass.
    audio_owner::the().log = [](const char *line) { ESP_LOGI("audio", "%s", line); };
    this->publish_state("Ready for tile configuration");
  }
  void loop() override { heap_watch::tick(millis()); }
  // Every log subscriber asks for the config dump: the records of the previous boot go to each of them.
  void dump_config() override {
    loop_record::report();
    ppa_trace::report();
    abort_record::report();
    heap_watch::dump();
  }
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
