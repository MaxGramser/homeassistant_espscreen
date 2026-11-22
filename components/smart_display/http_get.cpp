// The socket of http_get.h: what every download of the screen from ESP Screen Manager opens (docs/SCREEN_FILES.md).
// Compiled with the pictures (SCREEN_PICTURES, packages/features/camera.yaml), as everything that downloads is; a 4 MB
// board without them pays nothing.
#include "http_get.h"
#ifdef SCREEN_PICTURES
#include <cerrno>
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

namespace http_get {

constexpr uint32_t CONNECT_MS = 4000;  // as ESPHome's http_request timeout was

int connect_to(const Address &a, uint32_t wait_ms) {
  addrinfo hints{};
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  addrinfo *found = nullptr;
  const std::string port = std::to_string(a.port);
  if (getaddrinfo(a.host.c_str(), port.c_str(), &hints, &found) != 0 || !found) return -1;
  int fd = socket(found->ai_family, found->ai_socktype, found->ai_protocol);
  if (fd < 0) { freeaddrinfo(found); return -1; }
  const int flags = fcntl(fd, F_GETFL, 0);
  fcntl(fd, F_SETFL, flags | O_NONBLOCK);
  int r = connect(fd, found->ai_addr, found->ai_addrlen);
  freeaddrinfo(found);
  if (r < 0 && errno != EINPROGRESS) { close(fd); return -1; }
  if (r < 0) {
    fd_set writable;
    FD_ZERO(&writable);
    FD_SET(fd, &writable);
    timeval wait{static_cast<time_t>(CONNECT_MS / 1000), static_cast<suseconds_t>((CONNECT_MS % 1000) * 1000)};
    if (select(fd + 1, nullptr, &writable, nullptr, &wait) <= 0) { close(fd); return -1; }
    int error = 0;
    socklen_t len = sizeof(error);
    if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &len) < 0 || error != 0) { close(fd); return -1; }
  }
  fcntl(fd, F_SETFL, flags);
  timeval chunk{static_cast<time_t>(wait_ms / 1000), static_cast<suseconds_t>((wait_ms % 1000) * 1000)};
  setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &chunk, sizeof(chunk));
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &chunk, sizeof(chunk));
  return fd;
}
bool send_all(int fd, const std::string &text) {
  size_t sent = 0;
  while (sent < text.size()) {
    const auto n = send(fd, text.data() + sent, text.size() - sent, 0);
    if (n <= 0) return false;
    sent += static_cast<size_t>(n);
  }
  return true;
}

}  // namespace http_get
#endif
