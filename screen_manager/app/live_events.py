"""Read-only updates over WebSocket, with SSE for already-open older editors."""
import asyncio

from aiohttp import web


async def serve(request, updates):
    # Each SSE occupies an HTTP/1 connection. An overview with several previews
    # can occupy the browser's entire pool and strand actions and state reads.
    socket = web.WebSocketResponse(heartbeat=30, max_msg_size=1024)
    if socket.can_prepare(request).ok:
        await socket.prepare(request)

        async def send():
            async for body in updates:
                if body is not None:
                    await socket.send_str(body)

        async def read():
            async for _ in socket:
                pass  # This stream accepts no commands; reading detects closure.

        tasks = [asyncio.create_task(send()), asyncio.create_task(read())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await updates.aclose()
            await socket.close()
        return socket

    response = web.StreamResponse(headers={'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store',
                                          'X-Accel-Buffering': 'no', 'X-Content-Type-Options': 'nosniff'})
    try:
        await response.prepare(request)
        async for body in updates:
            await response.write(f'data: {body}\n\n'.encode() if body is not None else b': keepalive\n\n')
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        await updates.aclose()
    return response
