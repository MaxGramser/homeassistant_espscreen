#pragma once
// A plain HTTP GET on the LAN, the one way the screen downloads from ESP Screen Manager (docs/SCREEN_FILES.md). The add-on
// serves everything a screen fetches on its own port (8098): pictures and streams under /camera/ (picture_fetch.h,
// live_view.h), files under /files/ (file_fetch.h), and takes a screen's voice there (talk_uplink.h). Each of those
// reads its bytes its own way; what they share is here: the link, the answer's head and the socket.
//
// What it knows: http://host[:port]/path and the head of an answer, with the headers the add-on sends. What it does not:
// HTTPS, redirects and chunked transfer encoding, which the add-on never sends over the LAN.
//
// The link and the head are parsed free of sockets, so tests/test_picture_fetch.cpp and tests/test_live_view.cpp check
// them on a PC; http_get.cpp has the socket (BSD sockets on the ESP32's lwIP and on the host renders alike).
#include <cstddef>
#include <cstdint>
#include <string>

namespace http_get {

// ---- the link: http://host[:port]/path, nothing else (plain HTTP on the LAN, as the add-on serves it) ----
struct Address {
  std::string host, path;
  uint16_t port = 80;
  bool ok = false;
};
inline Address split(const std::string &url) {
  Address a;
  const std::string scheme = "http://";
  if (url.compare(0, scheme.size(), scheme) != 0) return a;
  const size_t start = scheme.size();
  const size_t slash = url.find('/', start);
  std::string authority = url.substr(start, slash == std::string::npos ? std::string::npos : slash - start);
  a.path = slash == std::string::npos ? "/" : url.substr(slash);
  const size_t colon = authority.rfind(':');
  if (colon != std::string::npos) {
    const std::string digits = authority.substr(colon + 1);
    if (digits.empty() || digits.size() > 5) return a;
    unsigned port = 0;
    for (char c : digits) {
      if (c < '0' || c > '9') return a;
      port = port * 10 + (c - '0');
    }
    if (port == 0 || port > 65535) return a;
    a.port = static_cast<uint16_t>(port);
    authority.resize(colon);
  }
  a.host = authority;
  a.ok = !a.host.empty() && a.host.find_first_of(" @/\\") == std::string::npos;
  return a;
}

// ---- the answer's head: the status line and the headers, up to the blank line ----
struct Head {
  bool complete = false;   // the blank line was seen; `length` bytes belong to the head
  size_t length = 0;
  int status = 0;
  bool has_length = false;
  size_t content_length = 0;
  std::string etag;
  bool audio = false;  // Content-Type audio/... (a live camera's sound between its pictures, live_view.h)
  // X-Picture: still, a live camera's picture from before its stream came (its still while WebRTC starts): the screen
  // shows it with the loader in its corner (live_view.h, "Until it is live"). Without it a picture is live.
  bool still = false;
  // X-Made: when the app made a live camera's picture, in its own milliseconds (wrapping at 2^32): set beside the
  // screen's clock, what is left over the least of it is how long the picture waited on its way (live_view.cpp).
  bool has_made = false;
  uint32_t made = 0;
  // X-Sound: talk, a part of sound from someone in a conversation: the screen plays it with a far smaller run-up.
  bool talk = false;
  // X-Turn: the app turned a live picture as a turned glass is (90, 180 or 270 degrees, the hello's picture_turn), so
  // the screen copies it onto the glass straight (live_view.cpp, show); 0: upright.
  int turn = 0;
};
inline bool same_ignoring_case(const char *a, const char *b, size_t n) {
  for (size_t i = 0; i < n; ++i) {
    char x = a[i], y = b[i];
    if (x >= 'A' && x <= 'Z') x += 32;
    if (y >= 'A' && y <= 'Z') y += 32;
    if (x != y) return false;
  }
  return true;
}
inline Head parse_head(const char *data, size_t size) {
  Head h;
  // The end of the head: CRLF CRLF (or LF LF from a lenient server).
  size_t end = std::string::npos, skip = 0;
  for (size_t i = 0; i + 1 < size; ++i) {
    if (data[i] == '\n' && data[i + 1] == '\n') { end = i; skip = 2; break; }
    if (i + 3 < size && data[i] == '\r' && data[i + 1] == '\n' && data[i + 2] == '\r' && data[i + 3] == '\n') { end = i; skip = 4; break; }
  }
  if (end == std::string::npos) return h;
  h.complete = true;
  h.length = end + skip;
  // Line by line.
  size_t pos = 0;
  bool first = true;
  while (pos < end) {
    size_t nl = pos;
    while (nl < end && data[nl] != '\n') ++nl;
    size_t stop = nl;
    if (stop > pos && data[stop - 1] == '\r') --stop;
    const char *line = data + pos;
    const size_t len = stop - pos;
    if (first) {
      first = false;
      // HTTP/1.1 200 OK
      size_t sp = 0;
      while (sp < len && line[sp] != ' ') ++sp;
      int status = 0;
      for (size_t i = sp + 1; i < len && line[i] >= '0' && line[i] <= '9'; ++i) status = status * 10 + (line[i] - '0');
      h.status = status;
    } else {
      size_t colon = 0;
      while (colon < len && line[colon] != ':') ++colon;
      if (colon < len) {
        size_t v = colon + 1;
        while (v < len && (line[v] == ' ' || line[v] == '\t')) ++v;
        size_t ve = len;
        while (ve > v && (line[ve - 1] == ' ' || line[ve - 1] == '\t')) --ve;
        if (colon == 14 && same_ignoring_case(line, "content-length", 14)) {
          size_t n = 0;
          bool digits = v < ve;
          for (size_t i = v; i < ve; ++i) {
            if (line[i] < '0' || line[i] > '9') { digits = false; break; }
            n = n * 10 + (line[i] - '0');
          }
          if (digits) { h.has_length = true; h.content_length = n; }
        } else if (colon == 4 && same_ignoring_case(line, "etag", 4)) {
          h.etag.assign(line + v, ve - v);
        } else if (colon == 12 && same_ignoring_case(line, "content-type", 12)) {
          h.audio = ve - v >= 6 && same_ignoring_case(line + v, "audio/", 6);
        } else if (colon == 9 && same_ignoring_case(line, "x-picture", 9)) {
          h.still = ve - v == 5 && same_ignoring_case(line + v, "still", 5);
        } else if (colon == 7 && same_ignoring_case(line, "x-sound", 7)) {
          h.talk = ve - v == 4 && same_ignoring_case(line + v, "talk", 4);
        } else if (colon == 6 && same_ignoring_case(line, "x-made", 6)) {
          uint32_t n = 0;
          bool digits = v < ve;
          for (size_t i = v; i < ve; ++i) {
            if (line[i] < '0' || line[i] > '9') { digits = false; break; }
            n = n * 10 + static_cast<uint32_t>(line[i] - '0');
          }
          if (digits) { h.has_made = true; h.made = n; }
        } else if (colon == 6 && same_ignoring_case(line, "x-turn", 6)) {
          int n = 0;
          bool digits = v < ve && ve - v <= 3;
          for (size_t i = v; digits && i < ve; ++i) {
            if (line[i] < '0' || line[i] > '9') { digits = false; break; }
            n = n * 10 + (line[i] - '0');
          }
          if (digits && (n == 90 || n == 180 || n == 270)) h.turn = n;
        }
      }
    }
    pos = nl + 1;
  }
  return h;
}

// The socket of a download: connected within four seconds with its reads and writes waiting at most `wait_ms`, or -1;
// and a request sent whole.
int connect_to(const Address &a, uint32_t wait_ms);
bool send_all(int fd, const std::string &text);

}  // namespace http_get
