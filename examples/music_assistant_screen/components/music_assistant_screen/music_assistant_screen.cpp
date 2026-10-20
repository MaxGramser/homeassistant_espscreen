#include "music_assistant_screen.h"
#include <cmath>
namespace esphome::music_assistant_screen {
void MusicAssistantScreen::sync(){
  tessera::MediaScreenConfig c;
  c.entity=roomy::plain(player_);c.library_entry=roomy::plain(entry_);c.favorite_button=roomy::plain(favorite_);
  c.enabled=enabled_&&enabled_->state&&!player_.empty();
  const float volume=volume_&&std::isfinite(volume_->state)?volume_->state:30;
  const float timeout=artwork_&&std::isfinite(artwork_->state)?artwork_->state:60;
  c.starting_volume=volume/100;c.artwork_after_ms=uint32_t(timeout*1000);
  tessera::configure_media_screen(c);
  last_enabled_=enabled_&&enabled_->state;last_volume_=volume;last_artwork_=timeout;
}
void MusicAssistantScreen::on_interval(uint32_t now){
  if(enabled_->state!=last_enabled_||volume_->state!=last_volume_||artwork_->state!=last_artwork_)sync();
  tessera::poll_media_screen(now);
}
bool MusicAssistantScreen::settings(tessera::SettingsPage &page){
  page.toggle(text("enabled"),[this](){return enabled_->state;},[this](bool v){if(v)enabled_->turn_on();else enabled_->turn_off();});
  page.number(text("volume"),0,100,1,"%",[this](){return int(volume_->state);},[this](int v){auto call=volume_->make_call();call.set_value(v);call.perform();});
  page.number(text("artwork"),0,600,15,"s",[this](){return int(artwork_->state);},[this](int v){auto call=artwork_->make_call();call.set_value(v);call.perform();});
  return true;
}
}
