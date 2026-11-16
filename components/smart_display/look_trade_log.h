#pragma once
// The steps of the host build's check of a card's style trade (look_trade.h, `checked`), as its log line names them:
// "restyle check FAIL: <step>, card ...". tools/render/run.py fails a render on that line.
//
// What it knows: the three steps' words, nothing else. They are log words a developer reads, never shown on a screen,
// so they stay English and the translations' lint skips this file by rule (tools/i18n.py leaves out every *_log.h;
// tests/test_log_words.py holds that such a file knows nothing that draws or translates).

namespace look_trade_log {

constexpr const char *TRADED = "traded";
constexpr const char *TRADED_BACK = "traded back";
constexpr const char *TRADED_AGAIN = "traded again";

}  // namespace look_trade_log
