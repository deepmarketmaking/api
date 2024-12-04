import asyncio
import json
from sys import argv
import time

import websockets

from authentication import create_get_id_token

async def main():

    if len(argv) != 5:
        print('Usage: python subscribe_unrecognized_figi.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password>')
        print('See README for additional details')
        exit()

    region = argv[1]
    client_id = argv[2]
    username = argv[3]
    password = argv[4]

    get_id_token = create_get_id_token(region, client_id, username, password)

    msg = {
        'token': get_id_token(),
        'inference': [
            {
                'rfq_label': 'spread',
                'figi': 'BBG006F8RW84', # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'spread',
                'figi': 'BBG00KHV1HM5',  # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'spread',
                'figi': 'BBG00P35JY86',  # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'spread',
                'figi': 'BBG00P35JYN9',  # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'spread',
                'figi': 'BBG00P2S1QD7',  # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            }
        ]
    }

    for i in range(300):
        msg['inference'].append({
                'rfq_label': 'price',
                'figi': 'BBG00BBHSZG0',
                'quantity': 1_000_000+i,
                'side': 'dealer',
                'ats_indicator': "N",
                'subscribe': True,
            })
        msg['inference'].append(
            {
                'rfq_label': 'spread',
                'figi': "BBG003LZRTD5",
                'quantity': 1_000_000+i,
                'side': 'offer',
                'ats_indicator': "Y",
                'subscribe': True,
            })

    # open a WebSocket connection to the server
    ws = await websockets.connect("wss://staging1.deepmm.com",
                                  max_size=10 ** 8,
                                  open_timeout=None,
                                  ping_timeout=None)
    # send the message to the server
    await ws.send(json.dumps(msg))
    last_token_send_time = time.time()

    # listen for messages from the server forever
    while True:
        response = await ws.recv()
        # Parse the response as JSON
        response_json = json.loads(response)

        if 'inference' in response_json:
            # print the number of inferences received
            print(f"{len(response_json['inference'])} inferences received")
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
