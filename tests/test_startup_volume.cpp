#include "../components/smart_display/startup_volume.h"
#include <cassert>
#include <limits>
int main(){
  using startup_volume::needs_cap;
  assert(needs_cap("idle",0.8f,0.3f));assert(needs_cap("stopped",0.8f,0.3f));
  assert(needs_cap("off",std::numeric_limits<float>::quiet_NaN(),0.3f));
  assert(!needs_cap("playing",0.8f,0.3f));assert(!needs_cap("paused",0.8f,0.3f));
  assert(!needs_cap("idle",0.2f,0.3f));assert(!needs_cap("idle",0.3f,0.3f));
  assert(!needs_cap("unavailable",0.8f,0.3f));
}
