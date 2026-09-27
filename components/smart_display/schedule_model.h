#pragma once
// Interval geometry is independent of heating, LVGL and Home Assistant.
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace schedule_model {
constexpr int DAY = 1440, STEP = 5, MAX_SLOTS = 16, MAX_PROGRAMMES = 7;
template<class Value> struct Slot {
  std::string id;
  int start = 0, end = DAY;
  Value value{};
  bool operator==(const Slot &s) const { return id == s.id && start == s.start && end == s.end && value == s.value; }
};
template<class Value> struct Programme {
  std::string id, name;
  unsigned days = 0;
  bool enabled = true;
  std::vector<Slot<Value>> slots;
  bool operator==(const Programme &p) const { return id == p.id && name == p.name && days == p.days && enabled == p.enabled && slots == p.slots; }
};
template<class Value> bool valid(const Programme<Value> &p) {
  if (p.id.empty() || p.name.empty() || !p.days || p.days > 127 || p.slots.empty() || p.slots.size() > MAX_SLOTS) return false;
  int end = 0;
  std::vector<std::string> ids;
  for (const auto &s : p.slots) {
    if (s.id.empty() || std::find(ids.begin(), ids.end(), s.id) != ids.end() || s.start != end ||
        s.start % STEP || s.end % STEP || s.end - s.start < STEP || s.end > DAY) return false;
    ids.push_back(s.id); end = s.end;
  }
  return end == DAY;
}
template<class Value> bool split(Programme<Value> &p, unsigned index, const std::string &id) {
  if (index >= p.slots.size() || p.slots.size() >= MAX_SLOTS || id.empty()) return false;
  for (const auto &s : p.slots) if (s.id == id) return false;
  auto &s = p.slots[index];
  int at = ((s.start + s.end) / (2 * STEP)) * STEP;
  if (at <= s.start || at >= s.end) return false;
  auto next = s; next.id = id; next.start = at; s.end = at;
  p.slots.insert(p.slots.begin() + index + 1, next);
  return true;
}
template<class Value> bool merge(Programme<Value> &p, unsigned index) {
  if (p.slots.size() < 2 || index >= p.slots.size()) return false;
  if (index) p.slots[index - 1].end = p.slots[index].end;
  else p.slots[1].start = 0;
  p.slots.erase(p.slots.begin() + index);
  return true;
}
template<class Value> bool boundary(Programme<Value> &p, unsigned index, int minute) {
  if (index == 0 || index >= p.slots.size()) return false;
  minute = std::clamp(((minute + STEP / 2) / STEP) * STEP,
                      p.slots[index - 1].start + STEP, p.slots[index].end - STEP);
  p.slots[index - 1].end = p.slots[index].start = minute;
  return true;
}
struct Heat {
  bool off = true;
  float temperature = 0;
  bool operator==(const Heat &v) const { return off == v.off && (off || std::fabs(temperature - v.temperature) < .00001f); }
};
struct Heating {
  float minimum = 5, maximum = 30, step = .5;
  int positions() const { return 1 + int(std::lround((maximum - minimum) / step)); }
  Heat value(int position) const { return position <= 0 ? Heat{} : Heat{false, minimum + (std::min(position, positions()) - 1) * step}; }
  int position(const Heat &v) const { return v.off ? 0 : 1 + int(std::lround((v.temperature - minimum) / step)); }
  bool valid(const Heat &v) const { return v.off || (std::isfinite(v.temperature) && v.temperature >= minimum && v.temperature <= maximum && value(position(v)) == v); }
};
// Reusable draft lifecycle. Failed/uncertain writes retain the draft and require
// a reload; transport delivery by itself is never persistence confirmation.
struct Lifecycle {
  bool dirty = false, pending = false, uncertain = false, leave_after_save = false;
  bool can_save(bool valid) const { return dirty && valid && !pending && !uncertain; }
  bool needs_guard() const { return dirty || pending; }
  void confirmed() { dirty = pending = uncertain = false; }
};
}  // namespace schedule_model
