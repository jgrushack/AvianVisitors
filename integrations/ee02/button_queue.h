#pragma once
#include <deque>
#include <string>

// Active HTTP commands live separately so retries keep their event ID.
class ButtonQueue {
 public:
  bool push(const std::string &action) {
    if (pending_.size() >= 64) return false;
    pending_.push_back(action);
    return true;
  }
  bool empty() const { return pending_.empty(); }
  std::string take() {
    if (empty()) return "";
    auto action = pending_.front();
    pending_.pop_front();
    return action;
  }
 private:
  std::deque<std::string> pending_;
};

inline ButtonQueue pending_buttons;
