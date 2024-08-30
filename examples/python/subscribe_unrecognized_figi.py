import asyncio
import json
from sys import argv
import websockets
import traceback
from authenticate import authenticate_user

async def main():
    if len(argv) < 3:
        print('Usage: python api_client_timestamp_sample.py <Deep MM dev username> <password>')
        exit()

    username = argv[1]
    password = argv[2]

    print("Mapping of CUSIPs to FIGIs complete\nCalling Deep MM API with FIGIs")

    msg = {
        'inference': [
            {
                'rfq_label': 'gspread',
                'figi': 'BBG006F8RW84', # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'gspread',
                'figi': 'BBG00KHV1HM5',  # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'gspread',
                'figi': 'BBG00P35JY86',  # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'gspread',
                'figi': 'BBG00P35JYN9',  # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'gspread',
                'figi': 'BBG00P2S1QD7',  # FIGI outside of our current universe
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'price',
                'figi': 'BBG00BBHSZG0',
                'quantity': 1_000_000,
                'side': 'dealer',
                'ats_indicator': "N",
                'subscribe': True,
            },
            {
                'rfq_label': 'gspread',
                'figi': "BBG003LZRTD5",
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

    # !! NOTE: when we say gspread we actually mean spread. Eventually this
    # will be fixed in the API, but at the moment what the API calls
    # gspread is actually the spread.
    labels = ['price', 'gspread']

    while True:
        try:
            msg['token'] = authenticate_user(username, password)
            ws = await websockets.connect("wss://staging1.deepmm.com")
            await ws.send(json.dumps(msg))
            while True:
                response = await ws.recv()
                # Parse the response as JSON
                response_json = json.loads(response)

                if 'message' in response_json and response_json['message'] == 'deactivated':
                    await ws.close()
                    break

                if 'inference' not in response_json:
                    print("Received unexpected response:", response_json)
                    continue
                # Filter each price list to keep only the 50th percentile value
                for item in response_json['inference']:
                    for label in labels:
                        if label in item:
                            item[label] = item[label][percentile_50_index]

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
