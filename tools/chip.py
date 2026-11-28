#!/usr/bin/env python3
"""A board's second chip over its USB port (docs/SECOND_CHIP.md): which firmware it runs, a new one, a sound.

    uv run --with pyserial python tools/chip.py hello [PORT]
    uv run --with pyserial python tools/chip.py flash FILE.uf2 [PORT]   restarts the chip as the drive RPI-RP2 and copies the file
    uv run --with pyserial python tools/chip.py play FILE.wav [PORT] [--volume 0..1]
    uv run --with pyserial python tools/chip.py try [PORT]              the chip plays its own two notes

PORT is the chip's own serial port (on a SenseCAP Indicator the one called INDICATOR RP2040, USB id 2886:0050); without
it the first port with that id is taken. The frames are chip_protocol.h's, the same the screen sends over its serial
line.
"""
import argparse
import shutil
import struct
import sys
import time
import wave
from pathlib import Path

import serial
from serial.tools import list_ports

CHIP_IDS = {(0x2886, 0x0050)}
HELLO, BEGIN, AUDIO, END, VOLUME, TRY, HELLO_BACK, STATUS = 0x01, 0x10, 0x11, 0x12, 0x13, 0x14, 0x81, 0x90
AUDIO_MOST = 511


def crc16(data, crc=0xFFFF):
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data):
    out, block = bytearray(), bytearray()
    for byte in data:
        if byte == 0:
            out += bytes([len(block) + 1]) + block
            block = bytearray()
        else:
            block.append(byte)
            if len(block) == 254:
                out += b'\xff' + block
                block = bytearray()
    return bytes(out + bytes([len(block) + 1]) + block)


def cobs_decode(data):
    out, at = bytearray(), 0
    while at < len(data):
        code = data[at]
        if code == 0 or at + code > len(data):
            return None
        out += data[at + 1:at + code]
        at += code
        if code != 0xFF and at < len(data):
            out.append(0)
    return bytes(out)


def frame(kind, payload=b''):
    plain = bytes([kind]) + payload
    return cobs_encode(plain + struct.pack('>H', crc16(plain))) + b'\x00'


class Chip:
    def __init__(self, port):
        self.line = serial.Serial(port, 115200, timeout=0.02)
        self.rest = b''

    def send(self, kind, payload=b''):
        self.line.write(frame(kind, payload))

    def frames(self):
        self.rest += self.line.read(4096)
        *whole, self.rest = self.rest.split(b'\x00')
        for wire in whole:
            plain = cobs_decode(wire) if wire else None
            if plain and len(plain) >= 3 and crc16(plain[:-2]) == struct.unpack('>H', plain[-2:])[0]:
                yield plain[0], plain[1:-2]

    def ask(self, kind, answer, payload=b'', seconds=1.0):
        self.send(kind, payload)
        until = time.time() + seconds
        while time.time() < until:
            for got, body in self.frames():
                if got == answer:
                    return body
        return None

    def hello(self):
        body = self.ask(HELLO, HELLO_BACK)
        if body is None or len(body) < 7:
            return None
        return {'protocol': body[0], 'version': '%d.%d.%d' % tuple(body[1:4]), 'what': body[4], 'room': struct.unpack('<H', body[5:7])[0]}

    def play(self, samples, rate, volume=1.0, stream=1):
        """Plays 16-bit mono `samples` (bytes) and returns once the chip says it is through."""
        hello = self.hello()
        if hello is None:
            raise SystemExit('the chip does not answer: is Tessera\'s firmware on it?')
        room = hello['room']
        self.send(VOLUME, struct.pack('<H', int(round(max(0.0, min(1.0, volume)) * 32768))))
        self.send(BEGIN, struct.pack('<BH', stream, rate))
        total, sent, played, state, ended = len(samples) // 2, 0, 0, 1, False
        last = time.time()
        while True:
            while sent < total and sent - played < room - AUDIO_MOST:
                count = min(AUDIO_MOST, total - sent, room - (sent - played))
                self.send(AUDIO, bytes([stream]) + samples[2 * sent:2 * (sent + count)])
                sent += count
            if sent >= total and not ended:
                self.send(END, bytes([stream, 0]))
                ended = True
            for got, body in self.frames():
                if got == STATUS and len(body) >= 10 and body[0] == stream:
                    state, _taken, played = body[1], *struct.unpack('<II', body[2:10])
                    last = time.time()
            if ended and state == 0:
                return played
            if time.time() - last > 2.0:
                raise SystemExit('the chip stopped answering')


def find_port():
    for port in list_ports.comports():
        if (port.vid, port.pid) in CHIP_IDS:
            return port.device
    raise SystemExit('no chip found: give its port')


def drive():
    """The chip as a drive: the folder of its INFO_UF2.TXT. Only folders named like the drive are looked into, since
    another volume (a network share that went away) can hold a look for minutes."""
    for root in ('/Volumes', '/media', '/run/media'):
        try:
            names = __import__('os').listdir(root)
        except OSError:
            continue
        for name in names:
            if name.startswith('RPI-RP2') and (Path(root) / name / 'INFO_UF2.TXT').exists():
                return Path(root) / name
    return None


def flash(file, port):
    if drive() is None:
        # Opening its port at 1200 baud restarts the chip as a drive; it leaves the bus while the port is still being
        # set up, so an error on the way is how it goes.
        try:
            line = serial.Serial(port or find_port(), 1200)
            line.dtr = False
            time.sleep(0.1)
            line.close()
        except (OSError, serial.SerialException):
            pass
    until = time.time() + 15
    while drive() is None:
        if time.time() > until:
            raise SystemExit('the drive RPI-RP2 did not appear')
        time.sleep(0.25)
    target = drive()
    print('writing', file, 'to', target)
    try:
        shutil.copyfile(file, target / Path(file).name)
    except OSError as error:  # the drive leaves as soon as the last block is in
        print('  (the drive left while the copy ended: %s)' % error)
    until = time.time() + 15
    while time.time() < until:
        try:
            chip = Chip(port or find_port())
            hello = chip.hello()
            if hello:
                print('the chip runs', hello['version'])
                return
        except (SystemExit, serial.SerialException):
            pass
        time.sleep(0.5)
    raise SystemExit('the chip did not come back')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('what', choices=['hello', 'flash', 'play', 'try'])
    parser.add_argument('rest', nargs='*')
    parser.add_argument('--volume', type=float, default=1.0)
    args = parser.parse_args()
    if args.what == 'hello':
        print(Chip(args.rest[0] if args.rest else find_port()).hello())
    elif args.what == 'flash':
        flash(args.rest[0], args.rest[1] if len(args.rest) > 1 else None)
    elif args.what == 'try':
        chip = Chip(args.rest[0] if args.rest else find_port())
        chip.send(VOLUME, struct.pack('<H', 32768))
        chip.send(TRY)
        time.sleep(1.2)
    else:
        with wave.open(args.rest[0], 'rb') as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise SystemExit('a mono WAV of 16 bits, please')
            samples, rate = w.readframes(w.getnframes()), w.getframerate()
        chip = Chip(args.rest[1] if len(args.rest) > 1 else find_port())
        start = time.time()
        played = chip.play(samples, rate, args.volume)
        print('played %d samples in %.2f s' % (played, time.time() - start))


if __name__ == '__main__':
    main()
