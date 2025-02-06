# Bare minimum script to subscribe to the Deep MM API and write the responses to the console

import asyncio
import json
from sys import argv
import time

from authentication import create_get_id_token
from connection import connect


async def main():
    if len(argv) != 5:
        print('Usage: python subscribe_simple.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password>')
        print('See README for additional details')
        exit()

    region = argv[1]
    client_id = argv[2]
    username = argv[3]
    password = argv[4]
    get_id_token = create_get_id_token(region, client_id, username, password)

    # create the subscription message
    msg = {
        'token': get_id_token(),
        'inference': [
            {
                'rfq_label': 'spread',
                'figi': 'BBG003LZRTD5',
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True
            },  # add additional inference requests here (up to the throttling limits)
        ]
    }
    # open a WebSocket connection to the server
    ws = await connect()
    # send the message to the server
    await ws.send(json.dumps(msg))
    last_token_send_time = time.time()

    # listen for messages from the server forever
    while True:
        # wait for a response from the server
        response = await ws.recv()
        # Parse the response as JSON
        response_json = json.loads(response)

        # Pretty print the JSON
        pretty_response = json.dumps(response_json, indent=4)
        print("Pretty Printed Response:", pretty_response)

        # periodically send an updated token to the server so our session does not expire
        # NOTE: the server does send a response to a message with only an updated token
        if time.time() - last_token_send_time > 60:
            await ws.send(json.dumps({ 'token': get_id_token() }))
            last_token_send_time = time.time()

        # Sample Response:
        # {
        #     "inference": [
        #         {
        #             "ats_indicator": "N",
        #             "date": "2023-11-01T15:10:07.661Z",
        #             "figi": "BBG003LZRTD5",
        #             "quantity": 1000000,
        #             "side": "bid",
        #             "spread": [
        #                 36.19638681411743, # 5th percentile
        #                 37.01240122318268, # 10th percentile
        #                 37.50055134296417, # 15th percentile
        #                 37.845322489738464, # 20th percentile
        #                 38.11945021152496, # 25th percentile
        #                 38.37002217769623, # 30th percentile
        #                 38.57978284358978, # 35th percentile
        #                 38.74189555644989, # 40th percentile
        #                 38.95164430141449, # 45th percentile
        #                 39.14642632007599, # 50th percentile
        #                 39.34023380279541, # 55th percentile
        #                 39.53405320644379, # 60th percentile
        #                 39.71298336982727, # 65th percentile
        #                 39.924341440200806, # 70th percentile
        #                 40.156757831573486, # 75th percentile
        #                 40.4340386390686, # 80th percentile
        #                 40.763866901397705, # 85th percentile
        #                 41.286712884902954, # 90th percentile
        #                 42.06854701042175 # 95th percentile
        #             ],
        #             "tenor": 20 # This is the on-the-run treasury tenor that was used to generate the spread percentiles
        #         }
        #     ]
        # }


if __name__ == '__main__':
    asyncio.run(main())
