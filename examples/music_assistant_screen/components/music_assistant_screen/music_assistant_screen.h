#pragma once
#include "esphome/core/component.h"
#include "esphome/components/smart_display/plugin_api.h"
#include "esphome/components/number/number.h"
#include "esphome/components/switch/switch.h"
namespace esphome::music_assistant_screen {
class MusicAssistantScreen : public Component, public tessera::Plugin {
 public:
  void set_player(const std::string &v){player_=roomy::text(v);}
  void set_library_entry(const std::string &v){entry_=roomy::text(v);}
  void set_favorite_button(const std::string &v){favorite_=roomy::text(v);}
  void set_enabled(switch_::Switch *v){enabled_=v;}
  void set_volume(number::Number *v){volume_=v;}
  void set_artwork_timeout(number::Number *v){artwork_=v;}
  void on_ready() override {sync();}
  void on_interval(uint32_t now) override;
  void on_alert() override {tessera::close_media_artwork();}
  void before_update() override {tessera::close_media_artwork();}
  void on_standby(bool dark) override {if(dark)tessera::close_media_artwork();}
  bool settings(tessera::SettingsPage &page) override;
 private:
  void sync();
  tessera::Text player_,entry_,favorite_;
  switch_::Switch *enabled_=nullptr;
  number::Number *volume_=nullptr,*artwork_=nullptr;
  float last_volume_=-1,last_artwork_=-1;
  bool last_enabled_=false;
};
}
