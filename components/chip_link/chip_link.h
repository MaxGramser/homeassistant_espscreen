#pragma once
// A board's second chip on its serial line (docs/SECOND_CHIP.md): the line, the frames on it (chip_protocol.h) and
// whether a chip with Tessera's firmware answers.
//
// The chip is asked who it is every two seconds until it answers, and every ten after that. A chip that runs another
// firmware (Seeed's own, as the board comes) never answers, and then present() is false: nothing waits for it, and the
// screen tells the app it has no sound (hw::speaker_works). A chip that gets Tessera's firmware while the screen runs
// (New screen writes it over USB) is found at the next ask, without a restart, and so is one that restarted: it says a
// new number in its answer, and whoever listens (on_present) tells it again what it forgot, as its volume.
//
// What it does not know: what the frames are for. The speaker (chip_speaker.h) sends the sound and reads the STATUS.
#include <cstdint>
#include <functional>
#include <string>

#include "chip_protocol.h"
#include "esphome/core/component.h"

namespace esphome::chip_link {

class ChipLink : public Component {
 public:
  void set_line(int port, int tx_pin, int rx_pin) {
    this->port_ = port;
    this->tx_pin_ = tx_pin;
    this->rx_pin_ = rx_pin;
  }
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::BUS; }

  // Whether a chip that plays sound answers on the line.
  bool present() const { return this->present_; }
  // Its firmware, "1.0.0", or nothing while none answers.
  std::string version() const;
  // The samples of sound it holds at most.
  uint32_t room() const { return this->room_; }
  // A frame onto the line. False when the line has no room for it this moment: ask again at the next pass.
  bool send(uint8_t type, const uint8_t *payload, size_t length);
  // For every STATUS of the chip: stream, state, samples taken, samples played.
  void on_status(std::function<void(uint8_t, uint8_t, uint32_t, uint32_t)> &&heard) { this->status_ = std::move(heard); }
  // When a chip came or went.
  void on_present(std::function<void(bool)> &&heard) { this->changed_ = std::move(heard); }

 protected:
  void ask_();
  void heard_();
  void set_present_(bool present);

  int port_{1}, tx_pin_{-1}, rx_pin_{-1};
  bool present_{false};
  uint8_t version_[3]{}, unanswered_{0};
  uint32_t room_{0}, asked_{0};
  uint16_t started_{0};  // the number the chip drew at its start (HELLO_BACK), to tell a chip that restarted
  chip_protocol::Reader reader_;
  uint8_t wire_[chip_protocol::WIRE_MOST];
  std::function<void(uint8_t, uint8_t, uint32_t, uint32_t)> status_;
  std::function<void(bool)> changed_;
};

}  // namespace esphome::chip_link
