// Protocol parsing: what ESP Screens sends a screen, read into the model (runtime_tiles.h declares receive()).
//
// Compiled on its own, not inline in main.cpp (firmware 0.3.3+). On Xtensa (the ESP32 and the ESP32-S3) ESP-IDF puts
// the literal pool of an object file in front of all of that file's code, and an l32r instruction reaches at most
// 256 KB back to its literal. Every header of this component lands in main.cpp, and with the 0.3.8 features its code
// grew past that range: the S3 boards failed to link with "dangerous relocation: l32r: literal target out of range",
// in this very function, and the CYD was 1.5 KB from the same error. Its own file gives it its own literal pool and
// takes some 30 KB out of main.cpp. docs/RELEASING.md tells how to recognise the limit.
#include "esphome/core/log.h"
#include "runtime_tiles.h"
namespace runtime_tiles {
static bool parse_bar_item(JsonVariant value, header_bar::Item &item) {
    if (!value.is<JsonObject>()) return false;
    item.kind = header_bar::kind(string(value["k"], 8));
    if (item.kind == header_bar::Kind::none) return false;
    uint32_t icon = tile_icon::codepoint(string(value["i"], 8));
    item.icon = icon && has_icon_glyph(icon) ? icon : 0;
    item.text = string(value["t"], header_bar::TEXT_BYTES);
    item.epoch = value["e"].is<unsigned>() ? value["e"].as<uint32_t>() : 0;
    item.has_color = header_bar::color(string(value["c"], 8), item.color);
    if (item.kind == header_bar::Kind::ago && item.epoch == 0) return false;
    return true;
}
static bool parse_bar(JsonVariant items, header_bar::Bar &out) {
  if (!items.is<JsonArray>() || items.as<JsonArray>().size() > header_bar::MAX_ITEMS) return false;
  for (JsonVariant value : items.as<JsonArray>()) {
    header_bar::Item item;
    if (!parse_bar_item(value, item)) return false;
    out.items[out.count++] = std::move(item);
  }
  out.received = true;
  return true;
}
// Reading what Home Assistant sent. Every loop here walks a JsonArray that ArduinoJson hands back from the
// document, and GCC 14 cannot tell that apart from a reference into the temporary the call was made on:
// `for (JsonVariant v : root["slots"].as<JsonArray>())` raises -Wdangling-reference, eighteen times in this
// one function. The array is a handle into the document, which outlives the loop by a long way, so the
// warning is wrong here - and turning it off for this function only keeps it working everywhere else, where
// the same warning would be worth reading. Naming each array instead would mean moving braces through the
// parser of the layout protocol, which is not a trade this is worth.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdangling-reference"
std::string receive(const std::string &payload) {
  if (!enabled) return "Use the Easy Setup profile";
  if (payload.size() > 4096) return "Error: message too large";
  std::string result = "Error: invalid message";
  Fingerprint packet_hash;
  packet_hash.add(payload);
  uint32_t packet_sequence = 0;
  bool sequenced = false;
  const bool accepted = esphome::json::parse_json(payload, [&](JsonObject root) -> bool {
    if (root["v"].as<int>() != page_protocol::VERSION) {
      const auto problem = root["v"].is<unsigned>() && root["v"].as<unsigned>() == 1 ? ProtocolProblem::old_addon : ProtocolProblem::unsupported;
      if (protocol_problem != problem) { protocol_problem = problem; cancel_layout_input(false); refresh_all(); }
      result = problem == ProtocolProblem::old_addon ? "Configuration problem. Update add-on." : "Error: protocol version";
      return false;
    }
    auto op = string(root["op"]);
#ifdef SWIPE_PROFILE
    // Diagnostic builds only, and outside the add-on's session so a bench script can send them (docs/SWIPE_PROFILE.md).
    if (op == "swipe_test") {
      // Page switches without a finger, `n` of them `ms` apart; `back` (ms) swipes straight back after each one, like a
      // quick second swipe.
      swipe_test(root["n"] | 20u, root["ms"] | 1200u, root["back"] | 0u);
      result = "Swipe test started";
      return true;
    }
    if (op == "heap_walk") {
      // How long one walk of each heap holds its lock, the time the panel's bounce-buffer interrupt waits on that core.
#ifdef USE_ESP32
      for (const uint32_t caps : {(uint32_t) MALLOC_CAP_INTERNAL, (uint32_t) MALLOC_CAP_SPIRAM}) {
        multi_heap_info_t info;
        const int64_t start = esp_timer_get_time();
        heap_caps_get_info(&info, caps);
        const int64_t took = esp_timer_get_time() - start;
        ESP_LOGI("swipe_prof", "heap walk %s: %lld us, %u blocks (%u free), largest %u", caps == MALLOC_CAP_SPIRAM ? "psram" : "internal",
                 (long long) took, (unsigned) (info.allocated_blocks + info.free_blocks), (unsigned) info.free_blocks,
                 (unsigned) info.largest_free_block);
      }
#endif
      result = "Heap walked";
      return true;
    }
    if (op == "kept_pages") {
      // At most `n` pages kept beside the one on the glass (kept_pages.h), -1 for as many as fit: the A/B of that round.
      kept_limit = root["n"] | -1;
      forget_kept();
      ESP_LOGI("swipe_prof", "kept pages: %d", kept_limit);
      result = "Kept pages set";
      return true;
    }
#endif
    if (op == "hello") {
      uint64_t request;
      if (!page_protocol::key(string(root["request"]), request)) return false;
      const uint64_t random = (uint64_t{esphome::random_uint32()} << 32) | esphome::random_uint32();
      result = "Session:" + protocol_key(transfer.grant(request, random));
      return true;
    }
    uint64_t lease, revision;
    if (!page_protocol::key(string(root["session"]), lease) ||
        !page_protocol::key(string(root["rev"]), revision) || !root["seq"].is<unsigned>()) return false;
    packet_sequence = root["seq"].as<unsigned>();
    const auto packet = transfer.packet(lease, packet_sequence, packet_hash.value);
    if (packet == page_protocol::Packet::reject) { result = "Error: obsolete message"; return false; }
    if (packet == page_protocol::Packet::duplicate) {
      result = transfer.active && model.ready() ? "Synced" : "Loading tiles";
      return true;
    }
    sequenced = true;
    if (op == "begin") {
      if (!root["tiles"].is<unsigned>() || !root["pages"].is<unsigned>() || !root["home"].is<unsigned>() ||
          !root["title"].is<const char *>() || root["title"].as<std::string>().size() > 96 ||
          root["pages"].as<unsigned>() == 0 || root["pages"].as<unsigned>() > grid.pages() ||
          root["tiles"].as<unsigned>() > grid.max_tiles() || root["home"].as<unsigned>() >= root["pages"].as<unsigned>() ||
          !root["keepalive"].is<unsigned>() || root["keepalive"].as<unsigned>() < 5 || root["keepalive"].as<unsigned>() > 3600)
        return false;
      const bool was_active = transfer.active && model.ready();
      auto candidate = transfer;
      const auto begin = candidate.begin(revision, root["pages"].as<unsigned>(), root["tiles"].as<unsigned>());
      if (begin == page_protocol::Begin::reject) return false;
      const bool was_problem = protocol_problem != ProtocolProblem::none;
      if (begin == page_protocol::Begin::unchanged) {
        transfer = candidate;
        protocol_problem = ProtocolProblem::none;
        last_received = esphome::millis();
        keepalive_seconds = root["keepalive"].as<unsigned>();
        if (was_problem) refresh_all();
        result = "Synced"; return true;
      }
      if (was_active && shown_page && *shown_page >= 0 && static_cast<size_t>(*shown_page) < model.page_data.records.size()) {
        previous_page_id = model.page_data.records[*shown_page].id;
        had_previous_page = true;
      }
      if (!model.begin(root["tiles"].as<unsigned>(), root["pages"].as<unsigned>(), string(root["title"], 96), [] { cancel_layout_input(); })) {
        refresh_all(); result = model.refusal.empty() ? "Error: layout" : model.refusal; return false;
      }
      transfer = candidate;
      protocol_problem = ProtocolProblem::none;
      last_received = esphome::millis();
      keepalive_seconds = root["keepalive"].as<unsigned>();
      model.page_data.home = root["home"].as<unsigned>();
      inbox = string(root["inbox"], 160);
      layout_rev = protocol_key(revision);
      if (root["clock_24h"].is<bool>()) settings_screen::set("clock_24h", root["clock_24h"].as<bool>() ? 1 : 0);
      uint32_t numbers = screen_text_numbers();
      const int style = root["numbers"].is<const char *>() ? screen_text::number_style_of(root["numbers"].as<std::string>()) : -1;
      if (style >= 0) numbers = (numbers & ~0xFu) | static_cast<unsigned>(style);
      if (root["group_min"].is<unsigned>() && root["group_min"].as<unsigned>() >= 1 && root["group_min"].as<unsigned>() <= 2)
        numbers = (numbers & ~0x30u) | (root["group_min"].as<unsigned>() << 4);
      if (root["percent_space"].is<bool>()) numbers = (numbers & ~0xC0u) | ((root["percent_space"].as<bool>() ? 2u : 1u) << 6);
      if (numbers != screen_text_numbers()) { screen_text_numbers(numbers); numbers_preference.save(&numbers); }
      refresh_all();
      result = "Loading tiles";
      return true;
    }
    if (op == "appearance") {
      uint64_t base;
      if (!transfer.active || !model.ready() || !page_protocol::key(string(root["base"]), base) ||
          !transfer.matches(base) || !root["title"].is<const char *>() ||
          root["title"].as<std::string>().size() > 96 || !root["pages"].is<JsonArray>() || !root["tiles"].is<JsonArray>()) return false;
      const auto pages = root["pages"].as<JsonArray>(), tiles = root["tiles"].as<JsonArray>();
      if (pages.size() > page_protocol::MAX_PAGES || tiles.size() > page_protocol::MAX_TILES) return false;
      uint64_t seen_tiles = 0;
      unsigned seen_pages = 0;
      // Validate the complete bounded edit before touching the sole live model.
      // The JSON document is the staging area, not a second set of tile records.
      for (JsonVariant item : pages) {
        if (!item.is<JsonObject>() || !item["p"].is<unsigned>() || !item["title"].is<const char *>()) return false;
        const unsigned page = item["p"].as<unsigned>();
        if (page >= model.page_data.records.size() || (seen_pages & (1u << page)) ||
            item["title"].as<std::string>().size() > 96) return false;
        seen_pages |= 1u << page;
      }
      for (JsonVariant item : tiles) {
        if (!item.is<JsonObject>() || !item["i"].is<unsigned>() || !item["name"].is<const char *>() ||
            !item["background"].is<const char *>()) return false;
        const unsigned index = item["i"].as<unsigned>();
        if (index >= model.count || (seen_tiles & (uint64_t{1} << index)) ||
            item["name"].as<std::string>().size() > 80 || item["background"].as<std::string>().size() > 16) return false;
        seen_tiles |= uint64_t{1} << index;
      }
      const std::string title = string(root["title"], 96);
      model.title = title.empty() ? tr(txt::status_home) : title;
      for (JsonVariant item : pages) model.page_data.records[item["p"].as<unsigned>()].title = string(item["title"], 96);
      transfer.revision = revision;
      layout_rev = protocol_key(revision);
      for (JsonVariant item : tiles) {
        const unsigned index = item["i"].as<unsigned>();
        auto &tile = model.tiles[index];
        tile.name = string(item["name"], 80);
        const std::string background = string(item["background"], 16);
        tile.background = tile_palette::color(background);
        tile.transparent = tile_palette::transparent(background);
        refresh_tile(index);
        if (active_index == static_cast<int>(index) && detail_update) detail_update(tile);
        refresh_detail(index);
      }
      last_received = esphome::millis();
      refresh_header_only();
      result = "Synced";
      return true;
    }
    if (!transfer.matches(revision)) { result = "Resend needed"; return false; }
    if (op == "ping") {
      last_received = esphome::millis();
      result = transfer.active && model.ready() ? "Synced" : "Resend needed";
      return true;
    }
    if (op == "bar_value") {
      if (!transfer.active || !root["targets"].is<JsonArray>()) return false;
      const auto targets = root["targets"].as<JsonArray>();
      if (targets.size() == 0 || targets.size() > page_protocol::MAX_PAGES * header_bar::MAX_ITEMS) return false;
      header_bar::Item item;
      if (!parse_bar_item(root["item"], item)) return false;
      uint64_t seen = 0;
      // Validate every destination before changing any page. No staging copy
      // of the page bars or additional persistent firmware storage is needed.
      for (JsonVariant value : targets) {
        if (!value.is<unsigned>()) return false;
        const unsigned target = value.as<unsigned>();
        const unsigned page = target / header_bar::MAX_ITEMS, index = target % header_bar::MAX_ITEMS;
        if (page >= model.page_data.records.size() || index >= model.page_data.records[page].bar.count ||
            (seen & (uint64_t{1} << target))) return false;
        seen |= uint64_t{1} << target;
      }
      bool visible_changed = false;
      for (JsonVariant value : targets) {
        const unsigned target = value.as<unsigned>();
        const unsigned page = target / header_bar::MAX_ITEMS, index = target % header_bar::MAX_ITEMS;
        auto &current = model.page_data.records[page].bar.items[index];
        if (!(current == item)) {
          current = item;
          visible_changed |= shown_page && *shown_page == static_cast<int>(page);
        }
      }
      if (visible_changed) refresh_header_only();
      last_received = esphome::millis();
      result = "Synced";
      return true;
    }
    if (op == "page" || op == "bar") {
      if (!root["p"].is<unsigned>() || root["p"].as<unsigned>() >= model.page_data.records.size()) return false;
      const unsigned index = root["p"].as<unsigned>();
      if ((op == "page" && (transfer.active || (transfer.pages & (1u << index)))) ||
          (op == "bar" && !transfer.active)) return false;
      page_protocol::Page next;
      if (!parse_bar(root["items"], next.bar)) return false;
      if (op == "page") {
        if (!page_protocol::key(string(root["id"]), next.id) || !root["home_control"].is<bool>() ||
            !root["excluded"].is<bool>() || !root["title"].is<const char *>() ||
            root["title"].as<std::string>().size() > 96) return false;
        for (size_t i = 0; i < model.page_data.records.size(); ++i)
          if ((transfer.pages & (1u << i)) && model.page_data.records[i].id == next.id) return false;
        next.title = string(root["title"], 96);
        next.home_control = root["home_control"].as<bool>();
        next.excluded = root["excluded"].as<bool>();
        if (!transfer.page(index)) return false;
        model.page_data.records[index] = std::move(next);
      } else {
        auto &current = model.page_data.records[index].bar;
        bool same = current.count == next.bar.count;
        for (size_t i = 0; same && i < current.count; ++i) same = current.items[i] == next.bar.items[i];
        current = std::move(next.bar);
        if (!same && shown_page && *shown_page == static_cast<int>(index)) refresh_header_only();
      }
      last_received = esphome::millis();
      result = transfer.active ? "Synced" : "Loading tiles";
      return true;
    }
    if (op == "commit") {
      // A retried commit with a new sequence acknowledges the same document.
      // It must not navigate back to the page shown before the transfer.
      if (transfer.active && model.ready()) {
        last_received = esphome::millis(); result = "Synced"; return true;
      }
      if (!transfer.commit()) { result = "Error: incomplete layout"; return false; }
      model.configured = true;
      if (shown_page) *shown_page = model.page_data.restore(previous_page_id, had_previous_page);
      if (layout_changed) layout_changed();
      prepare_start();  // every other page built ahead (firmware 0.3.2+)
      last_received = esphome::millis();
      refresh_all();
#ifdef USE_ESP32
      // Building every tile inside the API's call is the deepest the loop task goes; this is the figure the
      // loop_task_stack_size in hardware/esp-idf.yaml is sized from (firmware 0.3.1+).
      ESP_LOGI("health", "layout applied, loop_stack_min_free=%u", (unsigned) uxTaskGetStackHighWaterMark(nullptr));
#endif
      result = "Synced";
      return true;
    }
    if (op != "tile" && !transfer.active) { result = "Resend needed"; return false; }
    if (op == "camera") {
      // A link to a camera's image (app 0.2.66+): the answer to camera_request ("full"), or an alert's image ("alert",
      // announced with an empty link before show_alert and sent again with the link), or the media card's cover
      // ("cover", app 0.2.77+). Only ESP Screens' own port.
      const std::string view = string(root["t"], 8), entity = string(root["e"], view == "live" ? 400 : 120), url = string(root["u"], 240);
      // "live" (app 0.2.91+): the page's camera tiles as one strip; `e` lists them, "" for one without a picture.
      if (view == "live" ? !valid_entity_list(entity) : !valid_entity(entity) || (view != "full" && view != "alert" && view != "cover")) return false;
      if (!url.empty() && url.rfind("http://", 0) != 0) return false;
      const uint32_t expected_view = view == "live" ? live_view_id : view == "cover" ? cover_view_id : camera_view_id;
      if (view != "alert" && (!root["view"].is<unsigned>() || root["view"].as<unsigned>() != expected_view)) {
        result = "Synced"; return true;
      }
      camera_answer(view, entity, url);
      result = model.ready() ? "Synced" : "Loading tiles";
      return true;
    }
    if (op == "history") {
      if (!root["view"].is<unsigned>() || root["view"].as<unsigned>() != history_view_id) {
        result = "Synced"; return true;
      }
      // A detail card's history (app 0.2.59+), the answer to history_request. Checked whole before it replaces
      // the one the screen holds.
      History next;
      next.entity = string(root["entity"], 120);
      next.hours = root["hours"] | 0u;
      if (!valid_entity(next.entity) || (next.hours != 1 && next.hours != 24 && next.hours != 168)) return false;
      // An answer to an earlier question (another card, another range) would push out the one the card waits for.
      if (next.entity != history_asked_entity || next.hours != history_asked_hours) {
        result = model.ready() ? "Synced" : "Loading tiles";
        return true;
      }
      next.start = root["start"] | 0u;
      next.end = root["end"] | 0u;
      next.offset = std::clamp(root["off"] | 0, -14 * 3600, 14 * 3600);
      if (next.end <= next.start) return false;
      next.line = string(root["kind"], 12) != "timeline";
      if (root["xt"].is<JsonArray>()) for (JsonVariant moment : root["xt"].as<JsonArray>()) {
        if (next.times.size() == 8) break;
        if (moment.is<unsigned>()) next.times.push_back(moment.as<uint32_t>());
      }
      if (next.line) {
        unsigned i = 0;
        if (root["values"].is<JsonArray>()) for (JsonVariant value : root["values"].as<JsonArray>()) {
          if (i == history_view::PARTS) break;
          float v = number(value);
          next.has[i] = std::isfinite(v);
          next.values[i] = next.has[i] ? v : 0;
          ++i;
        }
        next.bottom = number(root["dom"][0], 0);
        next.top = number(root["dom"][1], 1);
        if (!(next.top > next.bottom)) next.top = next.bottom + 1;
        if (root["yt"].is<JsonArray>()) for (JsonVariant tick : root["yt"].as<JsonArray>()) {
          if (next.ticks.size() == 6) break;
          float v = number(tick[0]);
          if (std::isfinite(v)) next.ticks.emplace_back(v, string(tick[1], 16));
        }
        next.high = number(root["hi"][0]);
        next.has_high = std::isfinite(next.high);
        next.high_at = root["hi"][1] | 0u;
        next.low = number(root["lo"][0]);
        next.has_low = std::isfinite(next.low);
        next.low_at = root["lo"][1] | 0u;
        next.decimals = std::clamp(root["dec"] | 1, 0, 4);
        next.unit = string(root["unit"], 16);
      } else {
        next.slots = static_cast<uint16_t>(std::clamp(root["slots"] | 96u, 1u, 96u));
        if (root["states"].is<JsonArray>()) for (JsonVariant state : root["states"].as<JsonArray>()) {
          if (next.states.size() == 7) break;
          HistoryState s;
          s.label = string(state[0], 24);
          s.color = std::strtoul(string(state[1], 8).c_str(), nullptr, 16);
          s.seconds = state[2] | 0u;
          next.states.push_back(std::move(s));
        }
        if (root["seg"].is<JsonArray>()) for (JsonVariant item : root["seg"].as<JsonArray>()) {
          if (next.runs.size() == 96) break;
          const unsigned slot = item[0] | 0u;
          const int state = item[1] | -1;
          if (slot >= next.slots || state >= static_cast<int>(next.states.size()) || state < -1) return false;
          history_view::Run run;
          run.slot = static_cast<uint16_t>(slot);
          run.state = static_cast<int8_t>(state);
          run.begin = item[2] | 0u;
          run.end = std::max<uint32_t>(run.begin, item[3] | 0u);
          run.seconds = item[4] | 0u;
          next.runs.push_back(run);
        }
        if (root["words"].is<JsonArray>()) for (JsonVariant pair : root["words"].as<JsonArray>()) {
          if (next.words.size() == 12) break;
          next.words.emplace_back(string(pair[0], 32), string(pair[1], 24));
        }
        next.began = root["began"] | 0u;
        next.active = root["active"] | -1;
        if (next.active >= static_cast<int>(next.states.size())) next.active = -1;
      }
      history = std::move(next);
      history_received_at = esphome::millis();
      history_answered = true;
      history_received();
      result = model.ready() ? "Synced" : "Loading tiles";
      return true;
    }
    if (op == "options") {
      if (!root["view"].is<unsigned>() || root["view"].as<unsigned>() != options_view_id) {
        result = "Synced"; return true;
      }
      // The names a picker on a light's effects page asked for (options_request), one page per message.
      std::string entity = string(root["e"], 120);
      if (!valid_entity(entity) || !root["o"].is<JsonArray>()) return false;
      // Only as many as this screen has memory for, and the room asked for in one go: a list that doubles its
      // way there leaves the heap in pieces, and the allocation that does not fit aborts the firmware instead
      // of failing (effects_page::names_room).
      JsonArray sent = root["o"].as<JsonArray>();
      const size_t room = effects_page::names_room(heap_room ? heap_room() : 0);
      std::vector<std::string> names;
      names.reserve(std::min(room, static_cast<size_t>(sent.size())));
      for (JsonVariant name : sent) {
        if (names.size() >= room) break;
        std::string text = string(name, 48);
        if (!text.empty()) names.push_back(std::move(text));
      }
      if (options_received) options_received(entity, root["i"] | 0u, root["n"] | 1u, std::move(names));
      result = model.ready() ? "Synced" : "Loading tiles";
      return true;
    }
    const bool initial = op == "tile";
    if ((!initial && op != "state") || !root["i"].is<unsigned>() || !root["a"].is<JsonObject>() ||
        !root["state"].is<const char *>() || !root["name"].is<const char *>()) return false;
    const unsigned index = root["i"].as<unsigned>();
    const std::string entity = string(root["entity"], 120);
    if (initial) {
      if (transfer.active || index >= model.count || model.tiles[index].received || !valid_entity(entity) ||
          !root["slot"].is<unsigned>() || !root["o"].is<JsonObject>()) return false;
      const std::string size = string(root["o"]["size"]);
      if (!page_protocol::accepts_size(size, grid.columns, grid.rows)) return false;
      if (!model.valid_placement(index, root["slot"].as<unsigned>(), size == "full", size == "wide" || size == "square", (size == "tall" || size == "square") ? 2 : 1)) return false;
      if (page_entity(entity) && static_cast<unsigned>(entity[12] - '0') > model.pages) return false;
      if (!page_entity(entity)) for (size_t i = 0; i < model.count; ++i)
        if (i != index && model.tiles[i].received && model.tiles[i].entity == entity) return false;
      model.slots[index] = root["slot"].as<unsigned>();
      model.tiles[index].entity = entity;
    } else if (!root["o"].isNull() || !root["slot"].isNull() || !model.accepts(index, entity)) {
      result = "Error: outdated tile or configuration in state"; return false;
    }
    Tile &tile = model.tiles[index];
    if (!initial) {
      uint32_t icon = tile_icon::codepoint(string(root["icon"], 8));
      tile.icon = icon && has_icon_glyph(icon) ? tile_icon::utf8(icon) : "";
    }
    auto a = root["a"].as<JsonObject>();
    // The fingerprint of state, attributes and extras (a vacuum's mode or water select changes only
    // there), hashed while serializing so no copy of the message stays behind.
    Fingerprint state_hash;
    state_hash.add(string(root["state"]));
    state_hash.write('\n');
    serializeJson(a, state_hash);
    if (!root["x"].isNull()) serializeJson(root["x"], state_hash);
    bool was_confirmed=tile.confirmed;
    tile.observe(state_hash.value);
    if(tile.pending && !tile.local_feedback && !was_confirmed && tile.confirmed)
      ESP_LOGI("runtime_action","HA state received entity=%s elapsed=%u ms",entity.c_str(),(unsigned)(esphome::millis()-tile.pending_since));
    if (initial) {
    auto options = root["o"];
    std::string background=string(options["background"],16);
    tile.background = tile_palette::color(background);
    tile.transparent = tile_palette::transparent(background);
    // An icon these fonts lack (a newer set than this firmware) keeps the domain icon.
    uint32_t icon = tile_icon::codepoint(string(options["icon"], 8));
    tile.icon = icon && has_icon_glyph(icon) ? tile_icon::utf8(icon) : "";
    tile.tap = string(options["tap"]); if (tile.tap.empty()) tile.tap="auto";
    tile.display = string(options["display"]); if (tile.display.empty()) tile.display="standard";
    // A live picture's pace (0.2.91+): 15 or 30 s; a missing or odd value keeps the default.
    const int refresh = options["refresh"].is<int>() ? options["refresh"].as<int>() : 0;
    tile.refresh = refresh >= 5 && refresh <= 3600 ? refresh : 15;
    tile.overlay = string(options["overlay"], 8) != "none";
    tile.inline_control = string(options["inline"]); if (tile.inline_control.empty()) tile.inline_control="none";
    // What the second line says (firmware 0.2.90+); "auto" is the line the screen works out itself, as before.
    tile.subtitle = string(options["sub"], 96); if (tile.subtitle.empty()) tile.subtitle="auto";
    // Direct controls (0.2.19+): the manager sends only the set a wide card really shows.
    tile.controls = string(options["controls"], 16);
    // Geometry belongs to initialization and never changes in a live value packet.
    std::string size = string(options["size"]);
    tile.full = size == "full";
    tile.wide = tile.full || size == "wide" || size == "square";
    tile.height = (size == "tall" || size == "square") ? 2 : 1;

    }
    // Pre-computed extras: the manager converts time zones and fetches forecasts. What only some tiles
    // carry is collected in `next` and replaces the tile's Extra at the end (see Tile::set_extra).
    auto extra = root["x"];
    Extra next;
    // A tap's own Home Assistant action (app 0.2.67+): {"s": action, "d": [[key, text]], "t": [[key, template]]}.
    auto act = root["o"]["act"];
    if (initial && act.is<JsonObject>()) {
      std::string service = string(act["s"], 64);
      auto pairs = [](JsonVariant list, std::vector<std::pair<std::string, std::string>> &out) {
        if (!list.is<JsonArray>()) return;
        for (JsonVariant pair : list.as<JsonArray>()) {
          if (out.size() == 8 || !pair.is<JsonArray>() || pair.as<JsonArray>().size() != 2) continue;
          std::string key = string(pair[0], 32);
          if (!key.empty()) out.emplace_back(std::move(key), string(pair[1], 400));
        }
      };
      if (valid_action(service)) {
        next.action = std::move(service);
        pairs(act["d"], next.action_data);
        pairs(act["t"], next.action_templates);
      }
    }
    if (!initial) if (auto *saved = tile.extra_ptr()) {
      next.action = std::move(saved->action);
      next.action_data = std::move(saved->action_data);
      next.action_templates = std::move(saved->action_templates);
    }
    if (extra["days"].is<JsonArray>()) for (JsonVariant day : extra["days"].as<JsonArray>()) {
      if (next.forecast.size() == 5) break;
      next.forecast.emplace_back(); auto &f = next.forecast.back();
      f.day = string(day["d"], 8); f.condition = string(day["c"], 20); f.high = number(day["h"]); f.low = number(day["l"]);
      f.rain = number(day["p"]); f.mm = number(day["r"]);
    }
    if (extra["hours"].is<JsonArray>()) for (JsonVariant hour : extra["hours"].as<JsonArray>()) {
      if (next.hours.size() == 8) break;
      next.hours.emplace_back(); auto &h = next.hours.back();
      h.time = string(hour["t"], 5); h.condition = string(hour["c"], 20); h.temp = number(hour["h"]); h.rain = number(hour["p"]); h.mm = number(hour["r"]);
    }
    tile.last_run = extra["last"].is<unsigned>() ? extra["last"].as<uint32_t>() : 0;
    next.sunrise = string(extra["rise"], 5); next.sunset = string(extra["set"], 5);
    next.timer_end = extra["end"].is<unsigned>() ? extra["end"].as<uint32_t>() : 0;
    next.duration = string(extra["dur"], 16); next.remaining = string(extra["rem"], 16);
    tile.has_history=false;
    if (root["history"]["values"].is<JsonArray>()) {
      tile.history.assign(24,NAN);unsigned j=0;
      for (JsonVariant value:root["history"]["values"].as<JsonArray>()) {
        if(j==24) break; tile.history[j++]=number(value); }
      tile.has_history=j>0;tile.history_hours=std::clamp(root["history"]["hours"].as<unsigned>(),1u,24u);
    } else if (!tile.history.empty()) { tile.history.clear(); tile.history.shrink_to_fit(); }
    // Sixteen options at most (firmware 0.3.3, eight before): the select card pages through what it cannot show at once.
    if (a["options"].is<JsonArray>()) for(JsonVariant option:a["options"].as<JsonArray>()) {
      if(next.options.size()==16)break;next.options.push_back(string(option,48)); }
    tile.battery=number(a["battery_level"]);tile.volume=number(a["volume_level"]);
    tile.muted=a["is_volume_muted"].is<bool>() && a["is_volume_muted"].as<bool>();
    tile.device_class=string(a["device_class"],24);next.hvac_action=string(a["hvac_action"],24);
    next.media_title=string(a["media_title"],80);tile.supported=a["supported_features"].as<uint32_t>();
    // The media card (firmware 0.2.64+, app 0.2.77+): the artist, the album, the track's length and position, and a
    // mark of the cover picture; an app from before sends none of them and the card shows what it has.
    next.media_artist=string(extra["artist"],80);next.media_album=string(extra["album"],80);next.media_picture=string(extra["pic"],16);
    next.media_duration=extra["dur"].is<unsigned>()?extra["dur"].as<uint32_t>():0;
    next.media_position=extra["pos"].is<unsigned>()?extra["pos"].as<uint32_t>():0;
    next.media_position_at=extra["at"].is<unsigned>()?extra["at"].as<uint32_t>():0;
    tile.name = string(root["name"], 80);
    const std::string before = tile.state;
    tile.state = string(root["state"], 160);
    if (!initial && tile.received && before != tile.state) tile.changed_at = std::max<uint32_t>(1, esphome::millis());
    tile.unit = string(a["unit_of_measurement"], 20);
    tile.brightness = number(a["brightness"]);
    tile.percentage = number(a["percentage"]);
    tile.slider_reported(esphome::millis());
    tile.position = number(a["current_position"]);
    next.tilt = number(a["current_tilt_position"]);
    tile.current = number(a["current_temperature"]);
    tile.target = number(a["temperature"]);
    tile.humidity = number(a["current_humidity"]);
    tile.minimum = number(a["min_temp"], 7);
    tile.maximum = number(a["max_temp"], 35);
    tile.step = number(a["target_temp_step"], 0.5f);
    if(tile.domain()=="number" || tile.domain()=="input_number") {
      tile.minimum=number(a["min"],0);tile.maximum=number(a["max"],100);tile.step=number(a["step"],1); }
    if(tile.domain()=="weather") {
      tile.current=number(a["temperature"]);tile.unit=string(a["temperature_unit"],12);
      tile.humidity=number(a["humidity"]);next.wind=number(a["wind_speed"]);next.wind_unit=string(a["wind_speed_unit"],8);next.feels=number(a["apparent_temperature"]);
    }
    tile.modes = list(a["supported_color_modes"]);
    next.hvac_modes = list(a["hvac_modes"]);
    next.fan_modes = list(a["fan_modes"]); next.swing_modes = list(a["swing_modes"]);
    next.fan_mode = string(a["fan_mode"], 48); next.swing_mode = string(a["swing_mode"], 48);
    float hue = number(a["hs_color"][0]);
    float saturation = number(a["hs_color"][1]);
    tile.has_hs_color = std::isfinite(hue) && std::isfinite(saturation);
    tile.saturation = tile.has_hs_color ? std::lround(std::clamp(saturation, 0.0f, 100.0f)) : 0;
    if (std::isfinite(hue)) tile.hue = std::lround(std::clamp(hue, 0.0f, 360.0f));
    float kelvin = number(a["color_temp_kelvin"]);
    if (std::isfinite(kelvin)) tile.kelvin = std::lround(std::clamp(kelvin, 1000.0f, 15000.0f));
    tile.min_kelvin = std::clamp(number(a["min_color_temp_kelvin"], 0), 0.0f, 15000.0f);
    tile.max_kelvin = std::clamp(number(a["max_color_temp_kelvin"], 0), 0.0f, 15000.0f);
    next.fan_speed = string(a["fan_speed"], 48);
    if (a["fan_speed_list"].is<JsonArray>()) for (JsonVariant speed : a["fan_speed_list"].as<JsonArray>()) {
      if (next.fan_speeds.size() == 4) break;
      next.fan_speeds.push_back(string(speed, 48));
    }
    // Vacuum rows (app 0.2.46+): the cleaning mode and water selects of the robot's device and the
    // suction speeds to offer, each at most six; the battery sensor when the vacuum has no attribute.
    // A chip just tapped keeps its choice while Home Assistant is still busy with it, so another update
    // of the robot (its battery, say) does not flip the row back for a moment.
    std::vector<std::pair<char, std::string>> tapped;
    if (tile.waiting(esphome::millis())) for (auto &c : tile.extra().choices) if (!c.sent.empty()) tapped.emplace_back(c.kind, c.sent);
    auto choice = [&](const char *key, char kind) {
      auto c = extra[key];
      if (!c["o"].is<JsonArray>()) return;
      Choice row; row.kind = kind;
      row.entity = string(c["e"], 120); row.current = string(c["s"], 48); row.roles = string(c["r"], 6);
      if (kind != 's' && !valid_entity(row.entity)) return;
      for (JsonVariant value : c["o"].as<JsonArray>()) { if (row.values.size() == 6) break; row.values.push_back(string(value, 48)); }
      if (c["l"].is<JsonArray>()) for (JsonVariant label : c["l"].as<JsonArray>()) {
        if (row.labels.size() == row.values.size()) break; row.labels.push_back(string(label, 24)); }
      while (row.labels.size() < row.values.size()) row.labels.push_back(row.values[row.labels.size()]);
      if (!row.values.empty()) next.choices.push_back(std::move(row));
    };
    if (tile.domain() == "vacuum") { choice("mode", 'm'); choice("water", 'w'); choice("fan", 's'); tile_controls::settle_suction(next); }
    for (auto &[kind, value] : tapped) if (auto *c = next.choice(kind)) if (c->current != value) c->sent = value;
    // A light's effects page (app 0.2.83+): the effect it runs, and the selects and numbers of its device.
    next.effect = string(a["effect"], 48);
    if (extra["rows"].is<JsonArray>()) for (JsonVariant r : extra["rows"].as<JsonArray>()) {
      if (next.option_rows.size() == 3) break;
      OptionRow row; row.entity = string(r["e"], 120);
      if (!valid_entity(row.entity)) continue;
      row.name = string(r["n"], 32); row.current = string(r["s"], 48); row.count = static_cast<uint16_t>(std::min(r["c"] | 0u, 65535u));
      row.icon = tile_icon::codepoint(string(r["i"], 8));
      next.option_rows.push_back(std::move(row));
    }
    if (extra["nums"].is<JsonArray>()) for (JsonVariant r : extra["nums"].as<JsonArray>()) {
      if (next.number_rows.size() == 2) break;
      NumberRow row; row.entity = string(r["e"], 120);
      if (!valid_entity(row.entity)) continue;
      row.name = string(r["n"], 32); row.value = number(r["v"]); row.low = number(r["lo"], 0); row.high = number(r["hi"], 100); row.step = number(r["st"], 1);
      if (!(row.high > row.low)) continue;
      row.icon = tile_icon::codepoint(string(r["i"], 8));
      next.number_rows.push_back(std::move(row));
    }
    if (!std::isfinite(tile.battery)) tile.battery = number(extra["bat"]);
    next.charging = extra["chg"].is<int>() && extra["chg"].as<int>() == 1;
    next.room = string(extra["room"], 32);
    next.state_word = string(extra["w"], 32);
    // A value of this entity the second line was set to: the finished line, or seconds for a moment in time.
    next.subtitle = string(extra["s"], 64);
    next.subtitle_at = extra["sm"].is<unsigned>() ? extra["sm"].as<unsigned>() : 0;
    // An alarm panel (app 0.3.8+, firmware 0.3.3+): how it takes codes, who changed it, and a delay's end.
    if (tile.domain() == "alarm_control_panel") {
      next.code_format = string(a["code_format"], 8);
      next.changed_by = string(a["changed_by"], 48);
      next.arm_code_free = a["code_arm_required"].is<bool>() && !a["code_arm_required"].as<bool>();
      next.code_saved = extra["dc"].is<int>() && extra["dc"].as<int>() == 1;
      next.alarm_end = extra["ae"].is<unsigned>() ? extra["ae"].as<uint32_t>() : 0;
      next.alarm_delay = extra["ad"].is<unsigned>() ? extra["ad"].as<uint32_t>() : 0;
    }
    tile.set_extra(std::move(next));
    // Home Assistant reports the edited value: the -/+ pill follows its state again.
    if(std::isfinite(tile.edit_value) && tile.edit_sent && std::fabs(tile_controls::edit_target(tile)-tile.edit_value)<0.051f)tile.edit_value=NAN;
    tile.received = true;
    for(auto &w:widgets)if(w.index==index)w.cached_active=-1;
    last_received = esphome::millis();
    if (initial) {
      transfer.tile(index);
      result = "Loading tiles";
      return true;
    }
    refresh_tile(index);
    if (active_index == static_cast<int>(index) && detail_update) detail_update(tile);
    if (tile.domain() == "alarm_control_panel") alarm_state_arrived(index, before);
    refresh_detail(index);
    result = model.ready() ? "Synced" : "Loading tiles";
    return true;
  });
  if (accepted && sequenced) transfer.accepted(packet_sequence, packet_hash.value);
  return result;
}
#pragma GCC diagnostic pop
}  // namespace runtime_tiles
