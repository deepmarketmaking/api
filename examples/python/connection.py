import asyncio
import random

import websockets

SERVER_LIST = ['wss://deist.deepmm.com', 'wss://hayek.deepmm.com']


async def connect():
    # Create a WebSocket connection
    server_index = random.randint(0, len(SERVER_LIST) - 1)
    open_timeout = 1
    sleep_time = 0
    while True:
        try:
            print(f"Attempting connection to {SERVER_LIST[server_index]}")
            ws = await websockets.connect(SERVER_LIST[server_index],
                                          max_size=10 ** 8,
                                          open_timeout=open_timeout,
                                          ping_timeout=None)
            print(f"Successful connection to {SERVER_LIST[server_index]}")
            return ws
        except BaseException:
            print(f"Unsuccessful connection to {SERVER_LIST[server_index]}")
            await asyncio.sleep(sleep_time)
            server_index = 0 if server_index == len(SERVER_LIST) - 1 else server_index + 1
            open_timeout = min(60, open_timeout + 1)
            sleep_time = min(10, sleep_time + 1)
