// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_call_serve.cpp -o /tmp/test_call_serve && /tmp/test_call_serve
// A call's media served by the screen itself (call_serve.h): the heads of its parts are the ones a live view reads
// (ESP Screens' live_stream.part_head, byte for byte), a request is answered only under the call's token, and a
// camera's frame gets a size the JPEG encoder takes.
#include "../components/smart_display/call_serve.h"
#include <cassert>
#include <cstdio>
#include <string>

using namespace call_serve;

int main() {
  char head[HEAD];
  size_t n = picture_head(head, sizeof head, 31234, 4000000001u);
  assert(std::string(head, n) == "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 31234\r\nX-Made: 4000000001\r\n\r\n");
  n = sound_head(head, sizeof head, SOUND_PART, 17);
  assert(std::string(head, n) == "--frame\r\nContent-Type: audio/L16\r\nX-Sound: talk\r\nContent-Length: 640\r\nX-Made: 17\r\n\r\n");
  assert(picture_head(head, 20, 1, 1) == 0);    // no room: nothing, never a cut head

  const std::string token = "aB3-_tokenOfTheCall22";
  const std::string good = "GET /call/" + token + ".mjpeg HTTP/1.1\r\nHost: 192.0.2.7:8555\r\n\r\n";
  assert(asks_for(good.data(), good.size(), token));
  for (const std::string &bad : {std::string("GET /call/") + token + "x.mjpeg HTTP/1.1\r\n", std::string("GET /call/wrongTokenOfTheCall22.mjpeg HTTP/1.1\r\n"),
                                 std::string("POST /call/") + token + ".mjpeg HTTP/1.1\r\n", std::string("GET /call/") + token + ".mjpe",
                                 std::string("GET /camera/") + token + ".mjpeg HTTP/1.1\r\n", std::string("")})
    assert(!asks_for(bad.data(), bad.size(), token));
  assert(!asks_for(good.data(), good.size(), ""));   // no call, no stream

  // 1280 x 720 from the camera: 720 a side at most, in whole blocks of 16.
  Size s = picture_size(1280, 720);
  assert(s.w == 720 && s.h == 400);
  s = picture_size(640, 480);
  assert(s.w == 640 && s.h == 480);   // never larger than the frame
  s = picture_size(1920, 1080);
  assert(s.w == 720 && s.h == 400);
  s = picture_size(720, 1280);
  assert(s.w == 400 && s.h == 720);   // a standing frame alike
  assert(picture_size(16, 16).w == 0);
  std::puts("PASS: part heads as a live view reads them, a request answered only under the call's token, picture sizes in whole blocks");
  return 0;
}
