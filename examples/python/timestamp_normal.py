import asyncio
import json
from sys import argv
import websockets
import traceback
from authenticate import authenticate_user
from cusips_to_figis import openfigi_map_cusips_to_figis
from fit_normal_distribution import fit_normal_distribution
from scipy.stats import norm


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
                # !! NOTE: when we say gspread we actually mean spread. Eventually this
                # will be fixed in the API, but at the moment what the API calls
                # gspread is actually the spread.
                'rfq_label': 'gspread',
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
                'rfq_label': 'gspread',
                'figi': cusip_to_figi['594918BJ2'],
                'quantity': 1_000_000,
                'side': 'offer',
                'ats_indicator': "Y",
                'timestamp': ['2023-11-02T15:10:07.661Z', '2023-11-02T15:10:07.661Z'],
                'subscribe': False,
            },
        ]
    }

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
                    ws.close()
                    break

                # Fit a normal distribution to the percentiles
                for item in response_json['inference']:
                    # Pretty print the JSON
                    pretty_response = json.dumps(item, indent=4)
                    print("Inference:", pretty_response)

                    # !! NOTE: when we say gspread we actually mean spread. Eventually this
                    # will be fixed in the API, but at the moment what the API calls
                    # gspread is actually the spread.
                    if 'gspread' in item:
                        percentile_values = item['gspread']
                    elif 'price' in item:
                        percentile_values = item['price']

                    percentiles = [f for f in range(5, 100, 5)]
                    print("Percentiles: ", percentiles)
                    print("Percentile Values: ", percentile_values)

                    # Fit a normal distribution to the percentiles, percentile values
                    # and return the mean and standard deviation
                    mean, std, best_fit_error = fit_normal_distribution(percentiles, percentile_values)
                    print("Mean: ", mean)
                    print("Standard Deviation: ", std)
                    print("Best Fit Error for normal distribution: ", best_fit_error)

                    # Now we can show how to query the normal distribution for a given price and see what the probability is
                    query_value = mean + 2 * std
                    print("Query Value: ", query_value)
                    probability = norm.cdf(query_value, loc=mean, scale=std)
                    print("Probability that price or spread is below the query value: ", probability)

                await asyncio.sleep(1)
        except Exception as e:
            print("An error occurred:", str(e))
            print(response_json)
            traceback.print_exc()
            ws.close()
            print("Retrying in 30 seconds")
            asyncio.sleep(30)


if __name__ == '__main__':
    asyncio.run(main())