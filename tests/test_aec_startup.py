"""Execute the patched EspAec::process body with instrumented DSP boundaries."""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
component=ROOT/'components/esp_aec'
source=(component/'esp_aec.cpp').read_text()
body=source[source.index('bool EspAec::process('):source.index('\nFeatureControl EspAec::feature_control(')]
stub=r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>
using afe_aec_handle_t = int;
bool lock_available=true;
int dsp_calls=0;
std::vector<int16_t> last_input;
size_t afe_aec_process(afe_aec_handle_t*,const int16_t*in,int16_t*out) {
 ++dsp_calls;last_input.assign(in,in+1024);
 for(int i=0;i<512;++i)out[i]=in[2*i];
 return 1024;
}
namespace esp_audio_stack {
struct ScopedLock {ScopedLock(void*,int){} explicit operator bool()const{return lock_available;}};
}
class EspAec {
public:
 int cached_frame_size_=512,mode_=5;
 bool input_started_=false;
 std::atomic<uint32_t> startup_silence_frames_{0};
 int handle_storage_=1;
 void*handle_=&handle_storage_;void*handle_mutex_=nullptr;
 int16_t storage_[1024]{};int16_t*input_frame_=storage_;
 bool process(const int16_t*,const int16_t*,int16_t*,uint8_t);
};
'''
test=r'''
int main() {
 int16_t mic[1024]{},ref[512]{},out[512];
 auto clear_out=[&]{std::fill_n(out,512,123);};
 auto zero_out=[&]{assert(std::all_of(out,out+512,[](int16_t v){return v==0;}));};
 EspAec a;
 for(int i=0;i<1024;++i){clear_out();assert(a.process(mic,ref,out,1));zero_out();}
 assert(dsp_calls==0 && !a.input_started_ && a.startup_silence_frames_==1024);
 // The final selected sample must be included; low-amplitude speech is not gated.
 mic[511]=1;assert(a.process(mic,ref,out,1));
 assert(dsp_calls==1 && last_input[1022]==1 && a.input_started_);
 mic[511]=0;assert(a.process(mic,ref,out,1));
 assert(dsp_calls==2); // After startup, silent frames and tails still reach DSP.
 // Either reference or mic can start the original DSP; no level threshold.
 EspAec reference_only;ref[511]=-1;assert(reference_only.process(mic,ref,out,1));
 assert(dsp_calls==3 && last_input[1023]==-1);ref[511]=0;
 EspAec stereo;mic[1]=10;assert(stereo.process(mic,ref,out,2));
 assert(dsp_calls==3); // Unselected second mic must not start processing.
 mic[1022]=-1;assert(stereo.process(mic,ref,out,2));
 assert(dsp_calls==4 && last_input[1022]==-1);
 std::fill_n(mic,1024,0);
 // Other modes retain their existing call behavior.
 for(int mode : {0,1,3,4,6}){EspAec other;other.mode_=mode;assert(other.process(mic,ref,out,1));}
 assert(dsp_calls==9);
 // Startup silence must not mask missing pointers, handles or lock failures.
 EspAec fail;
 assert(!fail.process(mic,ref,nullptr,1));
 clear_out();assert(!fail.process(nullptr,ref,out,1));zero_out();
 clear_out();assert(!fail.process(mic,nullptr,out,1));zero_out();
 fail.handle_=nullptr;clear_out();assert(!fail.process(mic,ref,out,1));zero_out();
 fail.handle_=&fail.handle_storage_;lock_available=false;
 clear_out();assert(!fail.process(mic,ref,out,1));zero_out();lock_available=true;
 assert(dsp_calls==9 && fail.startup_silence_frames_==0);
 std::cout << "PASS: actual process body, leading zeros, first 1-LSB input, reference-only input, stride, later silence, unchanged modes and failure guards\n";
}
'''
import unittest

class AecStartup(unittest.TestCase):
    def test_actual_process_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'test.cpp').write_text(stub+body+test)
            subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)
