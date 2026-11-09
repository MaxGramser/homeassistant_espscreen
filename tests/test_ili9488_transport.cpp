// Compile the production driver against a recording transport, not a rewritten driver.
#include "components/ili9488_i80/ili9488_i80.h"
#include <cassert>
using namespace esphome;
using namespace esphome::ili9488_i80;
int main() {
 ILI9488I80 lcd;
 InternalGPIOPin data[16], dc(45), wr(18), rd(48);
 for(int i=0;i<16;++i){data[i].pin=i;lcd.set_data_pin(i,&data[i]);}
 lcd.set_dc_pin(&dc);lcd.set_wr_pin(&wr);lcd.set_rd_pin(&rd);
 lcd.setup();
 assert(!lcd.is_failed() && rd.high);
 assert(fake::bus.bus_width==16 && fake::io.lcd_param_bits==8 && fake::io.cs_gpio_num==-1);
 assert(fake::commands.front()==std::vector<uint8_t>({1}));
 // 320x17 exceeds the DMA buffer: two windows, each with a completion wait.
 // Source has a leading row, one left pixel and two right pixels of padding.
 const int stride=323;
 std::vector<uint8_t> source(stride*18*2,0);
 for(int row=0;row<17;++row)for(int x=0;x<320;++x){
   int v=row*320+x, i=((row+1)*stride+1+x)*2;
   source[i]=v>>8;source[i+1]=v;
 }
 lcd.draw_pixels_at(0,20,320,17,source.data(),display::COLOR_ORDER_RGB,display::COLOR_BITNESS_565,true,1,1,2);
 assert(fake::pixels.size()==2 && fake::waits==2);
 assert(fake::pixels[0].size()==5120 && fake::pixels[1].size()==320);
 for(int i=0;i<5440;++i)assert(fake::pixels[i/5120][i%5120]==i);
 assert(fake::commands.back()==std::vector<uint8_t>({0x2B,0,36,0,36}));
 // Out-of-bounds rectangles must never hit the peripheral.
 lcd.draw_pixels_at(319,0,2,1,source.data(),display::COLOR_ORDER_RGB,display::COLOR_BITNESS_565,true,0,0,0);
 assert(fake::pixels.size()==2);
 // Timeout leaves DMA storage alone and stops all subsequent writes.
 fake::timeout=true;
 lcd.draw_pixel_at(0,0,{255,0,0});
 assert(lcd.is_failed() && fake::pixels.size()==3);
 auto count=fake::commands.size();
 lcd.draw_pixel_at(1,0,{0,255,0});
 assert(fake::pixels.size()==3 && fake::commands.size()==count);
}
