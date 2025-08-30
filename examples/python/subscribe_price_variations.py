import asyncio
import json
from sys import argv
import time
import itertools
import httpx
def openfigi_map_isins_to_figis(api_key, isin_list):
    # Similar to cusips_to_figis but for ISINs
    _MAX_JOBS_PER_REQUEST = 90
    _MIN_REQUEST_INTERVAL = 0.5
    _last_response_time_dict = {'last_response_time': 0}
    _MAX_RETRY_RUNTIME = 1800
    retry_stop_time = time.time() + _MAX_RETRY_RUNTIME

    def _map_jobs(jobs, retry_stop_time):
        url = 'https://api.openfigi.com/v3/mapping'
        headers = {'Content-Type': 'text/json', 'X-OPENFIGI-APIKEY': api_key}
        batch = []

        def process_batch():
            if batch:
                interval = time.time() - _last_response_time_dict['last_response_time']
                if interval < _MIN_REQUEST_INTERVAL:
                    time.sleep(_MIN_REQUEST_INTERVAL - interval)
                for attempt in Retrying(
                        stop=stop_after_delay(max(0, retry_stop_time - time.time())),
                        wait=wait_fixed(6) + wait_random(0, 4)):
                    with attempt:
                        response = httpx.post(url=url, headers=headers, json=batch, timeout=30)
                        if response.status_code != httpx.codes.OK:
                            print(f'OpenFIGI status_code not OK: {response.status_code}')
                            raise Exception(f'OpenFIGI status_code not OK: {response.status_code}')
                _last_response_time_dict['last_response_time'] = time.time()
                results = response.json()
                for job, result in zip(batch, results):
                    yield (job, result)
            batch.clear()

        for job in jobs:
            batch.append(job)
            if len(batch) >= _MAX_JOBS_PER_REQUEST:
                for pair in process_batch():
                    yield pair
        for pair in process_batch():
            yield pair

    print("Mapping list of ISINs to FIGIs using OpenFIGI API")

    open_figi_data = {'isin': [], 'figi': []}
    for i, (job, result) in enumerate(
            _map_jobs(({"idType": "ID_ISIN", "idValue": i} for i in isin_list), retry_stop_time)):
        if 'warning' in result:
            print(f'''OpenFigi warning for request "{job}": "{result['warning']}"''')
        if 'data' in result:
            if len(result['data']) != 1:
                print(f'''OpenFigi unexpected response for request "{job}": "{result['data']}"''')
            else:
                open_figi_data['figi'].append(result['data'][0]['figi'])
                open_figi_data['isin'].append(job['idValue'])

    # Create dictionaries
    isin_to_figi = dict(zip(open_figi_data['isin'], open_figi_data['figi']))
    figi_to_isin = dict(zip(open_figi_data['figi'], open_figi_data['isin']))

    return isin_to_figi, figi_to_isin

from tenacity import Retrying, stop_after_delay, wait_fixed, wait_random

from authentication import create_get_id_token
from connection import connect

async def main():
    if len(argv) != 7:
        print('Usage: python subscribe_price_variations.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password> <openfigi_api_key> <isins_file>')
        print('See README for additional details')
        exit()

    region = argv[1]
    client_id = argv[2]
    username = argv[3]
    password = argv[4]
    # Open FIGI API key
    _API_KEY = argv[5]
    isins_file = argv[6]

    # Read ISINs from file
    with open(isins_file, 'r') as f:
        isins = [line.strip() for line in f if line.strip()]

    get_id_token = create_get_id_token(region, client_id, username, password)

    # Map ISINs to FIGIs
    isin_to_figi, figi_to_isin = openfigi_map_isins_to_figis(_API_KEY, isins)

    print("Mapping of ISINs to FIGIs complete\nCalling Deep MM API with FIGIs")

    # Define variations

    # All sides:
    # sides = ['bid', 'offer', 'dealer']
    # Sides we need: 
    sides = ['bid', 'offer']
    ats_indicators = ['Y', 'N']
    # All standardized quantities: 
    # quantities = [1_000, 10_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000]
    # Needed quantities
    quantities = [10_000, 100_000, 250_000, 500_000, 1_000_000]

    rfq_labels = ['spread', 'price']

    # Generate all combinations
    inference_list = []
    for isin in isins:
        figi = isin_to_figi.get(isin)
        if not figi:
            continue
        for side, ats, qty, label in itertools.product(sides, ats_indicators, quantities, rfq_labels):
            inference_list.append({
                'rfq_label': label,
                'figi': figi,
                'quantity': qty,
                'side': side,
                'ats_indicator': ats,
                'subscribe': True,
            })
    
    print(f"Total number of inference requests: {len(inference_list)}")

    msg = {
        'token': get_id_token(),
        'inference': inference_list
    }

    # Percentiles from 5 to 95 in steps of 5
    percentiles = [f for f in range(5, 100, 5)]

    labels = ['price', 'spread']

    # open a WebSocket connection to the server
    #ws = await connect('wss://gc2.deepmm.com')
    ws = await connect('wss://staging1.deepmm.com')
    #ws = await connect()
    # send the message to the server
    await ws.send(json.dumps(msg))
    # keep track of the last time we sent a token to the server
    last_token_send_time = time.time()

    # Open files for writing
    with open('responses.jsonl', 'a') as response_file, open('no_inference_responses.jsonl', 'a') as no_inference_file:
        # listen for messages from the server forever
        while True:
            # wait for a response from the server
            response = await ws.recv()
            # Parse the response as JSON
            response_json = json.loads(response)

            if 'inference' in response_json:
                # Keep all percentiles
                for item in response_json['inference']:
                    for label in labels:
                        if label in item:
                            item['isin'] = figi_to_isin.get(item['figi'], 'unknown')
                # Write to responses file
                response_file.write(json.dumps(response_json) + '\n')
                response_file.flush()
            else:
                # Write to no inference file
                no_inference_file.write(json.dumps(response_json) + '\n')
                no_inference_file.flush()

            # periodically send an updated token to the server so our session does not expire
            # NOTE: the server does send a response to a message with only an updated token
            if time.time() - last_token_send_time > 60:
                await ws.send(json.dumps({ 'token': get_id_token() }))
                last_token_send_time = time.time()


if __name__ == '__main__':
    asyncio.run(main())
