"""Save a Guition LVGL diagnostic snapshot as PNG through its encrypted API."""
import argparse
import asyncio
from pathlib import Path
import re
import struct
import zlib
import yaml
from aioesphomeapi import APIClient, LogLevel


def png(rows, width=240, height=240):
    pixels=bytearray()
    for y in range(height):
        pixels.append(0)
        for x in range(width):
            p=int(rows[y][x*4:x*4+4],16)
            pixels.extend((((p>>11)&31)*255//31,((p>>5)&63)*255//63,(p&31)*255//31))
    def chunk(name,data):
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')


async def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='guition-wallbox.local')
    p.add_argument('--name',default='guition-wallbox')
    p.add_argument('--secrets',type=Path,default=Path(__file__).resolve().parents[1]/'secrets.yaml')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--glass',action='store_true',help="the panel's frame buffer (a live picture too), not LVGL's drawing")
    args=p.parse_args()
    if args.output.exists():raise ValueError('Output already exists; choose a different name.')
    client=APIClient(args.host,6053,noise_psk=yaml.safe_load(args.secrets.read_text())['api_encryption_key'],expected_name=args.name)
    await client.connect(login=True)
    try:
        _,services=await client.list_entities_services()
        done=asyncio.Event();rows={};errors=[];size=[240,240]
        def log(msg):
            text=msg.message.decode(errors='replace') if isinstance(msg.message,bytes) else msg.message
            b=re.search(r'IMAGE BEGIN (\d+) (\d+)',text)
            if b:size[:]=[int(b[1]),int(b[2])]
            m=re.search(r'ROW (\d{3}) ([0-9a-f]+)',text)
            if m:rows[int(m[1])]=m[2]
            if 'IMAGE FAIL' in text:errors.append(text);done.set()
            if 'IMAGE COMPLETE' in text:done.set()
        client.subscribe_logs(log,log_level=LogLevel.LOG_LEVEL_INFO,dump_config=False)
        await client.execute_service(next(s for s in services if s.name==('glass_snapshot' if args.glass else 'ui_snapshot')),{})
        await asyncio.wait_for(done.wait(),timeout=60)
        if errors or set(rows)!=set(range(size[1])):raise ValueError(f'Incomplete image: {len(rows)}/{size[1]} rows; {errors}')
        with args.output.open('xb') as f:f.write(png(rows,*size))
        print(f'PASS: LVGL render saved to {args.output}')
    finally:await client.disconnect()

if __name__=='__main__':asyncio.run(main())
