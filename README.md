# Deep MM API for Real-time and Historical Pricing

## Introduction

Our (currently US Only) Corporate Credit AI pricing engine is able [to infer](https://www.cloudflare.com/learning/ai/inference-vs-training/#:~:text=In%20the%20field%20of%20artificial,examples%20of%20the%20desired%20result.) the probability distribution of hypothetical trades on the secondary market [conditioned on](https://en.wikipedia.org/wiki/Conditional_probability) properties of the trade knowable before the trade, and also conditioned on a trade occuring at the specified point in time:

- **FIGI**: the bond identifier, with an easy lookup from the CUSIP)
- **Label**: price, spread, ytm. What do you want the model to predict? (Generally price, spread, or yield to maturity (YTM), with plans for adding other labels in the future such as option-adjusted spread). 
- **Quantity**: How big of a hypothetical trade is it? Valid values range from 1 to 5,000,000, the later being the maximum reported by the commercial TRACE feed (the academic historical data has the actual sizes, but we're not allowed to use it).
- **Side**: bid, offer, dealer, as reported by trace (simplified from the two-field values reported by TRACE).
- **ATS Indicator**: Y,N, default N. This indicates whether you want to assume the trade is happening on an alternative trading service. This field is optional.
- **Timestamp**: List of strings in the ISO 8601 UTC timestamp format for which you want to get historical price, spread, or ytm probability distributions. Any timestamp greater than January 1st, 2019 is valid (as that is how far back we have historical data inputs for our AI model). This field is optional. Typically if you only want the current inference values, then you would not include this field.

You can also specify whether you want to subscribe to the inference. If you subscribe then you will receive updates at regular intervals while you maintain the websocket connection. 

The output of the model currently is the inferred 5th through the 95th percentiles of the label specified (5th being the lowest value and 95th being the highest). The percentiles are a table of select values in the AI-estimated [cumulative distribution function](https://en.wikipedia.org/wiki/Cumulative_distribution_function) of the label values. We do have plans to modify our API in the future to enable more percentiles, particularly in the tails. In our web application, we use simple linear interpolation between percentiles as needed to go from a specific label value to its probability. Another option for getting the probability of a label value perhaps more precisely or further into the tails than we currently model, is to fit a distribution to the percentiles returned from the API, and then query that distribution to get the [cumulative probability](https://en.wikipedia.org/wiki/Cumulative_distribution_function) of the value.  Examples on how to do this are in the following scripts:

- **[Normal Distribution](https://en.wikipedia.org/wiki/Normal_distribution)**: [examples/python/timestamp_normal.py](examples/python/timestamp_normal.py)
- **[Johnson SU Distribution](https://en.wikipedia.org/wiki/Johnson%27s_SU-distribution)**: [examples/python/timestamp_johnson_su.py](examples/python/timestamp_johnson_su.py)

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

   - `Deep MM Websocket Authentication`: You will need a currently active Deep MM username and password for API access. In the future we will be switching over to an authentication scheme more suited for APIs, but for now we use the same method as what is used for the web application, which is AWS cognito with a username and password. We have included example code in this repository on how to authenticate for access to the websocket.
   - `OpenFIGI Authentication`: If you want to make use of the [OpenFIGI api](https://www.openfigi.com/api) to convert your list of CUSIPs over to FIGIs as shown in some of the examples in this repository, you will need [to register](https://www.openfigi.com/user/signup) (for free) and obtain an OpenFIGI API key for your organization.

3. **API Endpoint**:
   Use a WebSocket client to connect to our API server, currently at `https://staging1.deepmm.com`. We recommend the Python websockets library. See the examples in the repository for more details.
   
## Known Issues

- **Unrecognized FIGIs**: We currently have about 94% coverage in investment grade (IG), and a similar percentage in high yield (HY) bonds, so some of the FIGI values you may send to the API will trigger a message saying that there are unrecognized FIGIs, and will have a list of the FIGIs. The issue is that the API currently returns a list of numbers which are our internal ID numbers. We are working on rolling out a fix so that the unrecognized FIGIs are reported back
- **Websockets closed when there's an error**: In some cases when an error is reported back by the API, the websocket connection pre-maturely shuts down. We are working on a fix
- **Portfolio trades not adjusted for**: We are planning a new version of the model which takes into account whether a trade is a portfolio trade or not. Right now our model is not able to see whether a trade is a portfolio trade or not, and so it's not able to learn to mostly ignore a portfolio trades price like you would expect.
- **On the run rates roll-overs**: When there is a new on-the-run treasury, we immediately start using it as the benchmark rather than waiting the one week convention. We are working with our data provider to fix this issue. This affects the estimation of spread and ytm, as well as the accuracy in price space for bonds benchmarked to a treasury during this 1-week period.

## FAQ

**Why do you currently only support FIGI identifiers in the API?**

Mostly for historical reasons as we were developing the backend infrastructure supporting the AI model's inference. Also there's a bit of frustration with the CUSIP system in that FactSet charges an exorbidant licensing fee to allow us to merely display the CUSIPs on our web application; it seems that [the industry is possibly moving towards this more open system](https://www.mayerbrown.com/en/insights/publications/2024/08/us-regulators-propose-data-standards-to-implement-the-financial-data-transparency-act). By using FIGIs, we are not required to check if someone has a CUSIP license before we allow them to try out the API, which can obviously increase the length of our sales cycle. 

We do eventually plan to support CUSIPs in our API -- it's just that we have other current priorities that we're focused on -- such as seeking to increase the coverage of our universe to 100%.
