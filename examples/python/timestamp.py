import asyncio
import json
from sys import argv
import websockets
import traceback
from authenticate import authenticate_user
from cusips_to_figis import openfigi_map_cusips_to_figis


async def main():
    if len(argv) != 4:
        print('Usage: python api_client_timestamp_sample.py <Deep MM dev username> <password> <openfigi_api_key>')
        exit()

    username = argv[1]
    password = argv[2]
    # Open FIGI API key
    _API_KEY = argv[3]

    cusip_to_figi, figi_to_cusip = openfigi_map_cusips_to_figis(_API_KEY,   ['594918BJ2', '594918AR5'])

    print("Mapping of CUSIPs to FIGIs complete\nCalling Deep MM API with FIGIs")

    msg = {
        'inference': [
            {
                'rfq_label': 'spread',
                'figi': cusip_to_figi['594918BJ2'],
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'timestamp': ['2023-11-01T15:10:07.661Z', '2023-11-02T15:10:07.661Z'],
                'subscribe': False,
            },
            {
                'rfq_label': 'price',
                'figi': cusip_to_figi['594918AR5'],
                'quantity': 1_000_000,
                'side': 'dealer',
                'ats_indicator': "N",
                'timestamp': ['2023-11-02T15:10:07.661Z', '2023-11-02T15:10:07.661Z'],
                'subscribe': False,
            },
            {
                'rfq_label': 'spread',
                'figi': cusip_to_figi['594918BJ2'],
                'quantity': 1_000_000,
                'side': 'offer',
                'ats_indicator': "Y",
                'timestamp': ['2023-11-02T15:10:07.661Z', '2023-11-02T15:10:07.661Z'],
                'subscribe': False,
            },
        ]
    }

    # Percentiles from 5 to 95 in steps of 5
    percentiles = [f for f in range(5, 100, 5)]

    # Index of 50th percentile:
    percentile_50_index = percentiles.index(50)

    labels = ['price', 'spread']

    while True:
        try:
            msg['token'] = authenticate_user(username, password)
            # The equivalent of create_connection in the websocket library is the connect function
            # ws = create_connection("wss://staging1.deepmm.com")
            ws = await websockets.connect("wss://staging1.deepmm.com")
            await ws.send(json.dumps(msg))
            while True:
                response = await ws.recv()
                # Parse the response as JSON
                response_json = json.loads(response)

                if 'message' in response_json and response_json['message'] == 'deactivated':
                    await ws.close()
                    break

                # Filter each price list to keep only the 50th percentile value
                for item in response_json['inference']:
                    for label in labels:
                        if label in item:
                            item[label] = item[label][percentile_50_index]
                            item['cusip'] = figi_to_cusip[item['figi']]

                # Pretty print the JSON
                pretty_response = json.dumps(response_json, indent=4)
                print("Pretty Printed Response:", pretty_response)
                await asyncio.sleep(1)
        except Exception as e:
            print("An error occurred:", str(e))
            print(response_json)
            traceback.print_exc()
            await ws.close()
            print("Retrying in 30 seconds")
            asyncio.sleep(30)


if __name__ == '__main__':
    asyncio.run(main())
