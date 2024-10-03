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

    template = {
                'rfq_label': 'spread',
                'figi': cusip_to_figi['594918BJ2'],
                'quantity': 1_000_000,
                'side': 'bid',
                'ats_indicator': "N",
                'subscribe': True,
            }

    while True:
        try:
            token = authenticate_user(username, password)
            ws = await websockets.connect("wss://staging1.deepmm.com", max_size=10 ** 8, timeout=120)

            # Iterate over 4,000 values to add to the quantity, adding each value to the message
            inferences = []
            for i in range(4_000):
                template['quantity'] = 1_000_000 + i
                inferences.append(template.copy())

            msg = {
                'token': token,
                'inference': inferences
            }

            await ws.send(json.dumps(msg))
            while True:
                response = await ws.recv()
                # Parse the response as JSON
                response_json = json.loads(response)

                # Print the keys of the top level of the response
                print("\n", len(response_json['inference']))

                min_quantity = 1_000_000_000
                max_quantity = 0
                for inference in response_json['inference']:
                    if inference['quantity'] < min_quantity:
                        min_quantity = inference['quantity']
                    if inference['quantity'] > max_quantity:
                        max_quantity = inference['quantity']
                print("quantity min max: ", min_quantity, max_quantity)

                if 'message' in response_json and response_json['message'] == 'deactivated':
                    await ws.close()
                    break
        except Exception as e:
            print("An error occurred:", str(e))
            print(response_json)
            traceback.print_exc()
            await ws.close()
            print("Retrying in 30 seconds")
            await asyncio.sleep(30)


if __name__ == '__main__':
    asyncio.run(main())
