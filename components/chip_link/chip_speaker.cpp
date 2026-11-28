// The sound output of a board's second chip as ESPHome's speaker (chip_speaker.h).
#include "chip_speaker.h"

#include <algorithm>
#include <cmath>

#include "esp_timer.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome::chip_link {

namespace {
const char *const TAG = "chip_link.speaker";
constexpr uint32_t MASK = 16384 - 1;
}  // namespace

void ChipSpeaker::setup() {
  RAMAllocator<int16_t> allocator;
  this->held_ = allocator.allocate(HELD);
  if (this->held_ == nullptr) {
    ESP_LOGE(TAG, "No memory for the sound");
    this->mark_failed();
    return;
  }
  this->link_->on_status([this](uint8_t stream, uint8_t state, uint32_t taken, uint32_t played) {
    this->status_(stream, state, taken, played);
  });
  // A chip that came (back) knows no stream of ours and no volume.
  this->link_->on_present([this](bool) {
    LockGuard lock(this->mutex_);
    this->open_ = this->ending_ = this->cut_ = false;
    this->volume_told_ = false;
    this->tail_ = this->head_;
    this->state_ = speaker::STATE_STOPPED;
  });
}

void ChipSpeaker::dump_config() { ESP_LOGCONFIG(TAG, "Speaker on the second chip, volume %.2f", this->volume_); }

size_t ChipSpeaker::play(const uint8_t *data, size_t length) {
  const auto &info = this->audio_stream_info_;
  const uint8_t channels = std::max<uint8_t>(info.get_channels(), 1);
  // Anything but 16 bits is not ours to play, and neither is sound without a chip: it goes, so nothing waits for it.
  if (this->held_ == nullptr || info.get_bits_per_sample() != 16 || !this->link_->present()) return length;
  const uint32_t rate = info.get_sample_rate();
  const uint8_t step = static_cast<uint8_t>(std::max<uint32_t>(1, (rate + RATE_MOST - 1) / RATE_MOST));
  const size_t frame = 2u * channels * step;
  LockGuard lock(this->mutex_);
  if (rate / step != this->held_rate_ || step != this->held_step_) {
    // Another rate: what is held goes to the chip first.
    if (this->fill_() > 0) return 0;
    this->held_rate_ = rate / step;
    this->held_step_ = step;
  }
  const size_t frames = std::min<size_t>(length / frame, HELD - this->fill_());
  const int count = channels * step;
  for (size_t i = 0; i < frames; ++i) {
    int32_t sum = 0;
    for (int k = 0; k < count; ++k) {
      const uint8_t *at = data + i * frame + 2 * k;
      sum += static_cast<int16_t>(at[0] | (at[1] << 8));
    }
    this->held_[this->head_++ & MASK] = static_cast<int16_t>(sum / count);
  }
  if (frames > 0) {
    this->last_ms_ = millis();
    this->finish_ = false;
  }
  return frames * frame;
}

void ChipSpeaker::loop() {
  if (this->held_ == nullptr) return;
  const uint32_t now = millis();
  LockGuard lock(this->mutex_);
  if (!this->link_->present()) {
    this->tail_ = this->head_;
    return;
  }
  if (!this->volume_told_) {
    // 0 to 1 evenly in decibels, 0 silence.
    float gain = 0.0f;
    if (!this->mute_state_ && this->volume_ > 0.0f) gain = powf(10.0f, (std::min(this->volume_, 1.0f) - 1.0f) * RANGE_DB / 20.0f);
    uint8_t p[2];
    chip_protocol::put16(p, static_cast<uint16_t>(lroundf(gain * 32768.0f)));
    this->volume_told_ = this->link_->send(chip_protocol::VOLUME, p, sizeof p);
  }
  if (this->cut_) {
    const uint8_t p[2] = {this->stream_, 1};
    if (!this->link_->send(chip_protocol::END, p, sizeof p)) return;
    this->cut_ = false;
  }
  if (this->fill_() > 0 && (!this->open_ || this->ending_ || this->rate_ != this->held_rate_)) {
    // A new sound: its own stream, which ends whatever the chip still played.
    uint8_t p[3] = {static_cast<uint8_t>(this->stream_ + 1), 0, 0};
    chip_protocol::put16(p + 1, static_cast<uint16_t>(this->held_rate_));
    if (!this->link_->send(chip_protocol::BEGIN, p, sizeof p)) return;
    this->stream_ = p[0];
    this->rate_ = this->held_rate_;
    this->step_ = this->held_step_;
    this->sent_ = this->played_ = 0;
    this->open_ = true;
    this->ending_ = false;
    this->state_ = speaker::STATE_RUNNING;
  }
  if (!this->open_) {
    if (this->state_ != speaker::STATE_STOPPED && now - this->last_ms_ > IDLE_MS) this->state_ = speaker::STATE_STOPPED;
    return;
  }
  while (this->fill_() > 0) {
    const uint32_t count = std::min({this->fill_(), static_cast<uint32_t>(chip_protocol::AUDIO_MOST),
                                     chip_protocol::may_send(this->link_->room(), this->sent_, this->played_)});
    if (count == 0) break;
    this->out_[0] = this->stream_;
    for (uint32_t i = 0; i < count; ++i)
      chip_protocol::put16(this->out_ + 1 + 2 * i, static_cast<uint16_t>(this->held_[(this->tail_ + i) & MASK]));
    if (!this->link_->send(chip_protocol::AUDIO, this->out_, 1 + 2 * count)) break;
    this->tail_ += count;
    this->sent_ += count;
  }
  if (this->fill_() == 0 && !this->ending_ && (this->finish_ || now - this->last_ms_ > IDLE_MS)) {
    const uint8_t p[2] = {this->stream_, 0};
    if (this->link_->send(chip_protocol::END, p, sizeof p)) {
      this->ending_ = true;
      this->state_ = speaker::STATE_STOPPING;
    }
  }
}

void ChipSpeaker::status_(uint8_t stream, uint8_t state, uint32_t, uint32_t played) {
  uint32_t frames = 0;
  {
    LockGuard lock(this->mutex_);
    if (!this->open_ || stream != this->stream_) return;
    frames = (played - this->played_) * this->step_;
    this->played_ = played;
    if (state == chip_protocol::STATE_IDLE && this->ending_) {
      this->open_ = this->ending_ = false;
      this->state_ = speaker::STATE_STOPPED;
    }
  }
  if (frames > 0) this->audio_output_callback_.call(frames, esp_timer_get_time());
}

void ChipSpeaker::start() {
  LockGuard lock(this->mutex_);
  if (this->state_ == speaker::STATE_STOPPED) {
    this->state_ = speaker::STATE_RUNNING;
    this->last_ms_ = millis();
  }
}

void ChipSpeaker::stop() {
  LockGuard lock(this->mutex_);
  this->tail_ = this->head_;
  if (this->open_) this->cut_ = true;
  this->open_ = this->ending_ = this->finish_ = false;
  this->state_ = speaker::STATE_STOPPED;
}

void ChipSpeaker::finish() {
  LockGuard lock(this->mutex_);
  this->finish_ = true;
}

bool ChipSpeaker::has_buffered_data() const { return this->fill_() > 0 || (this->open_ && this->sent_ != this->played_); }

void ChipSpeaker::set_volume(float volume) {
  this->volume_ = volume;
  this->volume_told_ = false;
}

void ChipSpeaker::set_mute_state(bool mute_state) {
  this->mute_state_ = mute_state;
  this->volume_told_ = false;
}

}  // namespace esphome::chip_link
