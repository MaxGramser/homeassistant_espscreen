"""Run the real saver callback/timer lifecycle against a small LVGL timer double.

The render probe covers the complete host; this focused test also closes a saver from its own frame callback.
"""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SaverAnimation(unittest.TestCase):
    def test_timer_lifetime_and_callback_context(self):
        compiler = shlex.split(os.environ['CXX']) if 'CXX' in os.environ else [shutil.which('clang++') or shutil.which('g++')]
        if not compiler[0]:
            self.fail('A C++ compiler is required to check the saver animation lifecycle (set CXX).')
        host = (ROOT / 'components/smart_display/plugin_host.cpp').read_text()
        api = (ROOT / 'components/smart_display/plugin_api.h').read_text()

        def section(text, start, end):
            return text[text.index(start):text.index(end, text.index(start))]

        saver = section(api, 'class Saver :', 'struct SaverType')
        lifecycle = section(host, 'struct OpenSaver :', 'constexpr int SAVER_TOUCH')
        animate = section(host, 'static void saver_animate()', 'bool saver_known(')
        end = section(host, 'static void saver_end() {', '// A tap or a hold on a part the saver made')
        # Exercise the production method bodies, including the new virtual defaults, without building the full UI.
        source = PREFIX + saver + '\n}\n' + lifecycle + animate + '\nstatic void saver_drift() {}\n' + end + MAIN
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'test.cpp').write_text(source)
            binary = path / ('test.exe' if os.name == 'nt' else 'test')
            built = subprocess.run([*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                    '-Wno-unused-parameter', '-Wno-unused-function', str(path / 'test.cpp'),
                                    '-o', str(binary)], capture_output=True, text=True, timeout=180)
            self.assertEqual(built.returncode, 0, (built.stdout + built.stderr)[-8000:])
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)

    def test_animation_starts_after_initial_callbacks(self):
        host = (ROOT / 'components/smart_display/plugin_host.cpp').read_text()
        show = host[host.index('void saver_show('):host.index('void saver_state(')]
        self.assertLess(show.index('saver_feed(true)'), show.index('s.on_tick('))
        self.assertLess(show.index('s.on_tick('), show.index('saver_animate()'))


PREFIX = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#define ESP_LOGI(...) ((void) 0)
struct lv_obj_t {};
struct Place {};
using JsonObjectConst = int;
struct lv_timer_t { void (*callback)(lv_timer_t *); uint32_t period; };
static lv_timer_t *active_timer = nullptr;
static int made = 0, deleted = 0;
static lv_timer_t *lv_timer_create(void (*callback)(lv_timer_t *), uint32_t period, void *) {
  assert(!active_timer);
  ++made;
  return active_timer = new lv_timer_t{callback, period};
}
static void lv_timer_delete(lv_timer_t *timer) {
  assert(timer == active_timer);
  active_timer = nullptr;
  ++deleted;
  delete timer;
}
namespace esphome { static uint32_t now = 0; static uint32_t millis() { return now; } }
namespace theme { static bool dark = false; }
namespace roomy { using Text = std::string; }
namespace rt {
  struct Loader { void release(int) {} };
  static Loader loader;
  static void pictures_collect() {}
  static int minute_of_day() { return 0; }
}
static constexpr int SAVER_OWNER = 2;
static std::vector<Place> outside;
static std::vector<Place> *placing = &outside;
static void place_clear(Place &) {}
namespace tessera {
struct InPsram {};
struct SaverContext {};
enum class SaverStep { OWN };
'''


MAIN = r'''
static int frames = 0, ticks = 0, destroyed = 0;
static uint32_t received = 0;
struct Probe : tessera::Saver {
  uint32_t period;
  bool close_in_frame = false, close_in_interval = false;
  explicit Probe(uint32_t ms) : period(ms) {}
  ~Probe() override { assert(!active_timer); ++destroyed; }
  void show(const tessera::SaverContext &) override {}
  uint32_t frame_interval_ms() const override {
    assert(theme::dark && placing == &saver_open->places);
    if (close_in_interval) saver_hide();
    return period;
  }
  void on_tick(uint32_t) override { ++ticks; }
  void on_frame(uint32_t ms) override {
    assert(theme::dark && placing == &saver_open->places);
    ++frames;
    received = ms;
    if (close_in_frame) {
      int before = destroyed;
      saver_hide();
      assert(destroyed == before);  // deletion waits until this method returns
    }
  }
};
static Probe *open(uint32_t ms) {
  saver_hide();
  saver_open = new OpenSaver();
  auto *probe = new Probe(ms);
  saver_open->saver.reset(probe);
  return probe;
}
static void fire(uint32_t now) {
  esphome::now = now;
  auto callback = active_timer->callback;
  callback(active_timer);  // the callback may delete its own timer
  assert(!theme::dark && placing == &outside && saver_calling == 0);
}
int main() {
  // A legacy saver inherits a disabled interval and needs no timer.
  struct Legacy : tessera::Saver { void show(const tessera::SaverContext &) override {} };
  saver_open = new OpenSaver();
  saver_open->saver = std::make_unique<Legacy>();
  saver_animate();
  assert(!active_timer && made == 0);
  saver_tick(100);
  saver_hide();

  open(0);
  saver_animate();
  assert(!active_timer);
  saver_tick(101);
  assert(ticks == 1);
  saver_hide();

  for (uint32_t requested : {1u, 16u, 33u, 100u}) {
    open(requested);
    saver_animate();
    assert(active_timer && active_timer->period == std::max(16u, requested));
    int before = ticks;
    fire(5000);  // delayed frames carry actual time, not a synthetic frame counter
    assert(received == 5000 && ticks == before);
    fire(UINT32_MAX - 2);
    assert(received == UINT32_MAX - 2);
    fire(3);
    assert(received == 3);  // milliseconds can wrap; no signed narrowing in the host
    saver_tick(102);
    assert(ticks == before + 1);
    saver_hide();
    assert(!active_timer && !saver_open);
  }

  auto *probe = open(33);
  probe->close_in_frame = true;
  saver_animate();
  fire(10);
  assert(!saver_open && !active_timer && !saver_gone);

  // A saver can also leave during interval selection, before any timer exists.
  probe = open(33);
  probe->close_in_interval = true;
  int before = made;
  saver_animate();
  assert(!saver_open && !active_timer && made == before);

  open(33);
  saver_animate();
  open(16);  // replacement stops the old timer before destroying the old saver
  saver_animate();
  fire(20);
  saver_hide();
  saver_hide();  // idempotent, with no double delete
  saver_animate();  // absent saver cannot start a timer
  assert(!active_timer && made == deleted && frames == 14);
}
'''


if __name__ == '__main__':
    unittest.main()
