import asyncio
import json
import sys
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

            print(f"Received {len(response_json['inference'])} inferences")

            await asyncio.sleep(1)
    except Exception as e:
        print("An error occurred:", str(e))
        print(response_json)
        traceback.print_exc()
    finally:
        await ws.close()
        asyncio.sleep(30)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
