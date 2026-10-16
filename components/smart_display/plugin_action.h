#pragma once
// A plugin's Home Assistant action with fields of any JSON type (plugin API 0.12, tessera::action with a JSON object),
// as Home Assistant's ESPHome integration takes an action from a screen (homeassistant/components/esphome/manager.py,
// async_on_service_call): `data` is a map of texts, given to the action as they are, and `data_template` a map of
// templates, each rendered and then read as a Python literal (helpers/template, _parse_result: "21" becomes 21, "True"
// true, "[20, 100]" a list, "{'a': 1}" a mapping). So a text goes in `data`, where Home Assistant never reads it again
// (an album called "1989" stays a text), and every other value in `data_template` as a Python literal.
//
// A template runs Jinja when it holds "{{", "{%" or "{#" (is_template_string). A literal written here never does: its
// own braces are a mapping's, always followed by a quote or its end, and a brace inside a text is written as \x7b or
// \x7d, which the literal reads back as the brace. Text from the internet in a list (an album title with "{{" in it)
// is a text again in Home Assistant, never a template. Pure, so tests/test_plugin_action.cpp runs it on the computer.
#include <cstddef>
#include <string>
#include <utility>
#include <vector>

namespace plugin_action {

// As many fields as Tessera's own taps carry (8 texts and 8 rendered values), a key as Home Assistant names its fields,
// and all of it together within what one action of the native API carries comfortably.
constexpr size_t MAX_FIELDS = 16, MAX_KEY = 32, MAX_BYTES = 1024;

// One field: `text` a text (`value` is the text itself), otherwise `value` is the field's JSON (a number, true or
// false, null, a list, an object).
struct Field {
  std::string key;
  bool text;
  std::string value;
};
using Pairs = std::vector<std::pair<std::string, std::string>>;
struct Encoded {
  Pairs data, templates;
};

// domain.action, as Home Assistant names an action.
inline bool service_name(const std::string &service) {
  const size_t dot = service.find('.');
  if (dot == std::string::npos || dot == 0 || dot + 1 >= service.size() || service.size() > 96) return false;
  for (size_t i = 0; i < service.size(); ++i) {
    const char c = service[i];
    if (i == dot) continue;
    if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) return false;
  }
  return true;
}

// A field's name: a-z, 0-9 and _, starting with a letter or _, at most MAX_KEY.
inline bool key_name(const std::string &key) {
  if (key.empty() || key.size() > MAX_KEY || (key[0] >= '0' && key[0] <= '9')) return false;
  for (char c : key)
    if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) return false;
  return true;
}

// Whether Home Assistant would render `text` as a Jinja template.
inline bool jinja(const std::string &text) {
  return text.find("{{") != std::string::npos || text.find("{%") != std::string::npos ||
         text.find("{#") != std::string::npos;
}

// The Python literal of a JSON value as ArduinoJson writes it (no spaces, texts with JSON's escapes, UTF-8 as it is):
// true, false and null as Python names them, a brace inside a text as \x7b and \x7d, "\/" as "/". Everything else of
// JSON is already Python. "" when the JSON is cut short.
inline std::string literal(const std::string &json) {
  std::string out;
  out.reserve(json.size() + 8);
  bool text = false;
  for (size_t i = 0; i < json.size(); ++i) {
    const char c = json[i];
    if (text) {
      if (c == '\\') {
        if (i + 1 >= json.size()) return "";
        const char next = json[++i];
        if (next == '/') out += '/';
        else { out += '\\'; out += next; }
      } else if (c == '{') {
        out += "\\x7b";
      } else if (c == '}') {
        out += "\\x7d";
      } else {
        if (c == '"') text = false;
        out += c;
      }
      continue;
    }
    if (c == '"') {
      text = true;
      out += c;
    } else if (json.compare(i, 4, "true") == 0) {
      out += "True";
      i += 3;
    } else if (json.compare(i, 5, "false") == 0) {
      out += "False";
      i += 4;
    } else if (json.compare(i, 4, "null") == 0) {
      out += "None";
      i += 3;
    } else {
      out += c;
    }
  }
  return text ? "" : out;
}

// The fields of one action as the ESPHome integration takes them. `entity`: the entity it acts on, its `entity_id`
// (empty: the fields name their own target, such as an entity_id list, or there is none). False, with `why`, when it
// does not fit: a name that is no field's, a field given twice with the entity, too many or too much.
inline bool encode(const std::string &entity, const std::vector<Field> &fields, Encoded &out, const char **why = nullptr) {
  auto no = [&](const char *reason) {
    if (why) *why = reason;
    return false;
  };
  out = {};
  if (fields.size() + !entity.empty() > MAX_FIELDS) return no("too many fields");
  size_t bytes = 0;
  if (!entity.empty()) {
    out.data.emplace_back("entity_id", entity);
    bytes += 9 + entity.size();
  }
  for (const auto &field : fields) {
    if (!key_name(field.key)) return no("a field's name is a-z, 0-9 and _");
    if (field.key == "entity_id" && !entity.empty()) return no("entity_id is given twice");
    for (const auto &pair : out.data) if (pair.first == field.key) return no("a field is given twice");
    for (const auto &pair : out.templates) if (pair.first == field.key) return no("a field is given twice");
    if (field.text) {
      out.data.emplace_back(field.key, field.value);
      bytes += field.key.size() + field.value.size();
      continue;
    }
    std::string value = literal(field.value);
    if (value.empty() || jinja(value)) return no("a value is no JSON");
    bytes += field.key.size() + value.size();
    out.templates.emplace_back(field.key, std::move(value));
  }
  if (bytes > MAX_BYTES) return no("the fields are larger than 1 KB");
  return true;
}

}  // namespace plugin_action
