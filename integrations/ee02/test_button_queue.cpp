#include "button_queue.h"
#include <cassert>
int main() {
  ButtonQueue q;
  assert(q.take().empty());
  q.push("mode");
  auto active = q.take();
  q.push("next"); q.push("previous"); q.push("mode");
  // An active command and its retries cannot be overwritten by later presses.
  assert(active == "mode");
  assert(q.take() == "next");
  assert(q.take() == "previous");
  assert(q.take() == "mode");
  assert(q.empty());
  for (int i=0; i<64; ++i) assert(q.push(std::to_string(i)));
  assert(!q.push("overflow"));
  for (int i=0; i<64; ++i) assert(q.take() == std::to_string(i));
  assert(q.empty());
}
