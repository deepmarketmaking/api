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

The output of the model currently is the inferred 5th through the 95th percentiles of the label specified (5th being the lowest value and 95th being the highest). The percentiles are a table of select values in the AI-estimated [cumulative distribution function](https://en.wikipedia.org/wiki/Cumulative_distribution_function) of the label values. We do have plans to modify our API in the future to enable more percentiles, particularly in the tails. In our web application, we use simple linear interpolation between percentiles as needed to go from a specific label value to its probability. Another option for getting the probability of a label value perhaps more precisely or further into the tails than we currently model, is to fit a distribution to the percentiles returned from the API, and then query that distribution to get the [cumulative probability](https://en.wikipedia.org/wiki/Cumulative_distribution_function) of the value.  

## FAQ

**Why do you currently only support FIGI identifiers in the API?**

Mostly for historical reasons as we were developing the backend infrastructure supporting the AI model's inference. Also there's a bit of frustration with the CUSIP system in that FactSet charges an exorbidant licensing fee to allow us to merely display the CUSIPs on our web application; it seems that [the industry is possibly moving towards this more open system](https://www.mayerbrown.com/en/insights/publications/2024/08/us-regulators-propose-data-standards-to-implement-the-financial-data-transparency-act). By using FIGIs, we are not required to check if someone has a CUSIP license before we allow them to try out the API, which can obviously increase the length of our sales cycle. 

We do eventually plan to support CUSIPs in our API -- it's just that we have other current priorities that we're focused on -- such as seeking to increase the coverage of our universe to 100%.
