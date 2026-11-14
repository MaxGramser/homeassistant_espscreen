// The talk uplink's pure parts (components/smart_display/talk_uplink.h): the request, a chunk's framing, the voice's
// level and its bar. The task needs a screen.
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "../components/smart_display/talk_uplink.h"

using namespace talk_uplink;

int main() {
  // The request says it is raw PCM at 16 kHz, in chunks, and that the connection ends with it.
  const std::string head = request_head("192.0.2.1", "/camera/abc/talk");
  assert(head.rfind("POST /camera/abc/talk HTTP/1.1\r\n", 0) == 0);
  assert(head.find("Transfer-Encoding: chunked\r\n") != std::string::npos);
  assert(head.find("audio/x-s16le;rate=16000") != std::string::npos);
  assert(head.size() > 4 && head.compare(head.size() - 4, 4, "\r\n\r\n") == 0);

  // A chunk's head: its length in hexadecimal.
  char out[12];
  assert(chunk_head(out, sizeof out, PART) == 5);
  assert(std::strncmp(out, "280\r\n", 5) == 0);

  // PART is 20 ms of 16 kHz samples, and the buffer holds whole parts.
  assert(PART == 640);
  assert(BUFFER % 2 == 0 && BUFFER >= 10 * PART);

  // Level: silence is the floor, a full-scale tone is about -3 dB, and a bar is 0 at the floor and 1 at the ceiling.
  std::vector<int16_t> quiet(320, 0), loud(320);
  for (size_t i = 0; i < loud.size(); ++i) loud[i] = i % 2 ? 30000 : -30000;
  assert(level_db(quiet.data(), quiet.size()) <= -120.0f);
  assert(level_db(loud.data(), loud.size()) > -1.0f);
  assert(bar_of(-120.0f) == 0.0f);
  assert(bar_of(0.0f) == 1.0f);
  const float mid = bar_of((FLOOR_DB + CEILING_DB) / 2);
  assert(mid > 0.45f && mid < 0.55f);
  return 0;
}
