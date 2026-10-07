#pragma once
// Every picture a screen shows goes one way (firmware 0.52.0): the camera full screen and the screensaver, a media card's
// cover, a media tile's cover (on the glass and fetched ahead for a kept page), each tile's own picture (a camera, a
// cover, a favourite, a map: tile_picture.h), a player's library and an alert's picture. Each of them only says, every
// round, what it wants to see: its owner (who wants it), the picture's key (what it is: another key is another
// picture), the board's download slot it comes through, how much it matters, and how the app is asked for it. The
// loader decides for all of them:
//
// - What the store holds is there. Whether a picture is had is read from the store every round (`kept`), never from a
//   flag an owner keeps, so a picture that went from the store (to make room, a layout that changed) is asked for again
//   at once instead of being waited for until something else changes.
// - One download at a time, in the order of what matters: an alert first, then the full view and the screensaver, a
//   media card, the library, the tiles on the glass, and last what is fetched ahead for a page out of sight. Of equal
//   ones, a picture not yet there goes first, then the one longest on the glass. What is on
//   the glass breaks off a download for a page out of sight; a download nobody wants any more breaks off too. Turning
//   pages fast, opening and closing a card before its picture came, leaves nothing behind: what an owner stops wanting
//   is gone the next round.
// - Asking the app is an event and costs the screen nothing, so a picture on the glass is asked for at once. One fetched
//   ahead waits until nothing on the glass waits.
// - A picture its owner moved on from (another track, a map whose people moved, a page whose covers changed) is
//   forgotten: the store lets it go once nothing draws it. What an owner still holds stays, so a page that comes back
//   shows its pictures at once; picture_store makes room with the one used longest ago when it needs to.
//
// Pure bookkeeping, free of LVGL and ESPHome: tests/test_picture_loader.cpp drives it on a PC, runtime_tiles.h binds it
// to the store, picture_fetch and the app's answers. The rhythm of a picture that refreshes (a camera) and the waits
// before asking again are camera_view's.
#include <algorithm>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
#include "camera_view.h"

namespace picture_loader {
// The board's downloads (picture_fetch): the full view, the alert's frame and the tiles' own pictures.
enum class Slot : uint8_t { FULL, THUMB, LIVE };
// How much a picture matters, the order downloads go in.
enum class Rank : uint8_t { ALERT, VIEW, CARD, LIBRARY, PAGE, AHEAD };
// Who wants a picture: one of each kind, or one per tile.
enum class Kind : uint8_t { ALERT, VIEW, CARD, LIBRARY, TILE };
struct Owner {
  Kind kind = Kind::VIEW;
  uint32_t index = 0;  // the tile's index; 0 where there is one
  bool operator==(const Owner &o) const { return kind == o.kind && index == o.index; }
};
// What came of a picture, for its owner.
enum class Outcome : uint8_t { LOADED, UNCHANGED, FAILED, NONE };
struct Want {
  std::string key;          // what the picture is; the store keeps it under this name
  std::string tag;          // which answer of the app is this picture's link ("cover|media_player.x")
  Slot slot = Slot::FULL;
  Rank rank = Rank::PAGE;
  uint32_t every = 0;       // a picture that refreshes (a camera): the next one this long after the last started; 0: once
  bool drawn = false;       // the app draws it (a map): an answer without a link is a hitch, asked again, later each time
  uint8_t tries = 0;        // downloads that may fail before the picture is given up (an alert's); 0: no end
  std::string url;          // a link the owner has already (the app sends an alert's by itself): nothing to ask
  std::function<void()> ask;                  // asks the app for the link (an event)
  std::function<void(Outcome)> done;          // the picture came (now in the store), did not, or the app has none
};

class Loader {
 public:
  // ---- bound once (runtime_tiles.h) ----
  // Whether the store holds `key`, and since when (millis of the download).
  std::function<bool(const std::string &key, uint32_t &stored_at)> kept;
  // Starts a download of the picture `key` into a slot; breaks one off (it reports nothing).
  std::function<void(Slot, const std::string &url, const std::string &key)> load;
  std::function<void(Slot)> cancel;
  // A picture its owner moved on from: the store may let it go once nothing draws it.
  std::function<void(const std::string &key)> forget;
  // Every step of every picture, for a diagnosis (runtime_tiles.h logs it at DEBUG): who, which picture, what happened.
  std::function<void(const Owner &, const std::string &key, const char *what, const std::string &detail)> log;

  // ---- every round ----
  void begin() { for (auto &j : jobs_) j.seen = false; }
  // An owner says what it wants this round. Another key than its last is another picture: the last is forgotten.
  void want(const Owner &owner, Want w) {
    Job *job = find(owner);
    if (!job) {
      jobs_.push_back(Job{});
      job = &jobs_.back();
      job->owner = owner;
      // An owner back after a while (a card opened again, a page that came back) takes over the key it had: another
      // picture now forgets that one too.
      for (auto it = last_.begin(); it != last_.end(); ++it)
        if (it->first == owner) { job->want.key = it->second; last_.erase(it); break; }
    }
    if (job->want.key != w.key) {
      note(*job, "wants", w.key);
      if (!job->want.key.empty() && forget) forget(job->want.key);
      if (job->phase == Phase::LOADING) stop(*job);
      const Owner keep = job->owner;
      *job = Job{};
      job->owner = keep;
    }
    job->want = std::move(w);
    job->seen = true;
    // A link the owner was given: no question, the download may start.
    if (!job->want.url.empty() && (job->phase == Phase::NEW || job->phase == Phase::ASKED)) {
      job->url = job->want.url;
      job->phase = Phase::LINKED;
    }
  }
  // The owner is done with its picture for good (a camera full screen that closed): it goes, and so does its download.
  void release(const Owner &owner) {
    for (auto it = last_.begin(); it != last_.end(); ++it)
      if (it->first == owner) { if (forget) forget(it->second); last_.erase(it); break; }
    Job *job = find(owner);
    if (!job) return;
    note(*job, "released");
    if (job->phase == Phase::LOADING) stop(*job);
    if (forget && !job->want.key.empty()) forget(job->want.key);
    jobs_.erase(jobs_.begin() + (job - jobs_.data()));
  }
  // After every owner had its say: what nobody wants goes, what is missing is asked for, and the next download starts
  // when `may_load` (no finger on the glass, the pages standing still) and nothing is on its way.
  void end(uint32_t now, bool may_load) {
    for (size_t i = 0; i < jobs_.size();) {
      if (jobs_[i].seen) { ++i; continue; }
      // Not wanted this round: its download breaks off; the picture stays in the store for when it is wanted again, and
      // the owner's key is remembered, so a picture it moves on to later lets this one go.
      if (jobs_[i].phase == Phase::LOADING) stop(jobs_[i]);
      note(jobs_[i], "not wanted now");
      remember(jobs_[i].owner, jobs_[i].want.key);
      jobs_.erase(jobs_.begin() + i);
    }
    for (auto &job : jobs_) settle(job, now);
    // A picture the store held already: its owner is told once, the same way as after a download.
    for (auto &job : jobs_)
      if (job.phase == Phase::DONE && !job.told) { job.told = true; if (job.want.done) job.want.done(Outcome::UNCHANGED); }
    const bool glass_waits = glass_waiting(now);
    for (auto &job : jobs_) {
      // One fetched ahead asks once nothing on the glass waits: the app's work for it should not hold up theirs.
      if (job.want.rank == Rank::AHEAD && glass_waits) continue;
      // One question of a kind at a time: the app's answer names the player, not the size, so a card's cover and a
      // tile's cover of the same player would take each other's links.
      if (asking(job.want.tag, now, &job)) continue;
      if (should_ask(job, now)) {
        note(job, job.phase == Phase::NEW ? "asks" : "asks again");
        job.phase = Phase::ASKED;
        job.asked_at = now ? now : 1;
        if (job.want.ask) job.want.ask();
      }
    }
    // What is on the glass breaks off a download for a page out of sight.
    if (Job *active = loading()) {
      if (active->want.rank == Rank::AHEAD && glass_waits) { note(*active, "breaks off for the glass"); stop(*active); }
      else return;
    }
    if (!may_load) return;
    Job *next = nullptr;
    for (auto &job : jobs_) {
      if (job.want.rank == Rank::AHEAD && glass_waits) continue;  // a page out of sight waits for the glass
      if (should_load(job, now) && (!next || before(job, *next))) next = &job;
    }
    if (!next) return;
    note(*next, next->kept_at ? "refreshes" : "loads", next->url);
    next->phase = Phase::LOADING;
    next->started_at = now ? now : 1;
    if (load) load(next->want.slot, next->url, next->want.key);
  }

  // ---- the app and the downloads ----
  // The app's answer for `tag`: a link, or "" when it has no picture.
  void answer(const std::string &tag, const std::string &url, uint32_t now) {
    for (auto &job : jobs_) {
      if (job.want.tag != tag || job.phase != Phase::ASKED) continue;
      job.url = url;
      job.failures = 0;
      note(job, url.empty() ? "answered: none" : "answered", url);
      if (url.empty()) {
        job.phase = Phase::NONE;
        job.none_at = now ? now : 1;
        if (job.empties < 255) ++job.empties;
        if (job.want.done) job.want.done(Outcome::NONE);
      } else {
        job.phase = Phase::LINKED;
        job.empties = 0;
      }
    }
  }
  // A download into `slot` ended. Returns the key it was for ("" when nobody wants it any more): the caller puts the
  // picture into the store under it, then calls arrived() so its owner shows it.
  std::string loaded(Slot slot, bool ok, uint32_t now) {
    Job *job = loading();
    if (!job || job->want.slot != slot) return {};
    job->finished_at = now ? now : 1;
    note(*job, ok ? "loaded" : "load failed");
    if (ok) {
      job->phase = Phase::DONE;
      job->failures = 0;
      job->told = true;
      return job->want.key;
    }
    // Tried again after the gap; a link that fails this often is old, and a new one is asked for. A picture with a number
    // of tries is given up after them.
    ++job->attempts;
    if (job->want.tries && job->attempts >= job->want.tries) {
      job->phase = Phase::NONE;
      job->none_at = now ? now : 1;
    } else {
      job->phase = ++job->failures >= camera_view::MAX_FAILURES && job->want.url.empty() ? Phase::NEW : Phase::LINKED;
      if (job->phase == Phase::NEW) { job->url.clear(); job->failures = 0; }
    }
    if (job->want.done) job->want.done(Outcome::FAILED);
    return {};
  }
  // The picture is in the store (or, without one, in the slot): its owner shows it.
  void arrived(const std::string &key, bool unchanged) {
    for (auto &job : jobs_)
      if (job.want.key == key && job.want.done) job.want.done(unchanged ? Outcome::UNCHANGED : Outcome::LOADED);
  }

  // ---- what owners read ----
  // Whether the owner's picture had its first try (here, failed or none): a spinner stops, a title starts to roll.
  bool settled_for(const Owner &owner) const {
    const Job *job = find(owner);
    return !job || job->phase == Phase::DONE || job->phase == Phase::NONE || job->finished_at != 0;
  }
  // Whether something on the glass still waits for its picture.
  bool glass_waiting(uint32_t now) const {
    return std::any_of(jobs_.begin(), jobs_.end(), [&](const Job &j) { return j.want.rank != Rank::AHEAD && waiting(j, now); });
  }
  // Whether the owner said what it wants (this round or before, and has not moved on).
  bool has(const Owner &owner) const { return find(owner) != nullptr; }
  // Whether the owner's picture is on its way right now.
  bool loading_for(const Owner &owner) const { const Job *job = find(owner); return job && job->phase == Phase::LOADING; }
  // Whether a download runs in this slot (its buffer is not to be freed under it).
  bool slot_busy(Slot slot) const {
    return std::any_of(jobs_.begin(), jobs_.end(), [&](const Job &j) { return j.phase == Phase::LOADING && j.want.slot == slot; });
  }
  bool busy() const { return std::any_of(jobs_.begin(), jobs_.end(), [](const Job &j) { return j.phase == Phase::LOADING; }); }
  size_t size() const { return jobs_.size(); }
  // For the tests and the log.
  enum class Phase : uint8_t { NEW, ASKED, NONE, LINKED, LOADING, DONE };
  Phase phase(const Owner &owner) const { const Job *job = find(owner); return job ? job->phase : Phase::NEW; }

 private:
  struct Job {
    Owner owner;
    Want want;
    Phase phase = Phase::NEW;
    std::string url;
    uint32_t asked_at = 0, none_at = 0, started_at = 0, finished_at = 0;
    uint32_t kept_at = 0;  // when the store's copy was made (a picture that refreshes waits for its turn from there)
    uint8_t failures = 0, empties = 0, attempts = 0;
    bool seen = false;
    bool told = false;   // the owner heard that its picture is here
  };
  std::vector<Job> jobs_;
  // The last key of owners that want nothing right now, the oldest first; a few dozen at most.
  static constexpr size_t REMEMBERED = 32;
  std::vector<std::pair<Owner, std::string>> last_;
  void remember(const Owner &owner, const std::string &key) {
    if (key.empty()) return;
    for (auto it = last_.begin(); it != last_.end(); ++it) if (it->first == owner) { last_.erase(it); break; }
    if (last_.size() == REMEMBERED) last_.erase(last_.begin());
    last_.emplace_back(owner, key);
  }

  Job *find(const Owner &owner) {
    for (auto &j : jobs_) if (j.owner == owner) return &j;
    return nullptr;
  }
  const Job *find(const Owner &owner) const {
    for (auto &j : jobs_) if (j.owner == owner) return &j;
    return nullptr;
  }
  Job *loading() {
    for (auto &j : jobs_) if (j.phase == Phase::LOADING) return &j;
    return nullptr;
  }
  // Whether another than `self` waits for an answer of this kind (and not for longer than an answer takes).
  bool asking(const std::string &tag, uint32_t now, const Job *self) const {
    return std::any_of(jobs_.begin(), jobs_.end(), [&](const Job &j) {
      return &j != self && j.want.tag == tag && j.phase == Phase::ASKED && now - j.asked_at < camera_view::ASK_AGAIN_MS;
    });
  }
  void note(const Job &job, const char *what, const std::string &detail = {}) const {
    if (log) log(job.owner, job.want.key, what, detail);
  }
  void stop(Job &job) {
    if (cancel) cancel(job.want.slot);
    job.phase = job.url.empty() ? Phase::NEW : Phase::LINKED;
    job.started_at = 0;
  }
  // What the store says, every round: a picture it holds is here, one it lost is asked for again.
  void settle(Job &job, uint32_t now) {
    if (job.phase == Phase::LOADING) return;
    uint32_t at = 0;
    const bool held = kept && kept(job.want.key, at);
    if (held) {
      job.kept_at = at;
      // Once is enough for a picture that does not refresh; one that does is fresh until its turn comes again.
      if (!job.want.every || now - at < job.want.every) {
        if (job.phase != Phase::DONE) job.told = false;
        job.phase = Phase::DONE;
        return;
      }
      if (job.phase == Phase::DONE) job.phase = job.url.empty() ? Phase::NEW : Phase::LINKED;
      return;
    }
    // Not held (any more): a picture that came is fetched again, through its link while that is good.
    if (job.phase == Phase::DONE) job.phase = job.url.empty() ? Phase::NEW : Phase::LINKED;
  }
  bool waiting(const Job &job, uint32_t now) const {
    if (job.phase == Phase::DONE || job.phase == Phase::NONE) return false;
    // A picture that refreshes and has one on the glass is not waiting for it.
    if (job.want.every && job.kept_at && now - job.kept_at < job.want.every * 2) return false;
    return true;
  }
  bool should_ask(const Job &job, uint32_t now) const {
    switch (job.phase) {
      case Phase::NEW: return true;
      // An answer that did not come is asked for again.
      case Phase::ASKED: return now - job.asked_at >= camera_view::ASK_AGAIN_MS;
      case Phase::NONE: {
        // The app has none: a cover stays without one until it is another picture; a map or a camera asks again. One
        // given up after its tries stays given up.
        if (job.want.tries && job.attempts >= job.want.tries) return false;
        if (!job.want.drawn && !job.want.every) return false;
        uint32_t wait = camera_view::ASK_AGAIN_MS;
        for (uint8_t n = 1; n < job.empties && wait < camera_view::ASK_AGAIN_MAX_MS; ++n) wait *= 2;
        if (job.want.every > wait) wait = job.want.every;
        return now - job.none_at >= std::min(wait, camera_view::ASK_AGAIN_MAX_MS);
      }
      default: return false;
    }
  }
  // Which of two pictures ready to load goes first: the one that matters more; of equal ones (the pictures of a page's
  // tiles), one that has no picture yet before a refresh, then the oldest picture, so cameras at the same pace take
  // turns. Otherwise the order in which their owners asked.
  static bool before(const Job &a, const Job &b) {
    if (a.want.rank != b.want.rank) return a.want.rank < b.want.rank;
    if ((a.kept_at == 0) != (b.kept_at == 0)) return a.kept_at == 0;
    return a.kept_at != 0 && a.kept_at < b.kept_at;
  }
  bool should_load(const Job &job, uint32_t now) const {
    if (job.phase != Phase::LINKED) return false;
    // A failed load is tried again after the gap; a picture that refreshes keeps its rhythm.
    if (job.finished_at && now - job.finished_at < camera_view::GAP_MS) return false;
    if (job.want.every && job.kept_at && now - job.kept_at < job.want.every) return false;
    return true;
  }
};
}  // namespace picture_loader
