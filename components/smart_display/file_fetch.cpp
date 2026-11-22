// A file downloaded beside the main loop: the queue, the task and its socket (file_fetch.h says why and what).
//
// One download at a time. The main loop starts it (tick) and hands its answer over (tick); the task only reads the
// socket into a buffer in PSRAM, and writes `state` DONE last (release/acquire), so everything the main loop reads it
// reads after that, and everything the task reads was written before the task was made.
#include "file_fetch.h"
#ifdef SCREEN_PICTURES
#include <atomic>
#include <cerrno>
#include <cstring>
#include <deque>
#include <sys/socket.h>
#include <unistd.h>
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "http_get.h"
#include "roomy.h"
#ifdef USE_ESP32
#include "psram_task.h"
#else
#include <thread>
#endif

namespace file_fetch {

static const char *const TAG = "file";
constexpr uint32_t RECV_MS = 4000;    // a chunk that does not come in this long ends the download
constexpr uint32_t WHOLE_MS = 10000;  // and a file that takes longer than this altogether
constexpr size_t CHUNK = 4096;
constexpr size_t HEAD_MAX = 4096;
constexpr uint32_t STACK_BYTES = 6144;  // a socket and a chunk; the body goes to PSRAM

enum State : int { IDLE = 0, LOADING = 1, DONE = 2 };

struct Job {
  std::string url;
  size_t most = 0;
  Done done;
};

static std::deque<Job> waiting;  // the main loop's alone
static Job running;
static std::atomic<int> state{IDLE};
// Written by the task before DONE.
static uint8_t *result = nullptr;
static size_t result_size = 0;
static bool result_ok = false;
static uint32_t started = 0;
#ifdef USE_ESP32
static psram_task::Task task;
#endif

static void download() {
  const http_get::Address a = http_get::split(running.url);
  if (!a.ok) { ESP_LOGW(TAG, "not a link: %s", running.url.c_str()); return; }
  const int fd = http_get::connect_to(a, RECV_MS);
  if (fd < 0) { ESP_LOGW(TAG, "no connection to %s:%u", a.host.c_str(), a.port); return; }
  const std::string request = "GET " + a.path + " HTTP/1.1\r\nHost: " + a.host + ":" + std::to_string(a.port) +
                              "\r\nConnection: close\r\n\r\n";
  if (!http_get::send_all(fd, request)) { ESP_LOGW(TAG, "the request did not go out"); close(fd); return; }
  auto *chunk = static_cast<uint8_t *>(roomy::allocate(CHUNK));
  if (!chunk) { ESP_LOGW(TAG, "no memory for the download"); close(fd); return; }
  roomy::Text head;
  http_get::Head answer;
  uint8_t *body = nullptr;
  size_t have = 0, room = 0;
  bool closed = false, failed = false;
  while (!closed && !failed) {
    if (esphome::millis() - started > WHOLE_MS) { ESP_LOGW(TAG, "took too long"); failed = true; break; }
    const auto n = recv(fd, chunk, CHUNK, 0);
    if (n < 0) {
      if (errno == EINTR) continue;
      ESP_LOGW(TAG, "the download stopped (%d)", errno);
      failed = true;
      break;
    }
    if (n == 0) { closed = true; break; }
    const uint8_t *data = chunk;
    size_t size = static_cast<size_t>(n);
    if (!answer.complete) {
      head.append(reinterpret_cast<const char *>(data), size);
      answer = http_get::parse_head(head.data(), head.size());
      if (!answer.complete) {
        if (head.size() > HEAD_MAX) { ESP_LOGW(TAG, "no file in the answer"); failed = true; }
        continue;
      }
      if (answer.status != 200) { ESP_LOGW(TAG, "HTTP %d for %s", answer.status, a.path.c_str()); failed = true; break; }
      if (answer.has_length && answer.content_length > running.most) {
        ESP_LOGW(TAG, "%s is %u bytes, more than the %u allowed", a.path.c_str(), (unsigned) answer.content_length, (unsigned) running.most);
        failed = true;
        break;
      }
      room = answer.has_length ? answer.content_length : running.most;
      body = static_cast<uint8_t *>(roomy::allocate(room ? room : 1));
      if (!body) { ESP_LOGW(TAG, "no memory for %u bytes", (unsigned) room); failed = true; break; }
      data = reinterpret_cast<const uint8_t *>(head.data()) + answer.length;
      size = head.size() - answer.length;
    }
    if (have + size > room) {
      ESP_LOGW(TAG, "%s is larger than the %u allowed", a.path.c_str(), (unsigned) room);
      failed = true;
      break;
    }
    std::memcpy(body + have, data, size);
    have += size;
    if (answer.has_length && have == answer.content_length) { closed = true; break; }
  }
  close(fd);
  roomy::release(chunk);
  if (failed || !answer.complete || (answer.has_length && have != answer.content_length)) {
    if (!failed && answer.complete) ESP_LOGW(TAG, "%s broke off at %u bytes", a.path.c_str(), (unsigned) have);
    if (body) roomy::release(body);
    return;
  }
  result = body;
  result_size = have;
  result_ok = true;
  ESP_LOGI(TAG, "%s: %u bytes in %u ms", a.path.c_str(), (unsigned) have, (unsigned) (esphome::millis() - started));
}

static void task_main(void *) {
  download();
#ifdef USE_ESP32
  const bool in_psram = psram_task::in_psram(task);
#endif
  state.store(DONE, std::memory_order_release);
#ifdef USE_ESP32
  psram_task::finish(in_psram);
#endif
}

static void start_next() {
  if (waiting.empty() || state.load(std::memory_order_acquire) != IDLE) return;
  running = std::move(waiting.front());
  waiting.pop_front();
  result = nullptr;
  result_size = 0;
  result_ok = false;
  started = esphome::millis();
  state.store(LOADING, std::memory_order_release);
#ifdef USE_ESP32
  if (!psram_task::start(task, task_main, "file", STACK_BYTES, nullptr, 1, tskNO_AFFINITY)) {
    ESP_LOGW(TAG, "no task for the download");
    state.store(DONE, std::memory_order_release);  // tick reports the failure
  }
#else
  std::thread(task_main, nullptr).detach();
#endif
}

bool get(const std::string &url, size_t most, Done done) {
  if (!http_get::split(url).ok || most == 0) return false;
  waiting.push_back(Job{url, most, std::move(done)});
  start_next();
  return true;
}

void tick() {
  if (state.load(std::memory_order_acquire) == DONE) {
#ifdef USE_ESP32
    psram_task::reap(task);
#endif
    Job job = std::move(running);
    uint8_t *data = result;
    const size_t size = result_size;
    const bool ok = result_ok;
    result = nullptr;
    state.store(IDLE, std::memory_order_release);
    if (job.done) job.done(ok, ok ? data : nullptr, ok ? size : 0);
    else if (data) roomy::release(data);
  }
  start_next();
}

}  // namespace file_fetch

#else
namespace file_fetch {
bool get(const std::string &, size_t, Done) { return false; }
void tick() {}
}  // namespace file_fetch
#endif
