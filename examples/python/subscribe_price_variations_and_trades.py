import asyncio
import json
from sys import argv
import time
import itertools
import httpx
from tenacity import Retrying, stop_after_delay, wait_fixed, wait_random

from authentication import create_get_id_token
from connection import connect

SERVER = 'wss://molyneux.deepmm.com'

async def token_sender(ws_inference, ws_trades, get_id_token):
    while True:
        await asyncio.sleep(60)
        token_msg = json.dumps({'token': get_id_token()})
        try:
            if ws_inference:
                await ws_inference.send(token_msg)
        except:
            pass
        try:
            if ws_trades:
                await ws_trades.send(token_msg)
        except:
            pass

async def heartbeat_sender(ws):
    while True:
        await asyncio.sleep(30)
        try:
            await ws.ping()
        except:
            break

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

async def main():
    if len(argv) != 7:
        print('Usage: python subscribe_price_variations_and_trades.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password> <openfigi_api_key> <isins_file>')
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

    print("Mapping of ISINs to FIGIs complete\nSubscribing to price variations and trades")

    # Define variations for inference
    sides = ['bid', 'offer']
    ats_indicators = ['Y', 'N']
    quantities = [10_000, 100_000, 250_000, 500_000, 1_000_000]
    rfq_labels = ['price']

    # Generate all combinations for inference
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

    # Build trade subscription list
    trade_list = []
    for isin in isins:
        figi = isin_to_figi.get(isin)
        if not figi:
            continue
        trade_list.append({
            'figi': figi,
            'subscribe': True,
            'include_inference': True
        })

    inference_msg = {
        'token': get_id_token(),
        'inference': inference_list
    }

    trade_msg = {
        'token': get_id_token(),
        'trade': trade_list
    }

    # Percentiles from 5 to 95 in steps of 5
    percentiles = [f for f in range(5, 100, 5)]

    labels = ['price', 'spread']

    # open two WebSocket connections to the server
    ws_inference = await connect(SERVER)
    ws_trades = await connect(SERVER)
    # send the messages to the servers
    await ws_inference.send(json.dumps(inference_msg))
    await ws_trades.send(json.dumps(trade_msg))

    # Create tasks for token and heartbeat
    token_task = asyncio.create_task(token_sender(ws_inference, ws_trades, get_id_token))
    heartbeat_inference_task = asyncio.create_task(heartbeat_sender(ws_inference))
    heartbeat_trades_task = asyncio.create_task(heartbeat_sender(ws_trades))

    # Open files for writing
    with open('responses.jsonl', 'a') as response_file, open('no_inference_responses.jsonl', 'a') as no_inference_file, open('trades.jsonl', 'a') as trades_file:
        # listen for messages from both servers forever
        while True:
            try:
                # Wait for message from either websocket
                done, pending = await asyncio.wait(
                    [ws_inference.recv(), ws_trades.recv()],
                    return_when=asyncio.FIRST_COMPLETED
                )
                # Cancel pending
                for task in pending:
                    task.cancel()
                # Get the response
                response = done.pop().result()
                # Parse the response as JSON
                response_json = json.loads(response)

                if response_json.get('message') in ['forbidden', 'deactivated']:
                    print(f"Received {response_json['message']} message, reconnecting both connections...")
                    # Cancel tasks
                    token_task.cancel()
                    heartbeat_inference_task.cancel()
                    heartbeat_trades_task.cancel()
                    # Reconnect both
                    ws_inference = await connect(SERVER)
                    ws_trades = await connect(SERVER)
                    inference_msg['token'] = get_id_token()
                    trade_msg['token'] = get_id_token()
                    await ws_inference.send(json.dumps(inference_msg))
                    await ws_trades.send(json.dumps(trade_msg))
                    # Send updated token to both
                    token_msg = json.dumps({'token': get_id_token()})
                    await ws_inference.send(token_msg)
                    await ws_trades.send(token_msg)
                    # Recreate tasks
                    token_task = asyncio.create_task(token_sender(ws_inference, ws_trades, get_id_token))
                    heartbeat_inference_task = asyncio.create_task(heartbeat_sender(ws_inference))
                    heartbeat_trades_task = asyncio.create_task(heartbeat_sender(ws_trades))
                    continue

                if 'inference' in response_json:
                    # Keep all percentiles
                    for item in response_json['inference']:
                        for label in labels:
                            if label in item:
                                item['isin'] = figi_to_isin.get(item['figi'], 'unknown')
                    # Write to responses file
                    response_file.write(json.dumps(response_json) + '\n')
                    response_file.flush()
                elif 'trade' in response_json:
                    # Add ISIN to each trade
                    for trade in response_json['trade']:
                        trade['isin'] = figi_to_isin.get(trade['figi'], 'unknown')
                    # Write to trades file
                    trades_file.write(json.dumps(response_json) + '\n')
                    trades_file.flush()
                else:
                    # Write to no inference file
                    no_inference_file.write(json.dumps(response_json) + '\n')
                    no_inference_file.flush()
            except Exception as e:
                print(f"Connection error: {e}")
                # Cancel tasks
                token_task.cancel()
                heartbeat_inference_task.cancel()
                heartbeat_trades_task.cancel()
                # Reconnect both
                ws_inference = await connect(SERVER)
                ws_trades = await connect(SERVER)
                inference_msg['token'] = get_id_token()
                trade_msg['token'] = get_id_token()
                await ws_inference.send(json.dumps(inference_msg))
                await ws_trades.send(json.dumps(trade_msg))
                # Send updated token to both
                token_msg = json.dumps({'token': get_id_token()})
                await ws_inference.send(token_msg)
                await ws_trades.send(token_msg)
                # Recreate tasks
                token_task = asyncio.create_task(token_sender(ws_inference, ws_trades, get_id_token))
                heartbeat_inference_task = asyncio.create_task(heartbeat_sender(ws_inference))
                heartbeat_trades_task = asyncio.create_task(heartbeat_sender(ws_trades))


if __name__ == '__main__':
    asyncio.run(main())