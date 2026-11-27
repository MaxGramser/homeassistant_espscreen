#include "../components/smart_display/card_orientation.h"
#include <cassert>

int main() {
  using card_orientation::Choice;
  using card_orientation::stacked;

  // The automatic choice retains the existing twice-the-cell-height threshold.
  assert(!stacked(Choice::automatic, 103, 52));
  assert(stacked(Choice::automatic, 104, 52));
  assert(stacked(Choice::automatic, 105, 52));
  // An explicit choice is independent of that threshold.
  assert(stacked(Choice::vertical, 80, 52));
  assert(!stacked(Choice::vertical, 40, 52, false));
  assert(!stacked(Choice::horizontal, 150, 52));
}
