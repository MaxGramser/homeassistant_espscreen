// The picture loader's bodies (picture_loader.h holds the class and what stays inline). A compilation unit of its own
// because every header of the component compiles into main.cpp, where on the ESP32 and the ESP32-S3 Loader::end (an
// inline function the linker laid out far from its literals) was the first to fall out of an l32r's reach on 2026-11-24
// (docs/RELEASING.md, "The Xtensa literal range"; tools/literal_margin.py measures it). Pure bookkeeping as the header:
// tests/test_picture_loader.cpp and tests/test_pictures_ahead.cpp include this file beside it.
#include "picture_loader.h"

namespace picture_loader {

void Loader::want(const Owner &owner, Want w) {
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
    std::string before = std::move(job->want.key);
    *job = Job{};
    job->owner = keep;
    job->had = std::move(before);
  }
  job->want = std::move(w);
  job->seen = true;
  // A link the owner was given: no question, the download may start.
  if (!job->want.url.empty() && (job->phase == Phase::NEW || job->phase == Phase::ASKED)) {
    job->url = job->want.url;
    job->phase = Phase::LINKED;
  }
}

void Loader::release(const Owner &owner) {
  for (auto it = last_.begin(); it != last_.end(); ++it)
    if (it->first == owner) { if (forget) forget(it->second); last_.erase(it); break; }
  Job *job = find(owner);
  if (!job) return;
  note(*job, "released");
  if (job->phase == Phase::LOADING) stop(*job);
  if (forget && !job->want.key.empty()) forget(job->want.key);
  jobs_.erase(jobs_.begin() + (job - jobs_.data()));
}

void Loader::end(uint32_t now, bool may_load) {
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
  // What was let in ahead already and is on its way (asked, linked or loading): a second picture is let in only beside
  // it, so the app never paints a picture that would be thrown away when it comes.
  size_t coming = 0;
  for (const auto &job : jobs_) if (on_its_way_ahead(job)) coming += job.want.bytes;
  for (auto &job : jobs_) {
    // One fetched ahead asks once nothing on the glass waits: the app's work for it should not hold up theirs. One
    // that would not fit the spare room is not asked for at all: it loads when its page comes back.
    if (job.want.rank == Rank::AHEAD) {
      if (glass_waits) continue;
      const bool counted = on_its_way_ahead(job);
      if (!fits_ahead(job, counted ? coming - job.want.bytes : coming)) continue;
      if (!counted && should_ask(job, now) && !asking(job.want.tag, now, &job)) coming += job.want.bytes;
    }
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
    if (job.want.rank == Rank::AHEAD && (glass_waits || !fits_ahead(job, 0))) continue;  // a page out of sight waits for the glass
    if (should_load(job, now) && (!next || before(job, *next))) next = &job;
  }
  if (!next) return;
  note(*next, next->kept_at ? "refreshes" : "loads", next->url);
  next->phase = Phase::LOADING;
  next->started_at = now ? now : 1;
  if (load) load(next->want.slot, next->url, next->want.key);
}

void Loader::answer(const std::string &tag, const std::string &url, uint32_t now) {
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

std::string Loader::loaded(Slot slot, bool ok, uint32_t now) {
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

void Loader::arrived(const std::string &key, bool unchanged) {
  for (auto &job : jobs_)
    if (job.want.key == key && job.want.done) job.want.done(unchanged ? Outcome::UNCHANGED : Outcome::LOADED);
}

void Loader::remember(const Owner &owner, const std::string &key) {
  if (key.empty()) return;
  for (auto it = last_.begin(); it != last_.end(); ++it) if (it->first == owner) { last_.erase(it); break; }
  if (last_.size() == REMEMBERED) last_.erase(last_.begin());
  last_.emplace_back(owner, key);
}

void Loader::stop(Job &job) {
  if (cancel) cancel(job.want.slot);
  job.phase = job.url.empty() ? Phase::NEW : Phase::LINKED;
  job.started_at = 0;
}

void Loader::settle(Job &job, uint32_t now) {
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

bool Loader::waiting(const Job &job, uint32_t now) const {
  if (job.phase == Phase::DONE || job.phase == Phase::NONE) return false;
  // A picture that refreshes and has one on the glass is not waiting for it.
  if (job.want.every && job.kept_at && now - job.kept_at < job.want.every * 2) return false;
  return true;
}

bool Loader::should_ask(const Job &job, uint32_t now) const {
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

bool Loader::before(const Job &a, const Job &b) {
  if (a.want.rank != b.want.rank) return a.want.rank < b.want.rank;
  if ((a.kept_at == 0) != (b.kept_at == 0)) return a.kept_at == 0;
  return a.kept_at != 0 && a.kept_at < b.kept_at;
}

bool Loader::should_load(const Job &job, uint32_t now) const {
  if (job.phase != Phase::LINKED) return false;
  // A failed load is tried again after the gap; a picture that refreshes keeps its rhythm, after a failure too: a camera
  // tile that found no connection (the screen's sockets all taken by its live streams and the video's viewers) asked
  // again every second and logged every failure (a reTerminal D1001 with five live cameras on a page, 2026-10-25).
  const uint32_t gap = job.failures && job.want.every > camera_view::GAP_MS ? job.want.every : camera_view::GAP_MS;
  if (job.finished_at && now - job.finished_at < gap) return false;
  if (job.want.every && job.kept_at && now - job.kept_at < job.want.every) return false;
  return true;
}

}  // namespace picture_loader
