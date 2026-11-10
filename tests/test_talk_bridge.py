"""The doorbell's talk bridge (screen_manager/app/talk_bridge.py): what needs no aiortc: the rate, the cutting into whole
samples and packets, the newest voice kept, one talker a camera, and the codec read back from the answer."""
import array
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'screen_manager' / 'app'))

import talk_bridge as tb  # noqa: E402


def pcm(*samples):
    return array.array('h', samples).tobytes()


def test_decimate_halves_and_keeps_a_steady_level():
    out, last = tb.decimate(array.array('h', [1000] * 8), 1000)
    assert list(out) == [1000] * 4 and last == 1000


def test_decimate_takes_the_highest_tone_away():
    # A tone at the old rate's half folds back at 8 kHz without a filter; through 1/4, 1/2, 1/4 nothing is left.
    samples = array.array('h', [5000, -5000] * 8)
    out, _ = tb.decimate(samples, -5000)
    assert all(abs(value) <= 1 for value in out)


def test_a_part_cut_inside_a_sample_stays_whole():
    source = tb.Pcm8k(level=1)
    source.last = 800  # the filter's history, so the first sample is not a run-up from silence
    data = pcm(*[800] * 320)
    source.feed(data[:161])  # odd: half a sample left over
    source.feed(data[161:])
    assert len(source.ready) == 160
    assert set(source.ready) == {800}


def test_a_packet_is_twenty_ms_and_silence_when_nothing_waits():
    source = tb.Pcm8k(level=1)
    assert source.packet() == bytes(tb.PACKET_SAMPLES * 2)
    source.feed(pcm(*[100] * (tb.PACKET_SAMPLES * 2)))
    packet = source.packet()
    assert len(packet) == tb.PACKET_SAMPLES * 2
    assert array.array('h', packet)[10] == 100


def test_the_newest_voice_stays():
    source = tb.Pcm8k(most=2, level=1)
    source.feed(pcm(*[1] * (tb.PACKET_SAMPLES * 4)))   # the old
    source.feed(pcm(*[2] * (tb.PACKET_SAMPLES * 4)))   # the new, two packets
    assert source.dropped == tb.PACKET_SAMPLES * 2
    assert set(array.array('h', source.packet())[1:]) == {2}  # its first sample still carries the old one in the filter


def test_a_voice_goes_to_the_door_at_half_level():
    source = tb.Pcm8k()
    source.last = 800
    source.feed(pcm(*[800] * (tb.PACKET_SAMPLES * 2)))
    assert set(array.array('h', source.packet())) == {400}


def test_one_talker_a_camera():
    links = tb.Links(websocket=None, clock=lambda: 0.0)
    first, second = links.link('camera.door', 's1'), links.link('camera.door', 's2')
    assert links.busy(first) is None
    links.begin(first)
    assert links.busy(first) is None and links.busy(second) == 'busy'
    links.end(first)
    assert links.busy(second) is None
    assert links.busy('nothing') == 'unknown'


def test_a_link_goes_after_its_time():
    now = [0.0]
    links = tb.Links(websocket=None, clock=lambda: now[0])
    old = links.link('camera.door')
    now[0] = tb.LINK_SECONDS + 1
    links.link('camera.other')
    assert links.busy(old) == 'unknown'


def test_the_codec_of_the_answer():
    answer = 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 8 0\r\na=rtpmap:8 PCMA/8000\r\na=rtpmap:0 PCMU/8000\r\n'
    assert tb.negotiated_codec(answer) == 'PCMA/8000'
    assert tb.negotiated_codec('') == ''


def test_a_conversations_sound_is_marked():
    import live_stream
    assert b'X-Sound: talk' in live_stream.part_head(b'audio/x-s16le;rate=16000', 640, talk=True)
    assert b'X-Sound' not in live_stream.part_head(b'audio/x-s16le;rate=16000', 640)


def test_a_screens_stream_address_uses_its_api_key():
    import screen_source
    url = screen_source.rtsp_url('192.0.2.1', 'abc')
    assert url.startswith('rtsp://tessera:') and url.endswith('@192.0.2.1:8554/')
    assert url != screen_source.rtsp_url('192.0.2.1', 'abd')


def test_a_voice_goes_straight_to_where_it_is_going():
    got = []
    voice = tb.Voice(got.append, 'camera.x')
    voice.feed(b'ab')
    assert got == [b'ab']
