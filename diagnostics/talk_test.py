#!/usr/bin/env python3
"""Plays a sound into a camera's speaker through the add-on's talk bridge (screen_manager/app/talk_bridge.py), without a
screen: the second step of proving the doorbell's Talk (docs/DOORBELL.md), between Home Assistant's own talk button and a
screen's microphone. It plays through a real camera's speaker, so run it only when someone there expects it.

Needs aiohttp, aiortc and av. Reads Home Assistant's address and a long-lived token from the arguments:

    uv run --no-project --python 3.13 --with aiohttp --with aiortc==1.15.0 --with av==17.1.0 python diagnostics/talk_test.py \
        --url http://homeassistant.local:8123 --token-file .esphome/ha_token --camera camera.front_door --wav hello.wav

Without --wav it sends a soft tone sweep for --seconds (default 5); with --silence it opens the session, sends silence and
says whether Home Assistant connected it (nothing to hear; the check that needs nobody there).
"""
import argparse
import asyncio
import contextlib
import math
import pathlib
import struct
import sys
import time
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'screen_manager' / 'app'))

import aiohttp  # noqa: E402

import talk_bridge  # noqa: E402

SECONDS_DEFAULT = 5


def tone(seconds):
    """A soft sweep from 300 to 1200 Hz at 16 kHz, 16-bit mono."""
    out = bytearray()
    phase = 0.0
    total = int(seconds * talk_bridge.SCREEN_RATE)
    for n in range(total):
        frequency = 300 + 900 * n / total
        phase += 2 * math.pi * frequency / talk_bridge.SCREEN_RATE
        out += struct.pack('<h', int(9000 * math.sin(phase)))
    return bytes(out)


def read_wav(path):
    with wave.open(str(path)) as wav:
        if wav.getframerate() != talk_bridge.SCREEN_RATE or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise SystemExit('The file must be 16 kHz, 16-bit mono (ffmpeg -i in -ar 16000 -ac 1 out.wav)')
        return wav.readframes(wav.getnframes())


async def main(args):
    url = args.url.rstrip('/').replace('http', 'ws', 1) + '/api/websocket'
    token = pathlib.Path(args.token_file).read_text().strip()

    @contextlib.asynccontextmanager
    async def websocket():
        async with aiohttp.ClientSession() as session, session.ws_connect(url) as ws:
            await ws.receive_json()
            await ws.send_json({'type': 'auth', 'access_token': token})
            said = await ws.receive_json()
            if said.get('type') != 'auth_ok':
                raise ConnectionError('Home Assistant refused the token')
            yield ws

    pcm = bytes(int(args.seconds * talk_bridge.SCREEN_RATE) * 2) if args.silence else \
        read_wav(args.wav) if args.wav else tone(args.seconds)
    talk = talk_bridge.Talk(websocket, args.camera)
    began = time.monotonic()
    if not await talk.open():
        print('Home Assistant did not connect the talk session.')
        return 1
    print(f'Connected in {time.monotonic() - began:.2f} s, codec {talk.codec}.')
    part = talk_bridge.SCREEN_RATE * 2 * talk_bridge.PACKET_MS // 1000
    started = time.monotonic()
    for i in range(0, len(pcm), part):
        talk.feed(pcm[i:i + part])
        wait = started + (i / part + 1) * talk_bridge.PACKET_MS / 1000 - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
    await asyncio.sleep(0.5)
    await talk.close()
    print(f'Sent {len(pcm) / (2 * talk_bridge.SCREEN_RATE):.1f} s, {talk.source.dropped} samples dropped.')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--camera', required=True)
    parser.add_argument('--wav')
    parser.add_argument('--seconds', type=float, default=SECONDS_DEFAULT)
    parser.add_argument('--silence', action='store_true')
    sys.exit(asyncio.run(main(parser.parse_args())))
