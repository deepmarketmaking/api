# Bare minimum script to call the Deep MM API and write the response to the console

import asyncio
import json
from sys import argv
import websockets
from authenticate import authenticate_user


async def main():
    username = "Your Account E-Mail Address"
    password = "Your Password"

    msg = {'inference': [
        {
            'rfq_label': 'gspread',
            'figi': 'BBG003LZRTD5',
            'quantity': 1_000_000,
            'side': 'bid',
            'ats_indicator': "N",
            'timestamp': ['2023-11-01T15:10:07.661Z'],
            # You can supply as many timestamps as you want here to receive historical inferences
            'subscribe': False,
        },  # You can list as many inference requests as you want here (up to the throttling limits).
    ], 'token': authenticate_user(username, password)}

    ws = await websockets.connect("wss://staging1.deepmm.com")
    await ws.send(json.dumps(msg))

    # We loop receiving messages because this is a websocket connection, so responses
    # come asynchronously on their own schedule and not necessarily all together.
    while True:
        response = await ws.recv()
        # Parse the response as JSON
        response_json = json.loads(response)

        # Pretty print the JSON
        pretty_response = json.dumps(response_json, indent=4)
        print("Pretty Printed Response:", pretty_response)

        # Sample Response:
        # {
        #     "inference": [
        #         {
        #             "ats_indicator": "N",
        #             "date": "2023-11-01T15:10:07.661Z",
        #             "figi": "BBG003LZRTD5",
        #             "quantity": 1000000,
        #             "side": "bid",
        #             "gspread": [ # !! This is actually spread, NOT gspread -- due to a miscommunication, the field name is incorrectly called gspread. We will fix this label in a later release.
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
        await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(main())
