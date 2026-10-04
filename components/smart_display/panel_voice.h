#pragma once
#include "esphome/core/defines.h"
#ifdef USE_SCREEN_DEVICE_VOICE
#include "esphome/core/component.h"
#include "esphome/components/microphone/microphone_source.h"
#include "esphome/components/speaker/speaker.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/ring_buffer/ring_buffer.h"
#include "esp_websocket_client.h"
#include "voice_wake_gate.h"
#include <atomic>
#include <functional>
#include <string>
#include <freertos/queue.h>

namespace esphome::smart_display {
// Driver calls and UI state belong to loop(). Network I/O has its own bounded
// worker; microphone and websocket callbacks only put bytes in ESPHome buffers.
class PanelVoice : public Component {
 public:
  enum Phase { IDLE, CONNECTING, LISTENING, THINKING, SPEAKING, STOPPING, ERROR };
  void setup() override;
  void loop() override;
  void on_shutdown() override { stop(); }
  void set_microphone(microphone::MicrophoneSource *source, microphone::Microphone *raw) { mic_ = source; raw_mic_ = raw; }
  void set_speaker(speaker::Speaker *speaker) { speaker_ = speaker; }
  void set_amplifier(switch_::Switch *amp) { amp_ = amp; }
  void set_url(const std::string &url) { url_ = url; }
  void set_token(const std::string &token) { headers_ = "Authorization: Bearer " + token + "\r\n"; }
  void set_page(std::function<int()> page) { page_ = page; }
  void set_revision(std::function<std::string()> revision) { revision_ = revision; }
  void set_wake_callbacks(std::function<void()> start, std::function<void()> stop, std::function<bool()> running) {
    wake_start_ = start; wake_stop_ = stop; wake_running_ = running;
  }
  void configure_wake(bool enabled, int model) { warm_enabled_ = enabled; wake_.configure(enabled, model); }
  bool wake_ready() const { return wake_.ready(); }
  void start();
  void stop();
  bool active() const { return wake_.pending() || conversation_; }
  bool listening() const {
    return phase_ == LISTENING && capture_enabled_ && raw_mic_->is_running() && !raw_mic_->get_mute_state();
  }
  int phase() const { return phase_; }

 protected:
  struct Command { char text[256]; };
  static void worker(void *arg);
  static void event(void *arg, esp_event_base_t base, int32_t id, void *data);
  void network_();
  void receive_(esp_websocket_event_data_t *event);
  void send_(const std::string &text);
  void handle_(const char *text);
  void capture_(const std::vector<uint8_t> &data);
  void fail_(const char *reason = nullptr);
  void begin_();
  bool buffers_();
  void prepare_();
  void disconnect_();
  bool transport_active_() const { return running_ || !worker_done_ || phase_ == STOPPING; }
  void set_phase_(Phase next, uint32_t now) { phase_ = next; phase_started_ = now; }
  std::string context_(const char *type) const;

  microphone::MicrophoneSource *mic_{nullptr};
  microphone::Microphone *raw_mic_{nullptr};
  speaker::Speaker *speaker_{nullptr};
  switch_::Switch *amp_{nullptr};
  std::function<int()> page_;
  std::function<std::string()> revision_;
  voice_wake::Gate wake_;
  std::function<void()> wake_start_, wake_stop_;
  std::function<bool()> wake_running_;
  std::string url_, headers_, hello_, last_context_;
  Phase phase_{IDLE};
  uint32_t started_{0}, phase_started_{0}, last_context_at_{0}, amp_at_{0}, idle_ms_{5000};
  uint32_t retry_at_{0}, retry_ms_{1000};
  size_t expected_{0}, accepted_{0}, pending_size_{0}, pending_offset_{0};
  bool ready_{false}, finishing_{false}, finish_called_{false}, failed_{false}, mic_started_{false};
  bool warm_enabled_{false}, conversation_{false}, start_sent_{false};
  uint8_t pending_[2048];
  char text_[256]{};
  QueueHandle_t incoming_{nullptr}, outgoing_{nullptr};
  std::unique_ptr<ring_buffer::RingBuffer> input_, output_, pre_roll_;
  std::atomic<bool> running_{false}, worker_done_{true}, connected_{false}, capture_enabled_{false}, fault_{false};
  std::atomic<bool> server_closed_{false};
  std::atomic<bool> send_audio_{false}, pre_roll_enabled_{false};
  std::atomic<uint32_t> last_server_{0}, last_speech_{0};
  esp_websocket_client_handle_t client_{nullptr};
};
}  // namespace esphome::smart_display
#endif
