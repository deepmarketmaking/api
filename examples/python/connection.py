import asyncio

import websockets

SERVER = 'wss://api.deepmm.com'


async def connect():
    # Create a WebSocket connection
    open_timeout = 1
    sleep_time = 0
    while True:
        try:
            print(f"Attempting connection to {SERVER}")
            ws = await websockets.connect(SERVER,
                                          max_size=10 ** 8,
                                          open_timeout=open_timeout,
                                          ping_timeout=None)
            print(f"Successful connection to {SERVER}")
            return ws
        except BaseException:
            print(f"Unsuccessful connection to {SERVER}")
            await asyncio.sleep(sleep_time)
            open_timeout = min(60, open_timeout + 1)
            sleep_time = min(10, sleep_time + 1)
