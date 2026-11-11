#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <vector>
#define IRAM_ATTR
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGCONFIG(...) ((void)0)
#define MALLOC_CAP_DMA 1
#define MALLOC_CAP_INTERNAL 2
using esp_err_t = int;
constexpr int ESP_OK=0, LCD_CLK_SRC_DEFAULT=0, pdFALSE=0, pdTRUE=1;
using BaseType_t = int;
using SemaphoreHandle_t = void*;
using esp_lcd_i80_bus_handle_t = void*;
using esp_lcd_panel_io_handle_t = void*;
struct esp_lcd_panel_io_event_data_t {};
struct esp_lcd_i80_bus_config_t {
 int dc_gpio_num, wr_gpio_num, clk_src, data_gpio_nums[16];
 size_t bus_width, max_transfer_bytes;
};
struct esp_lcd_panel_io_i80_config_t {
 int cs_gpio_num; uint32_t pclk_hz; size_t trans_queue_depth; int lcd_cmd_bits,lcd_param_bits;
 struct { int dc_idle_level,dc_cmd_level,dc_dummy_level,dc_data_level; } dc_levels;
 bool (*on_color_trans_done)(esp_lcd_panel_io_handle_t,esp_lcd_panel_io_event_data_t*,void*);
 void *user_ctx;
};
namespace fake {
inline esp_lcd_i80_bus_config_t bus{};
inline esp_lcd_panel_io_i80_config_t io{};
inline std::vector<std::vector<uint16_t>> pixels;
inline std::vector<std::vector<uint8_t>> commands;
inline bool timeout=false, error=false;
inline int waits=0;
}
inline const char *esp_err_to_name(int) { return "fake error"; }
inline void *heap_caps_malloc(size_t n,int) { return std::malloc(n); }
inline void *xSemaphoreCreateBinary() { return reinterpret_cast<void*>(1); }
inline int xSemaphoreGiveFromISR(void*,int*) { return pdTRUE; }
inline int pdMS_TO_TICKS(int n) { return n; }
inline int xSemaphoreTake(void*,int) { ++fake::waits; return fake::timeout?pdFALSE:pdTRUE; }
inline int esp_lcd_new_i80_bus(const esp_lcd_i80_bus_config_t *c,void **p) {fake::bus=*c;*p=(void*)1;return 0;}
inline int esp_lcd_new_panel_io_i80(void*,const esp_lcd_panel_io_i80_config_t *c,void **p) {fake::io=*c;*p=(void*)1;return 0;}
inline int esp_lcd_panel_io_tx_param(void*,int cmd,const void *p,size_t n) {
 std::vector<uint8_t> v{uint8_t(cmd)};
 if(n) v.insert(v.end(),(const uint8_t*)p,(const uint8_t*)p+n);
 fake::commands.push_back(v);return fake::error?1:0;
}
inline int esp_lcd_panel_io_tx_color(void*,int,const void *p,size_t n) {
 if(fake::error)return 1;
 fake::pixels.emplace_back((const uint16_t*)p,(const uint16_t*)p+n/2);
 if(!fake::timeout)fake::io.on_color_trans_done(nullptr,nullptr,fake::io.user_ctx);
 return 0;
}
namespace esphome {
inline void delay(int) {}
struct Color {uint8_t red,green,blue;};
namespace setup_priority {constexpr float HARDWARE=800;}
struct InternalGPIOPin {
 int pin;bool high=false;
 explicit InternalGPIOPin(int p=0):pin(p){}
 int get_pin(){return pin;}void setup(){}void digital_write(bool v){high=v;}
};
namespace display {
enum DisplayType {DISPLAY_TYPE_COLOR};
enum ColorOrder {COLOR_ORDER_RGB,COLOR_ORDER_BGR};
enum ColorBitness {COLOR_BITNESS_565,COLOR_BITNESS_888};
struct Clip {bool inside(int,int){return true;}};
class Display {
 bool failed=false;
 public:
 virtual ~Display()=default;
 virtual void setup(){} virtual void update(){} virtual void dump_config(){}
 virtual float get_setup_priority()const{return 0;}
 virtual DisplayType get_display_type()=0;
 virtual void draw_pixel_at(int,int,Color)=0;
 virtual void draw_pixels_at(int,int,int,int,const uint8_t*,ColorOrder,ColorBitness,bool,int,int,int){}
 bool is_failed(){return failed;}void mark_failed(){failed=true;}
 Clip get_clipping(){return {};}
 protected:
 virtual int get_width_internal()=0;virtual int get_height_internal()=0;void do_update_(){}
};
}
}
