// A plugin's action with fields of any JSON type (plugin API 0.12, components/smart_display/plugin_action.h): texts go
// as they are, every other value as the Python literal Home Assistant reads back into its type, and nothing a plugin
// sends is ever a Jinja template.
#include "components/smart_display/plugin_action.h"
#include <cassert>
#include <string>

using namespace plugin_action;

int main() {
  // JSON's words as Python names them; numbers, lists and mappings as they are.
  assert(literal("21") == "21");
  assert(literal("21.5") == "21.5");
  assert(literal("true") == "True" && literal("false") == "False" && literal("null") == "None");
  assert(literal("[20,100]") == "[20,100]");
  assert(literal("[true,false,null]") == "[True,False,None]");
  assert(literal("{\"a\":1,\"b\":[\"x\"]}") == "{\"a\":1,\"b\":[\"x\"]}");
  assert(literal("[{\"a\":{\"b\":true}}]") == "[{\"a\":{\"b\":True}}]");
  // A word inside a text stays the word: "true" in a title is no True.
  assert(literal("[\"true\",\"null\"]") == "[\"true\",\"null\"]");
  // Braces in a text never make a template, and the text reads back the same.
  assert(literal("[\"{{ states('lock.door') }}\"]") == "[\"\\x7b\\x7b states('lock.door') \\x7d\\x7d\"]");
  assert(literal("{\"{%\":\"{#\"}") == "{\"\\x7b%\":\"\\x7b#\"}");
  assert(!jinja(literal("[\"{{x}}\",{\"{%\":\"{#\"}]")));
  // JSON's escapes are Python's, but for "\/".
  assert(literal("[\"a\\\"b\\\\c\\nd\\/e\\u00e9\"]") == "[\"a\\\"b\\\\c\\nd/e\\u00e9\"]");
  assert(literal("[\"\xC3\xA9\"]") == "[\"\xC3\xA9\"]");   // UTF-8 as it is
  assert(literal("[\"cut") == "" && literal("[\"cut\\") == "");

  // Music Assistant's play_media: the entity, two texts and a list; the texts as they are, also one that looks like a
  // number or a template.
  Encoded out;
  const char *why = nullptr;
  assert(encode("media_player.kitchen",
                {{"media_id", true, "1989"}, {"media_type", true, "album"}, {"artist", true, "{{ Taylor }}"},
                 {"enqueue", false, "\"replace\""}, {"radio_mode", false, "false"}, {"media_ids", false, "[\"a\",\"b\"]"}},
                out, &why));
  assert(out.data.size() == 4 && out.templates.size() == 3);
  assert(out.data[0].first == "entity_id" && out.data[0].second == "media_player.kitchen");
  assert(out.data[1].second == "1989" && out.data[3].second == "{{ Taylor }}");
  assert(out.templates[0].second == "\"replace\"");
  assert(out.templates[1].first == "radio_mode" && out.templates[1].second == "False");
  assert(out.templates[2].second == "[\"a\",\"b\"]");
  // Without an entity the fields name their own target, several speakers at once.
  assert(encode("", {{"entity_id", false, "[\"media_player.a\",\"media_player.b\"]"}, {"volume_level", false, "0.4"}}, out));
  assert(out.data.empty() && out.templates.size() == 2 && out.templates[1].second == "0.4");
  // What does not fit: the entity twice, a name that is no field's, a field twice, too many, too much.
  assert(!encode("light.a", {{"entity_id", true, "light.b"}}, out, &why) && std::string(why) == "entity_id is given twice");
  assert(!encode("", {{"Brightness", false, "3"}}, out) && !encode("", {{"", true, "x"}}, out));
  assert(!encode("", {{"a", true, "x"}, {"a", false, "1"}}, out));
  std::vector<Field> many;
  for (int i = 0; i < 17; ++i) many.push_back({"f" + std::to_string(i), false, "1"});
  assert(!encode("", many, out));
  many.resize(16);
  assert(encode("", many, out) && !encode("light.a", many, out));
  assert(!encode("", {{"a", true, std::string(1100, 'x')}}, out, &why) && std::string(why) == "the fields are larger than 1 KB");
  assert(!encode("", {{"a", false, "[\"cut"}}, out));

  assert(service_name("music_assistant.play_media") && service_name("light.turn_on"));
  assert(!service_name("play_media") && !service_name(".x") && !service_name("x.") && !service_name("Light.on"));
  assert(key_name("media_id") && key_name("_x") && !key_name("1st") && !key_name(std::string(33, 'a')));
  return 0;
}
