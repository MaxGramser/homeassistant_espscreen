"""Exercise the real ESPHome ES7210 C++ driver against a fake I2C register bank."""
from pathlib import Path
import subprocess
import tempfile
import unittest

root = Path(__file__).resolve().parents[1]
headers = {
 'esphome/core/component.h': '''#pragma once
#include <algorithm>
#include <cstdint>
namespace esphome {
template<typename T> T clamp(T v,T lo,T hi){return std::clamp(v,lo,hi);}
class Component { public: virtual ~Component()=default; virtual void setup(){}; virtual void dump_config(){};
void mark_failed(){failed=true;} bool is_failed()const{return failed;}
void status_set_warning(){warning=true;} void status_clear_warning(){warning=false;}
bool warning=false; private: bool failed=false; };
}
''',
 'esphome/core/hal.h': '#pragma once\n',
 'esphome/core/log.h': '''#pragma once
template<typename... T> void test_log(T...){}
#define ESP_LOGCONFIG(...) test_log(__VA_ARGS__)
#define ESP_LOGE(...) test_log(__VA_ARGS__)
#define ESP_LOGW(...) test_log(__VA_ARGS__)
#define ONOFF(x) ((x)?"ON":"OFF")
''',
 'esphome/components/audio_adc/audio_adc.h': '''#pragma once
namespace esphome::audio_adc { class AudioAdc {public: virtual ~AudioAdc()=default;
virtual bool set_mic_gain(float)=0; virtual float mic_gain()=0;}; }
''',
 'esphome/components/i2c/i2c.h': '''#pragma once
#include <array>
#include <cstdint>
namespace esphome::i2c { class I2CDevice {public:
std::array<uint8_t,256> regs{};
int writes=0, fail_write=0, fail_read=0;
bool write_byte(uint8_t reg,uint8_t value){++writes; if(fail_write && !--fail_write)return false; regs[reg]=value;return true;}
bool read_byte(uint8_t reg,uint8_t *value){if(fail_read && !--fail_read)return false;*value=regs[reg];return true;}
}; }
''',
}
class Es7210Registers(unittest.TestCase):
    def test_real_driver_registers_and_i2c_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            for file, source in headers.items():
                path = out / file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            (out / 'test.cpp').write_text(r'''
            #include "es7210.h"
            #include <cassert>
            #include <limits>
            using namespace esphome::es7210;
            void gains(ES7210 &adc,uint8_t value){for(int r=0x1b;r<=0x1e;++r)assert(adc.regs[r]==value);}
            int main(){
             ES7210 adc;
             adc.set_sample_rate(16000); adc.set_mic_gain(36); adc.setup();
             assert(!adc.is_failed()); assert(!adc.alc_enabled()); gains(adc,0xbf);
             assert(adc.set_mic_gain(36)); assert(adc.regs[0x43]==0x1d);
             adc.regs[0x16]=0xa0; adc.regs[0x17]=0xb0;
             assert(adc.set_digital_gain(6)); gains(adc,0xcb); assert(adc.regs[0x16]==0xa0);
             assert(adc.set_alc_enabled(true)); gains(adc,0xd7);
             assert(adc.regs[0x16]==0xaf && adc.regs[0x17]==0xb6);
             assert(adc.regs[0x18]==0xf7 && adc.regs[0x19]==0xf7);
             const int writes=adc.writes;
             assert(adc.set_digital_gain(9)); assert(adc.writes==writes); gains(adc,0xd7);
             assert(adc.set_mic_gain(24)); assert(adc.regs[0x43]==0x18);
             assert(adc.alc_enabled()); gains(adc,0xd7);
             assert(adc.set_alc_enabled(false)); assert(!adc.alc_enabled()); gains(adc,0xd1);
             assert(adc.regs[0x43]==0x18 && adc.regs[0x16]==0xa0);
             for(int write=1;write<=9;++write){
              adc.fail_write=write;
              assert(!adc.set_alc_enabled(true)); assert(adc.warning);
              assert(!adc.alc_enabled() && adc.digital_gain()==9); gains(adc,0xd1);
              assert(adc.regs[0x16]==0xa0);
             }
             adc.fail_read=1;
             assert(!adc.set_alc_enabled(true)); assert(!adc.alc_enabled()); gains(adc,0xd1);
             assert(adc.set_alc_enabled(true));
             adc.fail_write=3;
             assert(!adc.set_alc_enabled(false)); assert(adc.alc_enabled()); gains(adc,0xd7);
             assert(adc.regs[0x16]==0xaf);
             assert(adc.set_alc_enabled(false)); gains(adc,0xd1); assert(!adc.warning);
             assert(!adc.set_digital_gain(std::numeric_limits<float>::infinity()));
             assert(!adc.set_digital_gain(std::numeric_limits<float>::quiet_NaN()));
             assert(!adc.set_digital_gain(32.5f)); assert(!adc.set_digital_gain(-96)); gains(adc,0xd1);
             assert(adc.set_digital_gain(-95.5f)); gains(adc,0x00);
             assert(adc.set_digital_gain(32)); gains(adc,0xff);
             assert(adc.set_alc_enabled(true)); adc.mark_failed();
             assert(!adc.set_digital_gain(0)); assert(!adc.set_alc_enabled(false));
             ES7210 boot; boot.set_sample_rate(16000); boot.set_mic_gain(24);
             boot.set_digital_gain(6); boot.set_alc_max_gain(18); boot.set_alc_enabled(true);
             assert(boot.writes==0); boot.setup(); assert(!boot.is_failed());
             gains(boot,0xe3); assert(boot.alc_enabled());
            
             assert(boot.set_alc_enabled(false)); gains(boot,0xcb);
             assert(boot.regs[0x12]==0); // Legacy stereo mode remains the default.
             for(uint8_t channel=1;channel<=4;++channel){
              ES7210 tdm;
              tdm.set_sample_rate(16000); tdm.set_mic_gain(30);
              tdm.set_tdm(true); tdm.set_reference(channel,0);
              tdm.set_digital_gain(6); tdm.set_alc_enabled(true);
              tdm.setup(); assert(!tdm.is_failed());
              assert(tdm.regs[0x11]==0x60 && tdm.regs[0x12]==0x02);
              const auto ref_reg=0x1b+4-channel;
              const auto ref_gain_reg=0x43+channel-1;
              const uint8_t alc_mask=0x0f & ~(1U << (4-channel));
              for(int mic=1;mic<=4;++mic){
               assert(tdm.regs[0x43+mic-1]==(mic==channel?0x10:0x1a));
               assert(tdm.regs[0x1b+4-mic]==(mic==channel?0xbf:0xd7));
              }
              assert(tdm.regs[0x16]==alc_mask);
              assert(tdm.set_mic_gain(36)); assert(tdm.regs[ref_gain_reg]==0x10);
              assert(tdm.set_alc_enabled(false)); assert(tdm.regs[0x16]==0);
              for(int mic=1;mic<=4;++mic)assert(tdm.regs[0x1b+4-mic]==(mic==channel?0xbf:0xcb));
              for(int write=1;write<=9;++write){
               tdm.fail_write=write;
               assert(!tdm.set_alc_enabled(true)); assert(!tdm.alc_enabled());
               assert(tdm.regs[ref_reg]==0xbf && tdm.regs[0x16]==0);
              }
              assert(tdm.set_alc_enabled(true)); assert(tdm.regs[0x16]==alc_mask);
              assert(tdm.regs[ref_reg]==0xbf && tdm.regs[ref_gain_reg]==0x10);
             }
             ES7210 gain;
             gain.set_sample_rate(16000); gain.set_mic_gain(30); gain.set_reference(3,6); gain.setup();
             assert(gain.regs[0x45]==0x12); assert(gain.set_mic_gain(24)); assert(gain.regs[0x45]==0x12);
            }
            
            ''')
            driver = root / 'components/es7210'
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', f'-I{out}', f'-I{driver}', str(out/'test.cpp'), str(driver/'es7210.cpp'), '-o', str(out/'test')], check=True)
            subprocess.run([str(out/'test')], check=True)
            print('PASS: ES7210 legacy gain/ALC, TDM format, all four reference-channel mappings, independent reference gain and I2C failure recovery')
