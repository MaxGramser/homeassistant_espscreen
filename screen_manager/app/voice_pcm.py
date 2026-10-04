"""Bounded device PCM conversion, using FFmpeg through PyAV on the host only."""
from array import array
from collections import deque
from fractions import Fraction
import io
import math
import sys

RATE = 16000
MAX_REPLY_BYTES = RATE * 2 * 45


class Resampler:
    def __init__(self, source, target):
        import av
        self.av, self.source, self.offset = av, source, 0
        self.converter = av.AudioResampler(format='s16', layout='mono', rate=target)

    def push(self, pcm):
        if len(pcm) % 2:
            raise ValueError('Incomplete PCM sample.')
        frame = self.av.AudioFrame(format='s16', layout='mono', samples=len(pcm) // 2)
        frame.sample_rate, frame.time_base, frame.pts = self.source, Fraction(1, self.source), self.offset
        self.offset += frame.samples
        frame.planes[0].update(pcm)
        return self.pack(self.converter.resample(frame))

    @staticmethod
    def pack(frames):
        return b''.join(bytes(frame.planes[0])[:frame.samples * 2] for frame in frames)

    def finish(self):
        return self.pack(self.converter.resample(None))


def decode_reply(data, mime):
    import av
    formats = {'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/mpeg': 'mp3',
               'audio/flac': 'flac', 'audio/x-flac': 'flac', 'audio/ogg': 'ogg'}
    if mime not in formats or len(data) > 4 * 1024 * 1024:
        raise ValueError('Unsupported or oversized reply.')
    pcm = bytearray()
    # Fixed audio demuxer, in-memory input, no playlists or remote resource loading.
    try:
        with av.open(io.BytesIO(data), format=formats[mime]) as container:
            converter = av.AudioResampler(format='s16', layout='mono', rate=RATE)
            for frame in container.decode(audio=0):
                pcm.extend(Resampler.pack(converter.resample(frame)))
                if len(pcm) > MAX_REPLY_BYTES:
                    raise ValueError('The spoken reply exceeds 45 seconds.')
            pcm.extend(Resampler.pack(converter.resample(None)))
    except av.error.FFmpegError as error:
        raise ValueError('The spoken reply could not be decoded.') from error
    if not pcm or len(pcm) > MAX_REPLY_BYTES:
        raise ValueError('No bounded spoken reply.')
    return bytes(pcm)


class Utterance:
    """Same bounded endpoint as browser Claude capture; never recognises words."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.frames = deque()
        self.samples = self.voiced = self.silence = 0
        self.active = False

    def push(self, pcm):
        samples = array('h', pcm)
        if sys.byteorder != 'little':
            samples.byteswap()
        speaking = bool(samples) and math.sqrt(sum(x*x for x in samples)/len(samples))/32768 >= .008
        self.frames.append(pcm)
        self.samples += len(samples)
        if speaking:
            self.active = True
            self.voiced += len(samples)
            self.silence = 0
        else:
            self.silence += len(samples)
        if not self.active:
            while self.samples > 4800:
                self.samples -= len(self.frames.popleft())//2
            return None, speaking
        if self.silence < 14400 and self.samples < RATE*30:
            return None, speaking
        result = b''.join(self.frames) if self.voiced >= 3200 else None
        self.reset()
        return result, speaking
