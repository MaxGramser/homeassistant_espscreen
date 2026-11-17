#pragma once
// A call's media served by the screen itself (docs/CALLS.md, "Screen to screen"): in a direct call each screen serves its
// own camera and microphone to the other one, and fetches the other's the same way, so ESP Screens only signals.
//
// What it is: one small server while a direct call is live. It answers GET /call/<token>.mjpeg on PORT with the stream
// a live view already plays (live_view.h): multipart/x-mixed-replace, pictures as image/jpeg and the voice as audio/L16
// parts marked X-Sound: talk, each part's head byte for byte as ESP Screens writes it (live_stream.part_head).
// What it knows: the call's token and the one address that may fetch (both from the op `call`, module_call.cpp), the
// microphone's parts (talk_uplink's tap) and the camera's frames the screen is handed for its own view
// (live_view::own_frame). What it does not: who calls whom, the keys of a call, the glass. Its pure parts are here and
// tests/test_call_serve.cpp proves them; the task is call_serve.cpp.
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

namespace call_serve {

constexpr uint16_t PORT = 8555;                 // calls.DIRECT_PORT (tests/test_calls.py holds the two together)
constexpr size_t SOUND_PART = 640;              // 20 ms of 16 kHz, 16-bit mono: one part, as talk_uplink's
constexpr uint32_t PICTURES_A_SECOND = 10;      // the floor a call's picture is held to (docs/CALLS.md)
constexpr int PICTURE_SIDE = 720;               // a call's pictures at most this many pixels a side
constexpr size_t HEAD = 128;                    // room for a part's head

inline const char *answer() {
  return "HTTP/1.0 200 OK\r\nContent-Type: multipart/x-mixed-replace;boundary=frame\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
}
inline const char *refusal() { return "HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"; }

// A part's head, as live_stream.part_head writes it; `made` is this screen's clock in ms (the viewer only sets it
// beside its own to see how long parts wait on the way). The length written, 0 when `out` is too small.
inline size_t picture_head(char *out, size_t size, size_t length, uint32_t made) {
  const int n = std::snprintf(out, size, "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\nX-Made: %u\r\n\r\n",
                              static_cast<unsigned>(length), static_cast<unsigned>(made));
  return n > 0 && static_cast<size_t>(n) < size ? static_cast<size_t>(n) : 0;
}
inline size_t sound_head(char *out, size_t size, size_t length, uint32_t made) {
  const int n = std::snprintf(out, size,
                              "--frame\r\nContent-Type: audio/L16\r\nX-Sound: talk\r\nContent-Length: %u\r\nX-Made: %u\r\n\r\n",
                              static_cast<unsigned>(length), static_cast<unsigned>(made));
  return n > 0 && static_cast<size_t>(n) < size ? static_cast<size_t>(n) : 0;
}

// Whether a request asks for this call's stream: its first line is "GET /call/<token>.mjpeg HTTP/1.x". The token is
// compared in the same time whatever it holds, so a guess learns nothing from how long the answer took.
inline bool asks_for(const char *request, size_t length, const std::string &token) {
  static const char before[] = "GET /call/", after[] = ".mjpeg ";
  const size_t b = sizeof before - 1, a = sizeof after - 1;
  if (token.empty() || length < b + token.size() + a) return false;
  unsigned char differs = 0;
  for (size_t i = 0; i < b; ++i) differs |= static_cast<unsigned char>(request[i] ^ before[i]);
  for (size_t i = 0; i < token.size(); ++i) differs |= static_cast<unsigned char>(request[b + i] ^ token[i]);
  for (size_t i = 0; i < a; ++i) differs |= static_cast<unsigned char>(request[b + token.size() + i] ^ after[i]);
  return differs == 0;
}

// A camera frame's size for a call: its own shape at most PICTURE_SIDE a side, in whole blocks of 16 pixels (the JPEG
// encoder's), never larger than the frame. How the frame is scaled into it is the picture engine's (its cut). {0, 0}
// for a frame too small to send.
struct Size { int w, h; };
inline Size picture_size(int width, int height) {
  if (width < 32 || height < 32) return {0, 0};
  const int longest = width > height ? width : height, side = longest < PICTURE_SIDE ? longest : PICTURE_SIDE;
  const int w = (width * side / longest) & ~15, h = (height * side / longest) & ~15;
  return w >= 16 && h >= 16 ? Size{w, h} : Size{0, 0};
}

// The task's side (call_serve.cpp), from the main loop unless said otherwise.
// `token`: what the other screen fetches under; `peer`: its address, the only one that is answered.
bool start(const std::string &token, const std::string &peer);
void stop();
bool running();
bool viewed();                 // the other screen fetches now
uint32_t started();            // esphome::millis() at start
void set_muted(bool muted);    // the microphone's parts go as silence, so the stream stays alive
void set_picture(bool on);     // the camera is on for this call
bool wants_picture();          // any task: the camera's frames are wanted (live_view::own_wanted)
// The camera's task: one frame of the screen's own camera (live_view::own_frame). Returns at once when no picture is
// due; otherwise scales it for the call under the glass's hold, for the server's task to encode.
void frame(const uint8_t *data, int width, int height, bool yuv420);

}  // namespace call_serve

// Built where a call, a live view, a microphone and the P4's picture engine are (the including file brings ESPHome's
// defines first); elsewhere nothing of the task exists and nothing calls it.
#if defined(SD_MOD_CALL) && defined(USE_LIVE_VIEW) && defined(USE_MICROPHONE) && defined(PICTURE_ENGINE_P4) && defined(SCREEN_PICTURES)
#define CALL_SERVE 1
#endif
