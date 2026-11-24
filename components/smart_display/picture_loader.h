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
// The class here, its larger bodies in picture_loader.cpp (a compilation unit of its own: docs/RELEASING.md, "The Xtensa
// literal range"). Pure bookkeeping, free of LVGL and ESPHome: tests/test_picture_loader.cpp drives it on a PC, runtime_tiles.h binds it
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
  size_t bytes = 0;         // what the picture takes in the store (picture_store::bytes_of), for one fetched ahead
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
  // Whether a picture of `bytes` fetched ahead for a page out of sight fits the store's spare room now, beside `coming`:
  // the pictures fetched ahead that were let in already and are not in the store yet (picture_store::Store::fits_ahead,
  // GitHub #415). Unbound: every one does.
  std::function<bool(size_t bytes, size_t coming)> room_ahead;
  // Every step of every picture, for a diagnosis (runtime_tiles.h logs it at DEBUG): who, which picture, what happened.
  std::function<void(const Owner &, const std::string &key, const char *what, const std::string &detail)> log;

  // ---- every round ----
  void begin() { for (auto &j : jobs_) j.seen = false; }
  // An owner says what it wants this round. Another key than its last is another picture: the last is forgotten.
  void want(const Owner &owner, Want w);
  // The owner is done with its picture for good (a camera full screen that closed): it goes, and so does its download.
  void release(const Owner &owner);
  // After every owner had its say: what nobody wants goes, what is missing is asked for, and the next download starts
  // when `may_load` (no finger on the glass, the pages standing still) and nothing is on its way.
  void end(uint32_t now, bool may_load);

  // ---- the app and the downloads ----
  // The app's answer for `tag`: a link, or "" when it has no picture.
  void answer(const std::string &tag, const std::string &url, uint32_t now);
  // A download into `slot` ended. Returns the key it was for ("" when nobody wants it any more): the caller puts the
  // picture into the store under it, then calls arrived() so its owner shows it.
  std::string loaded(Slot slot, bool ok, uint32_t now);
  // The picture is in the store (or, without one, in the slot): its owner shows it.
  void arrived(const std::string &key, bool unchanged);

  // How much the download in `slot` matters (Rank::PAGE when none runs): one fetched ahead that arrives when the room it
  // fitted is gone is not kept (picture_rounds_lvgl.h picture_done, GitHub #415).
  Rank loading_rank(Slot slot) const {
    for (const auto &j : jobs_) if (j.phase == Phase::LOADING && j.want.slot == slot) return j.want.rank;
    return Rank::PAGE;
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
  // Whether a download runs in this slot (its buffer is not to be freed under it).
  bool slot_busy(Slot slot) const {
    return std::any_of(jobs_.begin(), jobs_.end(), [&](const Job &j) { return j.phase == Phase::LOADING && j.want.slot == slot; });
  }
  bool busy() const { return std::any_of(jobs_.begin(), jobs_.end(), [](const Job &j) { return j.phase == Phase::LOADING; }); }
  // The key of the picture loading into `slot`, "" when none does (before loaded() says how it went).
  std::string loading_key(Slot slot) const {
    for (const auto &j : jobs_) if (j.phase == Phase::LOADING && j.want.slot == slot) return j.want.key;
    return {};
  }
  // The key the owner of the download into `slot` wanted before this one (its picture may still be on the glass), or "".
  // Its ETag goes with the new link, so the same bytes under another key come back 304 (runtime_tiles.h).
  std::string loading_had(Slot slot) const {
    for (const auto &j : jobs_) if (j.phase == Phase::LOADING && j.want.slot == slot) return j.had;
    return {};
  }
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
    std::string had;  // the key wanted before this one
    uint32_t asked_at = 0, none_at = 0, started_at = 0, finished_at = 0;
    uint32_t kept_at = 0;  // when the store's copy was made (a picture that refreshes waits for its turn from there)
    uint8_t failures = 0, empties = 0, attempts = 0;
    bool seen = false;
    bool told = false;   // the owner heard that its picture is here
  };
  std::vector<Job> jobs_;
  bool fits_ahead(const Job &job, size_t coming) const { return !room_ahead || room_ahead(job.want.bytes, coming); }
  bool on_its_way_ahead(const Job &job) const {
    return job.want.rank == Rank::AHEAD && (job.phase == Phase::ASKED || job.phase == Phase::LINKED || job.phase == Phase::LOADING);
  }
  // The last key of owners that want nothing right now, the oldest first; a few dozen at most.
  static constexpr size_t REMEMBERED = 32;
  std::vector<std::pair<Owner, std::string>> last_;
  void remember(const Owner &owner, const std::string &key);

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
  void stop(Job &job);
  // What the store says, every round: a picture it holds is here, one it lost is asked for again.
  void settle(Job &job, uint32_t now);
  bool waiting(const Job &job, uint32_t now) const;
  bool should_ask(const Job &job, uint32_t now) const;
  // Which of two pictures ready to load goes first: the one that matters more; of equal ones (the pictures of a page's
  // tiles), one that has no picture yet before a refresh, then the oldest picture, so cameras at the same pace take
  // turns. Otherwise the order in which their owners asked.
  static bool before(const Job &a, const Job &b);
  bool should_load(const Job &job, uint32_t now) const;
};
}  // namespace picture_loader
