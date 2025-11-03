import asyncio
import json
from sys import argv
import time

from authentication import create_get_id_token
from connection import connect
from cusips_to_figis import openfigi_map_cusips_to_figis

async def main():
    if len(argv) != 6:
        print('Usage: python subscribe.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password> <openfigi_api_key>')
        print('See README for additional details')
        exit()

    region = argv[1]
    client_id = argv[2]
    username = argv[3]
    password = argv[4]
    # Open FIGI API key
    _API_KEY = argv[5]

    get_id_token = create_get_id_token(region, client_id, username, password)

    cusip_to_figi, figi_to_cusip = openfigi_map_cusips_to_figis(_API_KEY,   ['594918BJ2', '594918AR5'])

    print("Mapping of CUSIPs to FIGIs complete\nCalling Deep MM API with FIGIs")

    msg = {
        'token': get_id_token(),
        'inference': [
            {
                'rfq_label': 'spread',
                'figi': cusip_to_figi['594918BJ2'],
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'price',
                'figi': cusip_to_figi['594918AR5'],
                'quantity': 1_000_000,
                'side': 'dealer',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'spread',
                'figi': cusip_to_figi['594918BJ2'],
                'quantity': 1_000_000,
                'side': 'offer',
                'ats_indicator': "Y",
                'subscribe': True,
            },
        ]
    }

    # Percentiles from 5 to 95 in steps of 5
    percentiles = [f for f in range(5, 100, 5)]

    # Index of 50th percentile:
    percentile_50_index = percentiles.index(50)

    labels = ['price', 'spread']

    # open a WebSocket connection to the server
    ws = await connect()
    # send the message to the server
    await ws.send(json.dumps(msg))
    # keep track of the last time we sent a token to the server
    last_token_send_time = time.time()

    # listen for messages from the server forever
    while True:
        # wait for a response from the server
        response = await ws.recv()
        # Parse the response as JSON
        response_json = json.loads(response)

        if 'inference' in response_json:
            # Filter each price list to keep only the 50th percentile value
            for item in response_json['inference']:
                for label in labels:
                    if label in item:
                        item[label] = item[label][percentile_50_index]
                        item['cusip'] = figi_to_cusip[item['figi']]

        # Pretty print the JSON
        pretty_response = json.dumps(response_json, indent=4)
        print("Pretty Printed Response:", pretty_response)

        # periodically send an updated token to the server so our session does not expire
        # NOTE: the server does send a response to a message with only an updated token
        if time.time() - last_token_send_time > 60:
            await ws.send(json.dumps({ 'token': get_id_token() }))
            last_token_send_time = time.time()


if __name__ == '__main__':
    asyncio.run(main())
