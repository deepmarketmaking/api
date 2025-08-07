# Deep MM API for Real-time and Historical Pricing

## Introduction

Our (currently US Only) Corporate Credit AI pricing engine is able [to infer](https://www.cloudflare.com/learning/ai/inference-vs-training/#:~:text=In%20the%20field%20of%20artificial,examples%20of%20the%20desired%20result.) the probability distribution of hypothetical trades on the secondary market [conditioned on](https://en.wikipedia.org/wiki/Conditional_probability) properties of the trade knowable before the trade, and also conditioned on a trade occuring at the specified point in time:

- **FIGI**: the bond identifier, with an easy lookup from the CUSIP)
- **Label**: "price", "spread", or "ytm". What do you want the model to predict? (Generally price, spread, or yield to maturity (YTM), with plans for adding other labels in the future such as option-adjusted spread). 
- **Quantity**: How big of a hypothetical trade is it? Valid values range from 1 to 5,000,000, the later being the maximum reported by the commercial TRACE feed (the academic historical data has the actual sizes, but we're not allowed to use it).
- **Side**: "bid", "offer", or "dealer", as reported by trace (simplified from the two-field values reported by TRACE).
- **ATS Indicator**: "Y","N", default "N". This indicates whether you want to assume the trade is happening on an alternative trading service. This field is optional.
- **Timestamp**: List of strings in the [ISO 8601](https://en.wikipedia.org/wiki/ISO_8601) UTC timestamp format (example '2023-11-01T15:10:07.661Z' -- the Z indicates that it is UTC. This timestamp example expresses November 1st, 2023 at 10:07.661 AM US/Eastern), for which you want to get historical price, spread, or ytm probability distributions. Any timestamp greater than January 1st, 2019 is valid (as that is how far back we have historical data inputs for our AI model). This field is optional. Typically if you only want the current inference values, then you would not include this field.

You can also specify whether you want to subscribe to the inference. If you subscribe then you will receive updates at regular intervals while you maintain the websocket connection. 

The output of the model currently is the inferred 5th through the 95th percentiles of the label specified (5th being the lowest value and 95th being the highest). The percentiles are a table of select values in the AI-estimated [cumulative distribution function](https://en.wikipedia.org/wiki/Cumulative_distribution_function) of the label values. We do have plans to modify our API in the future to enable more percentiles, particularly in the tails. In our web application, we use simple linear interpolation between percentiles as needed to go from a specific label value to its probability. Another option for getting the probability of a label value perhaps more precisely or further into the tails than we currently model, is to fit a distribution to the percentiles returned from the API, and then query that distribution to get the [cumulative probability](https://en.wikipedia.org/wiki/Cumulative_distribution_function) of the value.  Examples on how to do this are in the following scripts:

- **[Normal Distribution](https://en.wikipedia.org/wiki/Normal_distribution)**: [examples/python/timestamp_normal.py](examples/python/timestamp_normal.py)
- **[Johnson SU Distribution](https://en.wikipedia.org/wiki/Johnson%27s_SU-distribution)**: [examples/python/timestamp_johnson_su.py](examples/python/timestamp_johnson_su.py)

## Universe

We don't cover all bonds yet but we are working hard to increase our coverage. You can see the list of bonds that we cover [in this file downloadable here](https://s3.us-east-1.amazonaws.com/deepmm.public/universe.txt) (it's updated every night).

## Getting Started
To begin using the API, follow these steps:

1. **Install Dependencies**: Install the necessary dependencies listed in requirements.txt by running:

   ```bash
   pip install -r requirements.txt
   ```
   The main libraries used are:

   - `websockets`: For WebSocket communication.
   - `httpx`: For HTTP requests to the FIGI webservice to translate your cusips to figis(optional, depending on your implementation).
   - `tenacity`: For handling retries with resilience.
   - `pyarrow`: For efficient data handling.

2. **Authentication**

   - `Deep MM Websocket Authentication`:
      - You will need a currently active Deep MM username and password for API access
      - We use the standard AWS client (called boto3 in python) to connect to Cognito and obtain the IdToken that we have to send on the WebSocket connection once established
      - We have also included [example code in this repository](examples/python/authentication.py) on how to authenticate and obtain the Cognito IdToken used to authenticate once connected to the WebSocket server
      - Once you have the IdToken from Cognito, you just send it to the Websocket server once the connection is established
      - An updated token must be sent to the WebSocket server periodically in order to keep the session from expiring
      - You can have up to five connections opened simultaneously, but in order to open more than one connection you must use the same Cognito IdToken for all of them
      - You can use a new IdToken to establish a new connection, but all previous connections for the same user will be disconnected
   - `OpenFIGI Authentication`: If you want to make use of the [OpenFIGI api](https://www.openfigi.com/api) to convert your list of CUSIPs over to FIGIs as shown in some of the examples in this repository, you will need [to register](https://www.openfigi.com/user/signup) (for free) and obtain an OpenFIGI API key for your organization.

3. **API Server Connection Settings**:
   Use a WebSocket client to connect to the WebSocket Server. We recommend the Python `websockets` library. See the examples in the repository for more details.
   - Use the following settings to connect:
      - WebSocket server: `wss://api.deepmm.com`
      - AWS Region: `us-east-1`
      - Cognito Client ID:
        - While testing use `2so174j2e4fsg1m28kc9id3hgk`
        - For production deployments contact us for a dedicated Cognito Client ID

4. **Batching**: When submitting requests to the websocket server for historical inferences, it's important to batch them into as large as possible messages (while staying under the throttling limits). Our server has much better throughput for historical inferences with large rather than small batches. If you run into websocket client message size limits, here's an example of how to set up the connection with larger limits:

   ```python
    import websockets

    ws = await websockets.connect("wss://api.deepmm.com",
                                  max_size=10 ** 8,
                                  open_timeout=None,
                                  ping_timeout=None)
   ```

   It's also generally a good idea to submit subscription requests in larger batches, but it's not quite as important because the subscriptions for your connection are eventually consolidated into a single list automatically on the server side. 

6. **Throttling**: At the time of this writing each customer can subscribe to up 32,000 simultaneous subscriptions, or 32,000 historical timestamp requests within a 30-second window. We are working hard to increase this limit further, especially for users willing to use one of the standardized sizes (expressed here in python scalar format) (which allows us to infer once and send out to multiple users, thus decreasing the required inference load on our servers):

   - 1,000
   - 10,000
   - 100,000
   - 250,000
   - 500,000
   - 1,000,000
   - 2,000,000
   - 3,000,000
   - 4,000,000
   - 5,000,000

## Subscribing

Suppose that I wanted to receive a regularly updating feed for a bond with figi `BBG003LZRTD5`, then I could create a websocket request message like this (in python json format):

```python
    {'inference': [
        {
            'rfq_label': 'spread',
            'figi': 'BBG003LZRTD5',
            'quantity': 1_000_000,
            'side': 'bid',
            'ats_indicator': 'N',
            'subscribe': True,
        },  # You can list as many inference requests as you want here (up to the throttling limits).
    ]}
```
This creates an inference request which will cause the server to send regular updates for the spread of this bond, conditioned on the trade for the bond being for 1,000,000 in size, the dealer is buying the bond, and is not being traded on an ATS. Notice there are a list of inferences. Let's say instead we wanted to get both sides of the market, and we also want to get the spread both when the trade is 1 MM as well as 100,000, then we just add some more subscription requests to the list:

```python
    {'inference': [
        {
            'rfq_label': 'spread',
            'figi': 'BBG003LZRTD5',
            'quantity': 1_000_000,
            'side': 'bid',
            'ats_indicator': 'N',
            'subscribe': True,
        },
        {
            'rfq_label': 'spread',
            'figi': 'BBG003LZRTD5',
            'quantity': 1_000_000,
            'side': 'offer',
            'ats_indicator': 'N',
            'subscribe': True,
        },
        {
            'rfq_label': 'spread',
            'figi': 'BBG003LZRTD5',
            'quantity': 100_000,
            'side': 'bid',
            'ats_indicator': 'N',
            'subscribe': True,
        },
        {
            'rfq_label': 'price',
            'figi': 'BBG003LZRTD5',
            'quantity': 100_000,
            'side': 'offer',
            'ats_indicator': 'N',
            'subscribe': True,
        },
    ]}
```

Here's a sample response:

```python
    "inference": [
        {
            "ats_indicator": "N",
            "date": "2025-08-07T12:59:28.846Z",
            "figi": "BBG003LZRTD5",
            "quantity": 1000000,
            "side": "bid",
            "spread": [
                -22.91455864906311,
                -7.083559036254883,
                2.160295844078064,
                8.799150586128235,
                14.376422762870789,
                18.862897157669067,
                23.15084934234619,
                26.953154802322388,
                30.642613768577576,
                34.11840796470642,
                37.46683597564697,
                40.637338161468506,
                43.72316598892212,
                46.88047468662262,
                50.239020586013794,
                53.98953557014465,
                58.43271017074585,
                64.13162350654602,
                74.54012632369995
            ],
            "tenor": 2,
            "treasury_cusip": "91282CNQ0",
            "cusip": "594918BJ2"
        },
        {
            "ats_indicator": "Y",
            "date": "2025-08-07T12:59:28.846Z",
            "figi": "BBG003LZRTD5",
            "quantity": 1000000,
            "side": "offer",
            "spread": [
                -41.308724880218506,
                -24.528831243515015,
                -14.819729328155518,
                -7.663071155548096,
                -1.518470048904419,
                3.519865870475769,
                8.44331979751587,
                12.850263714790344,
                17.133909463882446,
                21.212029457092285,
                25.10717809200287,
                28.9124995470047,
                32.68296420574188,
                36.629754304885864,
                40.91789126396179,
                45.74577212333679,
                51.37031078338623,
                58.68079662322998,
                71.77832126617432
            ],
            "tenor": 2,
            "treasury_cusip": "91282CNQ0",
            "cusip": "594918BJ2"
        },
        {
            "ats_indicator": "Y",
            "date": "2025-08-07T12:59:28.846Z",
            "figi": "BBG003LZRTD5",
            "quantity": 100000,
            "side": "bid",
            "spread": [
                -41.308724880218506,
                -24.528831243515015,
                -14.819729328155518,
                -7.663071155548096,
                -1.518470048904419,
                3.519865870475769,
                8.44331979751587,
                12.850263714790344,
                17.133909463882446,
                21.212029457092285,
                25.10717809200287,
                28.9124995470047,
                32.68296420574188,
                36.629754304885864,
                40.91789126396179,
                45.74577212333679,
                51.37031078338623,
                58.68079662322998,
                71.77832126617432
            ],
            "tenor": 2,
            "treasury_cusip": "91282CNQ0",
            "cusip": "594918BJ2"
        },
        {
            "ats_indicator": "N",
            "date": "2025-08-07T12:59:28.846Z",
            "figi": "BBG003LZRTD5",
            "quantity": 100000,
            "side": "offer",
            "price": [
                80.9112777709961,
                81.02932739257812,
                81.09603881835938,
                81.14326477050781,
                81.17647552490234,
                81.20579528808594,
                81.225830078125,
                81.24657440185547,
                81.26457977294922,
                81.28137969970703,
                81.29777526855469,
                81.31477355957031,
                81.33233642578125,
                81.34815216064453,
                81.37256622314453,
                81.40092468261719,
                81.43618774414062,
                81.48920440673828,
                81.58154296875
            ],
            "cusip": "594918AR5"
        }
    ]
}
```

The attributes of the assumed trade are indicated for each of the inferences. The spread and prices come down as percentiles from the 5th to the 95th percentiles in 5% increments. For spread the treasury benchmark cusip is noted in the response. The date is in the UTC timezone.

## Known Issues

- **Unrecognized FIGIs**: We currently have about 94% coverage in the investment grade (IG) index, and a similar percentage in high yield (HY) bonds index, so some of the FIGI values you may send to the API will trigger a message saying that there are unrecognized FIGIs, and will have a list of the FIGIs. The issue is that the API currently returns a list of numbers which are our internal ID numbers. We are working on rolling out a fix so that the unrecognized FIGIs are reported back. In staging we have the step-up-step down bonds available, which increases our total universe size by about 6,000, and this will be published to production soon.
- **Websockets closed when there's an error**: In some cases when an error is reported back by the API, the websocket connection pre-maturely shuts down. We are working on a fix
- **Portfolio trades not adjusted for**: We are planning a new version of the model which takes into account whether a trade is a portfolio trade or not. Right now our model is not able to see whether a trade is a portfolio trade or not, and so it's not able to learn to mostly ignore a portfolio trades price like you would expect.
- **On the run rates roll-overs**: When there is a new on-the-run treasury, there are some issues we are working to resolve in selecting the correct (street convention) treasury benchmark to use to calculate spread. We're working hard to resolve this issue.


## PyXLL plugin for excel integration
https://github.com/deepmarketmaking/pyxll

## FAQ

**Why do you currently only support FIGI identifiers in the API?**

Mostly for historical reasons as we were developing the backend infrastructure supporting the AI model's inference. Also there's a bit of frustration with the CUSIP system in that FactSet charges an exorbidant licensing fee to allow us to merely display the CUSIPs on our web application; it seems that [the industry is possibly moving towards this more open system](https://www.mayerbrown.com/en/insights/publications/2024/08/us-regulators-propose-data-standards-to-implement-the-financial-data-transparency-act). By using FIGIs, we are not required to check if someone has a CUSIP license before we allow them to try out the API, which can obviously increase the length of our sales cycle. 

We do eventually plan to support CUSIPs in our API -- it's just that we have other current priorities that we're focused on -- such as seeking to increase the coverage of our universe to 100%.

**Why do you only support inferences conditioned on sizes of up to 5,000,000?**

We train our model to predict the label probability distribution as reported by the FINRA TRACE (BTDS and 144A) system. For high yield (HY) bonds of size over 1 MM, they are reported as "1MM+" by TRACE. For investment grade (IG) bonds of size over 5 MM, they are reported as size "5MM+". Therefore, the model has no training data over 5 MM on which to calibrate its weights. Therefore, the API does not permit any inference requests above 5 MM (or below 1), because otherwise the model would have undefined output above that range. There is some amount of generalization capability in that you could send an inference request between 1 MM and 5 MM for a HY bond, and you should get a reasonable result, even though TRACE doesn't have training data between 1 and 5 MM for HY bonds. This generalization capability comes about because we train the same model to work on both HY and IG bonds.

**If your model is so good, why do you sell access to it as subscription rather than just starting your own bond trading / market making hedge fund**

We feel that to build a product that will reach its full potential for value provided to users, it will have to be a cost shared by many firms. This is because this technology is pretty costly to research, develop, scale, and maintain. Our founder, Nathaniel Powell, built a corporate bond pricing model at JP Morgan, which at the time was the largest market maker in US corporate bonds, but still was stretched pretty thin, working on many different projects not corporate bond related. We estimate that we are expending more resources concentrated on corporate bond pricing than JP Morgan was, as a small startup. 

Also -- the enterprise value of a successful enterprise SaaS AI software company is much greater than that of a small hedge fund or prop trading shop.
