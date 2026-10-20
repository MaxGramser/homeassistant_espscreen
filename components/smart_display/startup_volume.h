#pragma once
#include <cmath>
#include <string>
namespace startup_volume {
inline bool needs_cap(const std::string &state,float volume,float cap){
  const bool stopped=state=="idle"||state=="off"||state=="standby"||state=="stopped";
  return stopped && (!std::isfinite(volume)||volume>cap);
}
}
