#pragma once
// Bounded, on-demand media group view, shared with the inbox decoder.
#include <cstdint>
#include <string>
#include <vector>
#include "lvgl.h"
namespace runtime_tiles {
constexpr uint32_t MEDIA_GROUPING = 524288;
struct MediaGroup { std::string entity, name; };
struct MediaSpeaker { std::string entity, name; int volume=-1; bool muted=false, enabled=false; };
struct MediaSpeakers {
  std::string source, group, name;
  unsigned page=0, pages=1, group_page=0, group_pages=1;
  std::vector<MediaGroup> groups;
  std::vector<MediaSpeaker> speakers;
};
inline MediaSpeakers media_speakers;
inline uint32_t media_speakers_view=0,media_speakers_received=0;
inline bool media_speakers_dirty=false;
bool media_touching();
void media_speakers_open(unsigned index);
void media_speakers_close();
void media_speakers_tick();
void media_speakers_accept(MediaSpeakers next);
void media_views_foreground();
void media_art_event(lv_event_t *event);
void media_zoom_close();
void media_zoom_show(lv_image_dsc_t *source);
void media_zoom_tick();
}  // namespace runtime_tiles
