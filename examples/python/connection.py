import asyncio
import os

import websockets

DEFAULT_SERVER = 'wss://api.deepmm.com'


async def connect(server=None):
    if server is None:
        server = os.getenv('DEEP_MM_SERVER', DEFAULT_SERVER)
    # Create a WebSocket connection
    open_timeout = 1
    sleep_time = 0
    while True:
        try:
            print(f"Attempting connection to {server}")
            ws = await websockets.connect(server,
                                          max_size=10 ** 8,
                                          open_timeout=open_timeout,
                                          ping_timeout=None)
            print(f"Successful connection to {server}")
            return ws
        except BaseException:
            print(f"Unsuccessful connection to {server}")
            await asyncio.sleep(sleep_time)
            open_timeout = min(60, open_timeout + 1)
            sleep_time = min(10, sleep_time + 1)
