import asyncio
import json
from sys import argv

from authentication import create_get_id_token
from connection import connect
from cusips_to_figis import openfigi_map_cusips_to_figis
from fit_normal_distribution import fit_normal_distribution
from scipy.stats import norm


async def main():
    if len(argv) != 6:
        print('Usage: python timestamp_normal.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password> <openfigi_api_key>')
        print('See README for additional details')
        exit()

    region = argv[1]
    client_id = argv[2]
    username = argv[3]
    password = argv[4]
    # Open FIGI API key
    _API_KEY = argv[5]

    get_id_token = create_get_id_token(region, client_id, username, password)

    cusip_to_figi, _ = openfigi_map_cusips_to_figis(_API_KEY,   ['594918BJ2', '594918AR5'])

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

    # open a WebSocket connection to the server
    ws = await connect()
    # send the message to the server
    await ws.send(json.dumps(msg))

    # wait for a response from the server
    response = await ws.recv()
    # Parse the response as JSON
    response_json = json.loads(response)

    if 'inference' in response_json:
        # Fit a normal distribution to the percentiles
        for item in response_json['inference']:
            # Pretty print the JSON
            pretty_response = json.dumps(item, indent=4)
            print("Inference:", pretty_response)

            if 'spread' in item:
                percentile_values = item['spread']
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
    else:
        # if the response is missing 'inference' then just pretty print the response
        print(json.dumps(response_json, indent=4))

    # close the WebSocket
    await ws.close()


if __name__ == '__main__':
    asyncio.run(main())
