#include "panel_voice.h"
#ifdef USE_SCREEN_DEVICE_VOICE
#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/components/json/json_util.h"
#include "panel_voice_timing.h"
#include "esp_crt_bundle.h"
#include <algorithm>
#include <cstring>

namespace esphome::smart_display {
static const char *const TAG = "panel_voice";

void PanelVoice::setup() {
  mic_->add_data_callback([this](const std::vector<uint8_t> &data) { capture_(data); });
}

std::string PanelVoice::context_(const char *type) const {
  return json::build_json([&](JsonObject root) {
    root["type"] = type; root["page"] = page_(); root["revision"] = revision_();
    if (strcmp(type, "prepare") == 0) { root["version"] = 2; root["rate"] = 16000; }
  });
}

void PanelVoice::start() {
  if (active()) return;
  if (raw_mic_->get_mute_state() || !page_ || !revision_ || revision_() == "0000000000000000") {
    set_phase_(ERROR, millis()); return;
  }
  if (!buffers_()) { set_phase_(ERROR, millis()); return; }
  pre_roll_enabled_ = false;
  input_->reset();
  uint8_t audio[2048];
  while (const size_t length = pre_roll_->read(audio, sizeof(audio), 0))
    input_->write_without_replacement(audio, length, 0, false);
  // Capture the tail of the detector's stream immediately. The provider receives
  // nothing until the wake handoff and the explicit start have been accepted.
  capture_enabled_ = true; send_audio_ = false; start_sent_ = false;
  last_speech_ = millis();
  wake_.request(millis());
  set_phase_(CONNECTING, millis());
}

bool PanelVoice::buffers_() {
  // Five seconds of post-wake audio cover a cold or reconnecting provider.
  // The half-second rolling pre-roll stays local until an explicit wake/start.
  if (!input_) input_ = ring_buffer::RingBuffer::create(160000);
  if (!pre_roll_) pre_roll_ = ring_buffer::RingBuffer::create(16000);
  if (!output_) output_ = ring_buffer::RingBuffer::create(8192);
  if (!incoming_) incoming_ = xQueueCreate(12, sizeof(Command));
  if (!outgoing_) outgoing_ = xQueueCreate(12, sizeof(Command));
  return input_ && pre_roll_ && output_ && incoming_ && outgoing_;
}

void PanelVoice::prepare_() {
  if (running_ || !worker_done_) return;
  if (!buffers_()) {
    if (active()) fail_();
    else { disconnect_(); set_phase_(ERROR, millis()); }
    return;
  }
  output_->reset(); xQueueReset(incoming_); xQueueReset(outgoing_);
  hello_ = context_("prepare"); last_context_ = context_("page");
  fault_ = false; server_closed_ = false; failed_ = false; connected_ = false; worker_done_ = false; running_ = true;
  send_audio_ = false; start_sent_ = false;
  last_context_at_ = last_server_ = millis();
  if (xTaskCreate(worker, "panel_voice_tx", 6144, this, 4, nullptr) != pdPASS) {
    worker_done_ = true; fault_ = true;
  }
}

void PanelVoice::begin_() {
  conversation_ = true;
  ready_ = finishing_ = finish_called_ = mic_started_ = false;
  expected_ = accepted_ = pending_size_ = pending_offset_ = 0;
  started_ = millis();
  set_phase_(CONNECTING, started_);
  prepare_();
}

void PanelVoice::disconnect_() {
  running_ = false; send_audio_ = false;
  retry_at_ = millis() + retry_ms_;
  retry_ms_ = std::min<uint32_t>(60000, retry_ms_ * 2);
}

void PanelVoice::stop() {
  const bool was_active = active();
  wake_.cancel();
  capture_enabled_ = false; pre_roll_enabled_ = false;
  disconnect_();
  if (!was_active) { set_phase_(IDLE, millis()); return; }
  raw_mic_->stop(); mic_started_ = false;
  speaker_->stop(); amp_->turn_off();
  conversation_ = true; // Release the drivers before allowing another wake.
  set_phase_(STOPPING, millis());
}

void PanelVoice::fail_(const char *reason) {
  failed_ = true;
  ESP_LOGW(TAG, "Voice stopped: %s (phase %d)", reason ? reason : "transport/audio fault", int(phase_));
  stop();
}

void PanelVoice::capture_(const std::vector<uint8_t> &data) {
  if (raw_mic_->get_mute_state() || data.empty()) return;
  if (!capture_enabled_) {
    if (pre_roll_enabled_ && pre_roll_) pre_roll_->write(data.data(), data.size());
    return;
  }
  uint64_t energy = 0;
  for (size_t i = 0; i + 1 < data.size(); i += 2) {
    const int32_t sample = int16_t(uint16_t(data[i]) | (uint16_t(data[i+1]) << 8));
    energy += sample * sample;
  }
  if (data.size() >= 2 && energy / (data.size()/2) >= 68719) last_speech_ = millis(); // RMS 0.008
  if (input_->write_without_replacement(data.data(), data.size(), 0, false) != data.size()) fault_ = true;
}

void PanelVoice::send_(const std::string &text) {
  if (!running_) return;
  Command command{};
  if (text.size() >= sizeof(command.text)) { fault_ = true; return; }
  memcpy(command.text, text.data(), text.size());
  if (xQueueSend(outgoing_, &command, 0) != pdPASS) fault_ = true;
}

void PanelVoice::handle_(const char *text) {
  const bool parsed = json::parse_json(text, [this](JsonObject root) {
    const std::string type = root["type"] | "";
    const auto now = millis();
    if (type == "ping") { send_("{\"type\":\"pong\"}"); return true; }
    if (type == "prepared") { retry_ms_ = 1000; return true; }
    if (type == "listen") {
      const int idle = root["idle_seconds"] | 0;
      if (!conversation_ || idle < 1 || idle > 300 || !speaker_->is_stopped()) return false;
      idle_ms_ = idle * 1000;
      // Preserve the initial buffered command when the provider becomes ready.
      if (phase_ != CONNECTING) input_->reset();
      last_speech_ = now; send_audio_ = true;
      set_phase_(LISTENING, now);
    } else if (type == "pause") {
      capture_enabled_ = false; send_audio_ = false; raw_mic_->stop(); mic_started_ = false; set_phase_(THINKING, now);
    } else if (type == "play") {
      const int bytes = root["bytes"] | 0, rate = root["rate"] | 0;
      if (bytes <= 0 || bytes > 16000 * 2 * 45 || bytes % 2 || rate != 16000 || !speaker_->is_stopped()) return false;
      capture_enabled_ = false; send_audio_ = false; raw_mic_->stop(); mic_started_ = false;
      expected_ = bytes; accepted_ = pending_size_ = pending_offset_ = 0;
      ready_ = finishing_ = finish_called_ = false; amp_at_ = 0;
      speaker_->set_audio_stream_info(audio::AudioStreamInfo(16, 1, 16000));
      output_->reset(); set_phase_(SPEAKING, now);
    } else if (type == "finish" && phase_ == SPEAKING && accepted_ == expected_) {
      finishing_ = true;
    } else if (type == "error") {
      if (active()) fail_("add-on error"); else disconnect_();
    } else return false;
    return true;
  });
  if (!parsed) fault_ = true;
}

void PanelVoice::loop() {
  using voice_timing::elapsed;
  const auto now = millis();
  pre_roll_enabled_ = warm_enabled_ && !active() && phase_ != STOPPING && !raw_mic_->get_mute_state();
  const int action = wake_.step(now, wake_running_ && wake_running_(), raw_mic_->is_stopped(),
                               speaker_->is_stopped(), conversation_, raw_mic_->get_mute_state());
  if ((action & voice_wake::Gate::STOP_WAKE) && wake_stop_) wake_stop_();
  if ((action & voice_wake::Gate::START_WAKE) && wake_start_) { set_phase_(IDLE, now); wake_start_(); }
  if (action & voice_wake::Gate::START_VOICE) begin_();
  if ((action & voice_wake::Gate::FAILED) && !conversation_) {
    capture_enabled_ = false; set_phase_(ERROR, now);
  }
  if (raw_mic_->get_mute_state() && !conversation_ && phase_ == CONNECTING) {
    capture_enabled_ = false; set_phase_(IDLE, now);
  }
  if (phase_ == STOPPING) {
    if (worker_done_ && raw_mic_->is_stopped() && speaker_->is_stopped()) {
      if (input_) input_->reset();
      if (output_) output_->reset();
      if (pre_roll_) pre_roll_->reset();
      conversation_ = false;
      set_phase_(failed_ ? ERROR : IDLE, now);
    }
    return;
  }
  // Warm sockets do not own the microphone and do not count as conversations.
  // Only an opted-in wake detector keeps a provider prepared between requests.
  if (!active() && (!warm_enabled_ || raw_mic_->get_mute_state())) {
    if (running_) disconnect_();
    if (pre_roll_) pre_roll_->reset();
    return;
  }
  if (!running_ && worker_done_ && page_ && revision_ && revision_() != "0000000000000000" &&
      (conversation_ || (warm_enabled_ && int32_t(now - retry_at_) >= 0))) prepare_();
  if (!running_) return;
  Command command;
  while (xQueueReceive(incoming_, &command, 0) == pdPASS && running_) handle_(command.text);
  // Process a queued provider error before the close frame. A normal close
  // (silence, Stop or add-on shutdown) returns to idle without an error flash.
  if (server_closed_ || fault_ || (connected_ && elapsed(now, last_server_.load()) > 5000)) {
    if (active()) {
      if (server_closed_) stop();
      else fail_(fault_ ? "transport/audio fault" : "add-on heartbeat timeout");
    }
    else disconnect_();
    return;
  }
  if (conversation_ && (raw_mic_->get_mute_state() || elapsed(now, started_) >= 600000 ||
      (phase_ == CONNECTING && elapsed(now, phase_started_) > 4500) ||
      (phase_ == THINKING && elapsed(now, phase_started_) > 120000) ||
      (phase_ == SPEAKING && elapsed(now, phase_started_) > 55000))) { fail_("session/phase deadline or mute"); return; }
  if (conversation_ && running_ && !start_sent_) { send_(context_("start")); start_sent_ = true; }
  if (elapsed(now, last_context_at_) >= 250) {
    last_context_at_ = now;
    const auto context = context_("page");
    if (context != last_context_) { last_context_ = context; send_(context); }
  }
  if (conversation_ && (phase_ == LISTENING || phase_ == CONNECTING)) {
    if (phase_ == LISTENING && (elapsed(now, last_speech_.load()) >= idle_ms_ || elapsed(now, phase_started_) > 30000)) { stop(); return; }
    if (!mic_started_ && raw_mic_->is_stopped() && speaker_->is_stopped()) {
      capture_enabled_ = true; raw_mic_->start(); mic_started_ = true;
    }
    if (!raw_mic_->is_running() && elapsed(now, phase_started_) > 3000) fail_("microphone start timeout");
  } else if (phase_ == SPEAKING) {
    if (!ready_) {
      if (!raw_mic_->is_stopped()) return;
      speaker_->start();
      if (!speaker_->is_running()) return;
      if (!amp_at_) { amp_->turn_on(); amp_at_ = now; }
      if (elapsed(now, amp_at_) < 50) return;
      ready_ = true; send_("{\"type\":\"ready\"}");
    }
    if (pending_offset_ == pending_size_) {
      pending_size_ = output_->read(pending_, sizeof(pending_), 0); pending_offset_ = 0;
    }
    if (pending_size_ > pending_offset_) {
      const size_t sent = speaker_->play(pending_ + pending_offset_, pending_size_ - pending_offset_, 0);
      pending_offset_ += sent; accepted_ += sent;
      if (accepted_ > expected_) { fail_(); return; }
      if (sent) send_("{\"type\":\"credit\",\"bytes\":" + std::to_string(accepted_) + "}");
    }
    if (finishing_ && accepted_ == expected_) {
      if (!finish_called_) { speaker_->finish(); finish_called_ = true; }
      if (speaker_->is_stopped()) {
        amp_->turn_off(); set_phase_(THINKING, now); send_("{\"type\":\"done\"}");
      }
    }
  }
}

void PanelVoice::worker(void *arg) {
  auto *self = static_cast<PanelVoice *>(arg);
  self->network_(); self->worker_done_ = true; vTaskDelete(nullptr);
}

void PanelVoice::network_() {
  esp_websocket_client_config_t config{};
  config.uri = url_.c_str(); config.headers = headers_.c_str();
  config.disable_auto_reconnect = true;
  config.network_timeout_ms = 1500; config.buffer_size = 4096;
  config.ping_interval_sec = 2; config.pingpong_timeout_sec = 3;
  config.crt_bundle_attach = esp_crt_bundle_attach;
  client_ = esp_websocket_client_init(&config);
  if (!client_) { fault_ = true; return; }
  esp_websocket_register_events(client_, WEBSOCKET_EVENT_ANY, event, this);
  if (esp_websocket_client_start(client_) != ESP_OK) fault_ = true;
  bool sent_start = false;
  uint8_t pcm[2048]; Command command;
  while (running_ && !fault_) {
    if (connected_) {
      if (!sent_start) {
        if (esp_websocket_client_send_text(client_, hello_.c_str(), hello_.size(), pdMS_TO_TICKS(1000)) != int(hello_.size())) fault_ = true;
        sent_start = true;
      }
      while (xQueueReceive(outgoing_, &command, 0) == pdPASS && !fault_) {
        const auto length = strlen(command.text);
        if (esp_websocket_client_send_text(client_, command.text, length, pdMS_TO_TICKS(1000)) != int(length)) fault_ = true;
      }
      const size_t length = send_audio_ && capture_enabled_ ? input_->read(pcm, sizeof(pcm), 0) : 0;
      if (length && capture_enabled_ && esp_websocket_client_send_bin(client_, reinterpret_cast<char *>(pcm), length,
              pdMS_TO_TICKS(1000)) != int(length)) fault_ = true;
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }
  esp_websocket_client_stop(client_);
  esp_websocket_client_destroy(client_); client_ = nullptr; connected_ = false;
}

void PanelVoice::event(void *arg, esp_event_base_t, int32_t id, void *data) {
  auto *self = static_cast<PanelVoice *>(arg);
  if (id == WEBSOCKET_EVENT_CONNECTED) { self->last_server_ = millis(); self->connected_ = true; }
  else if (id == WEBSOCKET_EVENT_DISCONNECTED || id == WEBSOCKET_EVENT_ERROR) {
    if (self->running_ && !self->server_closed_) self->fault_ = true;
  } else if (id == WEBSOCKET_EVENT_DATA) self->receive_(static_cast<esp_websocket_event_data_t *>(data));
}

void PanelVoice::receive_(esp_websocket_event_data_t *event) {
  if (!running_) return;
  last_server_ = millis();
  if (event->op_code == 0x08) {
    const auto *bytes = reinterpret_cast<const uint8_t *>(event->data_ptr);
    if (event->data_len >= 2 && bytes[0] == 3 && bytes[1] == 232) server_closed_ = true;
    else fault_ = true;
    return;
  }
  if (event->op_code != 1 && event->op_code != 2) return;
  if (event->data_len < 0 || event->payload_offset < 0 || event->payload_len < 0 ||
      event->payload_offset + event->data_len > event->payload_len) { fault_ = true; return; }
  if (event->op_code == 2) {
    if (event->payload_len > 2048 || event->payload_len % 2 ||
        output_->write_without_replacement(event->data_ptr, event->data_len, 0, false) != size_t(event->data_len)) fault_ = true;
  } else {
    if (event->payload_len >= int(sizeof(text_))) { fault_ = true; return; }
    memcpy(text_ + event->payload_offset, event->data_ptr, event->data_len);
    if (event->payload_offset + event->data_len == event->payload_len) {
      text_[event->payload_len] = '\0';
      Command command{}; memcpy(command.text, text_, event->payload_len + 1);
      if (xQueueSend(incoming_, &command, 0) != pdPASS) fault_ = true;
    }
  }
}
}  // namespace esphome::smart_display
#endif
