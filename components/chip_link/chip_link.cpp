// A board's second chip on its serial line (chip_link.h).
#include "chip_link.h"

#include <cstdio>

#include "driver/uart.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome::chip_link {

namespace {
const char *const TAG = "chip_link";
// What waits to go out: eight frames of sound, 90 ms of the line at full speed.
constexpr int SEND_BUFFER = 8192;
constexpr int READ_BUFFER = 1024;
constexpr uint32_t ASK_ABSENT_MS = 2000, ASK_PRESENT_MS = 10000;
// A chip that left three asks unanswered is gone.
constexpr uint8_t UNANSWERED_MOST = 3;
}  // namespace

void ChipLink::setup() {
  const auto port = static_cast<uart_port_t>(this->port_);
  uart_config_t line{};
  line.baud_rate = static_cast<int>(chip_protocol::BAUD);
  line.data_bits = UART_DATA_8_BITS;
  line.parity = UART_PARITY_DISABLE;
  line.stop_bits = UART_STOP_BITS_1;
  line.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
  line.source_clk = UART_SCLK_DEFAULT;
  if (uart_driver_install(port, READ_BUFFER, SEND_BUFFER, 0, nullptr, 0) != ESP_OK || uart_param_config(port, &line) != ESP_OK ||
      uart_set_pin(port, this->tx_pin_, this->rx_pin_, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE) != ESP_OK) {
    ESP_LOGE(TAG, "The line to the chip did not open");
    this->mark_failed();
    return;
  }
  this->ask_();
}

void ChipLink::dump_config() {
  ESP_LOGCONFIG(TAG, "Second chip: UART%d, TX GPIO%d, RX GPIO%d, %u baud", this->port_, this->tx_pin_, this->rx_pin_,
                (unsigned) chip_protocol::BAUD);
  if (this->present_) {
    ESP_LOGCONFIG(TAG, "  Firmware %s, room for %u samples", this->version().c_str(), (unsigned) this->room_);
  } else {
    ESP_LOGCONFIG(TAG, "  No chip with Tessera's firmware answers");
  }
}

std::string ChipLink::version() const {
  if (!this->present_) return "";
  char text[16];
  std::snprintf(text, sizeof text, "%u.%u.%u", this->version_[0], this->version_[1], this->version_[2]);
  return text;
}

bool ChipLink::send(uint8_t type, const uint8_t *payload, size_t length) {
  if (this->is_failed()) return false;
  const auto port = static_cast<uart_port_t>(this->port_);
  const size_t wire = chip_protocol::frame(type, payload, length, this->wire_);
  size_t room = 0;
  if (wire == 0 || uart_get_tx_buffer_free_size(port, &room) != ESP_OK || room < wire) return false;
  return uart_write_bytes(port, this->wire_, wire) == static_cast<int>(wire);
}

void ChipLink::loop() {
  const auto port = static_cast<uart_port_t>(this->port_);
  uint8_t some[128];
  for (;;) {
    const int got = uart_read_bytes(port, some, sizeof some, 0);
    if (got <= 0) break;
    for (int i = 0; i < got; ++i)
      if (this->reader_.feed(some[i])) this->heard_();
  }
  if (millis() - this->asked_ >= (this->present_ ? ASK_PRESENT_MS : ASK_ABSENT_MS)) this->ask_();
}

void ChipLink::ask_() {
  this->asked_ = millis();
  if (this->present_ && ++this->unanswered_ > UNANSWERED_MOST) this->set_present_(false);
  this->send(chip_protocol::HELLO, nullptr, 0);
}

void ChipLink::heard_() {
  const uint8_t *p = this->reader_.payload();
  switch (this->reader_.type()) {
    case chip_protocol::HELLO_BACK:
      if (this->reader_.size() < 7) return;
      this->unanswered_ = 0;
      if (p[0] != chip_protocol::VERSION || !(p[4] & chip_protocol::WHAT_SOUND)) {
        if (this->present_) this->set_present_(false);
        return;
      }
      this->version_[0] = p[1];
      this->version_[1] = p[2];
      this->version_[2] = p[3];
      this->room_ = chip_protocol::u16(p + 5);
      {
        // A chip that started anew since the last answer is a chip that came: it knows nothing it was told before.
        const uint16_t started = this->reader_.size() >= 9 ? chip_protocol::u16(p + 7) : 0;
        const bool anew = this->present_ && started != this->started_;
        this->started_ = started;
        if (!this->present_ || anew) this->set_present_(true);
      }
      return;
    case chip_protocol::STATUS:
      if (this->reader_.size() < 10) return;
      this->unanswered_ = 0;
      if (this->status_) this->status_(p[0], p[1], chip_protocol::u32(p + 2), chip_protocol::u32(p + 6));
      return;
    default:
      return;
  }
}

void ChipLink::set_present_(bool present) {
  this->present_ = present;
  this->unanswered_ = 0;
  if (present) {
    ESP_LOGI(TAG, "The chip answers: firmware %s", this->version().c_str());
  } else {
    ESP_LOGW(TAG, "The chip no longer answers");
  }
  if (this->changed_) this->changed_(present);
}

}  // namespace esphome::chip_link
