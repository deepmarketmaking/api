import asyncio
import json
from sys import argv
import time

import websockets

from authentication import create_get_id_token
from cusips_to_figis import openfigi_map_cusips_to_figis

async def main():
    if len(argv) != 6:
        print('Usage: python performance_test.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password> <openfigi_api_key>')
        exit()

    region = argv[1]
    client_id = argv[2]
    username = argv[3]
    password = argv[4]
    # Open FIGI API key
    _API_KEY = argv[5]

    get_id_token = create_get_id_token(region, client_id, username, password)

    cusip_to_figi, _ = openfigi_map_cusips_to_figis(_API_KEY,   ['594918BJ2', '594918AR5'])

    print("Mapping of CUSIPs to FIGIs complete\nCalling Deep MM API with FIGIs")

    template = {
                'rfq_label': 'spread',
                'figi': cusip_to_figi['594918BJ2'],
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            }

    # open a WebSocket connection to the server
    ws = await websockets.connect("wss://staging1.deepmm.com",
                                  max_size=10 ** 8,
                                  open_timeout=None,
                                  ping_timeout=None)
    
    # 4,000 unique subscription requests, differing only in the quantity property
    inferences = []
    for i in range(4_000):
        inferences.append({**template, 'quantity': 1_000_000 + i})
    msg = {
        'token': get_id_token(),
        'inference': inferences
    }
    # send the message to the server
    await ws.send(json.dumps(msg))
    # keep track of the last time we sent a token to the server
    last_token_send_time = time.time()

    # listen for messages from the server forever
    while True:
        # wait for a response from the server
        response = await ws.recv()
        # parse the response as JSON
        response_json = json.loads(response)
        if 'inference' in response_json:
            # print the number of inferences received
            print(f"{len(response_json['inference'])} inferences received")
            # print the min and max quantities received
            min_quantity = 1_000_000_000
            max_quantity = 0
            for inference in response_json['inference']:
                min_quantity = min(min_quantity, inference['quantity'])
                max_quantity = max(max_quantity, inference['quantity'])
            print(f"{min_quantity = }, {max_quantity = }\n")
        else:
            # if the response did not contain 'inference' then pretty-print the response
            print(json.dumps(response_json, indent=4))
        # periodically send an updated token to the server so our session does not expire
        # NOTE: the server does send a response to a message with only an updated token
        if time.time() - last_token_send_time > 60:
            await ws.send(json.dumps({ 'token': get_id_token() }))
            last_token_send_time = time.time()


if __name__ == '__main__':
    asyncio.run(main())
