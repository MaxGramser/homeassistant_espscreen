#pragma once
// The screen's microphone going up to the add-on, one way for the doorbell's Talk and for a call (docs/CALLS.md, "The
// voice"): 16 kHz 16-bit mono, 20 ms parts, a chunked HTTP POST on the camera port the screen already uses. No codec on
// the screen: a voice costs 256 kbit/s, which is nothing beside the camera's picture, and works on every board with a
// microphone. The add-on keeps the rest (talk_bridge.py for a doorbell; voice switching, docs/CALLS.md).
//
// What a PC can check is here: the request's head, a chunk's framing, the voice's level (tests/test_talk_uplink.cpp).
// talk_uplink.cpp has the task, which starts and ends by the main loop's word and never touches the microphone's own
// buffers: the microphone's callback puts a whole part into a stream buffer or leaves it out whole (a part cut in the
// middle of a sample turns all that follows into noise, docs/CAMERA.md).
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>

#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif

namespace esphome {
namespace microphone {
class Microphone;
}
}  // namespace esphome

namespace talk_uplink {

constexpr uint32_t RATE = 16000;
constexpr size_t PART = RATE * 2 * 20 / 1000;  // 20 ms of samples, what goes in one chunk
constexpr size_t BUFFER = 12800;               // 400 ms between the microphone and the socket
constexpr uint32_t ANSWER_MS = 18000;          // the add-on connects the camera first (talk_bridge.ANSWER_SECONDS) and says so
constexpr int GAIN = 4;                        // as Screen camera's microphone: these boards' microphones are quiet
// The voice's level for the key's bars: an RMS below FLOOR is silence, CEILING is a full bar.
constexpr float FLOOR_DB = -55.0f, CEILING_DB = -18.0f;
// The level from which a part counts as someone speaking (what turns Talk off after a minute of nothing).
constexpr float VOICE_DB = -44.0f;

// How far along the talk is (the key's words, docs/DOORBELL.md "Talk").
enum class State : uint8_t { OFF, CONNECTING, LIVE, BUSY, FAILED };

inline std::string request_head(const std::string &host, const std::string &path) {
  return "POST " + path + " HTTP/1.1\r\nHost: " + host +
         "\r\nContent-Type: audio/x-s16le;rate=16000\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n";
}

// A chunk's head for `length` bytes: "280\r\n". The bytes follow, then "\r\n".
inline int chunk_head(char *out, size_t size, size_t length) { return std::snprintf(out, size, "%zx\r\n", length); }

// dB of a 16-bit part's RMS, below full scale; -120 for silence.
inline float level_db(const int16_t *samples, size_t count) {
  if (!count) return -120.0f;
  double sum = 0;
  for (size_t i = 0; i < count; ++i) sum += static_cast<double>(samples[i]) * samples[i];
  const double rms = std::sqrt(sum / count);
  return rms < 1.0 ? -120.0f : static_cast<float>(20.0 * std::log10(rms / 32768.0));
}

// The bars' height, 0 to 1, of a level in dB.
inline float bar_of(float db) {
  if (db <= FLOOR_DB) return 0.0f;
  if (db >= CEILING_DB) return 1.0f;
  return (db - FLOOR_DB) / (CEILING_DB - FLOOR_DB);
}

#if defined(USE_MICROPHONE) && defined(USE_LIVE_VIEW)
// The board's microphone (packages/features/audio-player.yaml binds it).
void bind_microphone(esphome::microphone::Microphone *microphone);
bool available();
// The main loop's: start talking to `url` (http://host:port/camera/<token>/talk); false when one is already going or
// nothing to talk with. The microphone starts at once, its first parts are thrown away until the add-on says it is live.
bool start(const std::string &url);
void stop();
State state();
// While muted the microphone's parts go up as silence, so the stream on the far side stays alive (docs/CALLS.md).
void set_muted(bool muted);
// The voice's bar, 0 to 1, of the last few parts; when the voice was last above VOICE_DB (the main loop's clock).
float bar();
uint32_t voice_at();
#else
template<class Microphone> inline void bind_microphone(Microphone *) {}
inline bool available() { return false; }
inline bool start(const std::string &) { return false; }
inline void stop() {}
inline State state() { return State::OFF; }
inline void set_muted(bool) {}
inline float bar() { return 0.0f; }
inline uint32_t voice_at() { return 0; }
#endif

}  // namespace talk_uplink
