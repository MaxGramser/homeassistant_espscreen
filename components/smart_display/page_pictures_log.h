#pragma once
// Why a page's picture was not taken or not put just now, as the log's line names it: "[page_pic] none now: <why>"
// (page_pictures_lvgl.h, page_pictures_say).
//
// What it knows: those words, nothing else. They are log words a developer reads, never shown on a screen, so they stay
// English and the translations' lint skips this file by rule (tools/i18n.py leaves out every *_log.h;
// tests/test_log_words.py holds that such a file knows nothing that draws or translates).

namespace page_pictures_log {

constexpr const char *NO_MEMORY = "no PSRAM to spare for another picture";
constexpr const char *PAUSED = "LVGL is paused";
constexpr const char *COVERED = "something over the page";
constexpr const char *STREAMING = "a stream writes the glass";

}  // namespace page_pictures_log
