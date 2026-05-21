# Deep MM Python Client

Python client library for the [Deep MM API](https://www.deepmm.com) - Real-time and historical corporate bond pricing.

## Installation

```bash
pip install axor-api
```

## Quick Start

```python
import asyncio
import json
from axor import connect, create_get_id_token

async def main():
    # Authenticate with AWS Cognito
    get_id_token = create_get_id_token(
        region="us-east-1",
        client_id="2so174j2e4fsg1m28kc9id3hgk",  # Test client ID
        username="your-username",
        password="your-password"
    )

    # Connect to the Deep MM API
    ws = await connect()

    # Send authentication token
    await ws.send(json.dumps({'token': get_id_token()}))

    # Subscribe to real-time pricing
    subscription = {
        'inference': [{
            'rfq_label': 'spread',
            'figi': 'BBG003LZRTD5',
            'quantity': 1_000_000,
            'side': 'bid',
            'subscribe': True,
        }]
    }
    await ws.send(json.dumps(subscription))

    # Receive updates
    while True:
        response = await ws.recv()
        print(response)

asyncio.run(main())
```

## Features

- **Authentication**: AWS Cognito integration with automatic token refresh
- **Real-time Subscriptions**: WebSocket-based live pricing updates
- **Historical Data**: Query historical pricing distributions
- **CUSIP/FIGI Mapping**: Convert CUSIPs to FIGIs using OpenFIGI API
- **Distribution Fitting**: Fit normal and Johnson SU distributions to percentile data

## API Reference

### Authentication

```python
from axor import create_get_id_token

get_id_token = create_get_id_token(
    region="us-east-1",
    client_id="your-client-id",
    username="your-username",
    password="your-password"
)

# Token is automatically refreshed as needed
token = get_id_token()
```

### Connection

```python
from axor import connect

# Use default server (wss://api.deepmm.com)
ws = await connect()

# Or specify custom server
ws = await connect("wss://custom-server.com")
```

### CUSIP to FIGI Mapping

```python
from axor import openfigi_map_cusips_to_figis

cusip_to_figi, figi_to_cusip = openfigi_map_cusips_to_figis(
    api_key="your-openfigi-api-key",
    cusip_list=["594918BJ2", "037833100"]
)

# Use the mappings
figi = cusip_to_figi["594918BJ2"]
```

The API is FIGI-native. The OpenFIGI workflow above maps CUSIP/ISIN identifiers to FIGIs. For FIGI to CUSIP/ISIN lookups, prefer Deep MM's public [`bond_data_public.json`](https://public.deepmm.com/bond_data_public.json) mapping when the bond is present there.

### Distribution Fitting

```python
from axor import fit_normal_distribution, fit_johnson_su

# Fit normal distribution to percentile data
percentiles = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95]
values = [...]  # Your percentile values from API response

mu, sigma, error = fit_normal_distribution(percentiles, values)
print(f"Mean: {mu}, Std Dev: {sigma}")

# Fit Johnson SU distribution (better for skewed/heavy-tailed data)
gamma, delta, loc, scale, error = fit_johnson_su(percentiles, values)

# Generate plots (requires matplotlib)
from axor import plot_cdf_of_fitted_johnson_su_distribution

plot_cdf_of_fitted_johnson_su_distribution(
    'output.png',
    percentiles,
    values,
    gamma, delta, loc, scale
)
```

## Request guidance

The WebSocket API supports both real-time subscriptions (`"subscribe": true`) and one-off requests (`"subscribe": false`). For pre-trade integrations, consider requesting multiple signal variations that match the RFQs you expect to price: several standardized quantities, both `bid` and `offer` sides, and both ATS and non-ATS assumptions. If you only start with one size, `1_000_000` is generally the best default based on Deep MM experiments.

Recommended standardized quantities are `1_000`, `10_000`, `100_000`, `250_000`, `500_000`, `1_000_000`, `2_000_000`, `3_000_000`, `4_000_000`, and `5_000_000`. Using these values reduces server load because common inferences can be reused across clients. You can linearly interpolate between standardized size points to approximate a specific RFQ size, or send a one-off request for the exact RFQ configuration when exact ad hoc pricing is more important than maintaining a subscription.

For normal subscription requests, the server sends an immediate snapshot/first response for the accepted subscription, followed by later independent updates. Very large batches may be handled differently to protect server load, so send subscriptions in reasonable batches.

Unsupported FIGIs are reported with an `unrecognized figis` message and are filtered out without counting as active subscriptions; valid subscriptions in the same mixed request can still proceed. If a recognized FIGI cannot be inferred for a requested historical timestamp because there is not enough data, the API returns an `insufficient data` message for that inference. Live subscriptions can remain active through these per-update insufficient-data messages.

### Label and yield notes

`rfq_label="price"` returns the model-implied price distribution. `rfq_label="spread"` returns the model-implied spread distribution, where the spread target is based on TRACE-reported yield minus the assigned benchmark Treasury yield. Where TRACE yield is not present, Deep MM fills in the missing yield with its own YTM calculator before calculating the spread label.

`rfq_label="ytm"` currently uses the spread/yield pipeline rather than calling the price model and converting that price to YTM. In practice, it returns the modeled spread plus the selected benchmark Treasury yield. Where TRACE-reported yield is present, this yield label is primarily based on TRACE yield; where TRACE yield is not present, Deep MM fills in with its own YTM calculator.

Because price and spread/yield are separate model outputs, they may not agree exactly after conversion into the same units. TRACE-reported yield can also reflect yield-to-worst conventions for some securities. For callable, fixed-to-float, or otherwise non-plain-vanilla bonds where YTW can differ materially from YTM, the current YTM fallback can be less accurate until Deep MM's fuller YTW calculator is integrated.

For spread/yield outputs, Deep MM assigns a benchmark Treasury using an algorithm intended to follow market convention and uses the latest TP ICAP Treasury yield mid received before the execution/inference timestamp. Spread responses include `treasury_cusip` when available.

## Examples

Complete working examples are available in the [examples/](examples/) directory:

- **[subscribe_simple.py](examples/subscribe_simple.py)** - Basic subscription to real-time pricing
- **[subscribe.py](examples/subscribe.py)** - Advanced subscription with multiple variations
- **[timestamp_simple.py](examples/timestamp_simple.py)** - Historical pricing queries
- **[timestamp_normal.py](examples/timestamp_normal.py)** - Historical data with normal distribution fitting
- **[timestamp_johnson_su.py](examples/timestamp_johnson_su.py)** - Historical data with Johnson SU fitting

## Installation for Development

```bash
# Clone the repository
git clone https://github.com/deepmarketmaking/api.git
cd api/python

# Install in editable mode with dev dependencies
pip install -e ".[dev,visualization]"

# Run tests
pytest
```

## Requirements

- Python 3.8 or higher
- Dependencies:
  - `boto3` - AWS Cognito authentication
  - `websockets` - WebSocket communication
  - `httpx` - HTTP requests for OpenFIGI API
  - `numpy`, `scipy` - Distribution fitting
  - `pyarrow` - Efficient data handling
  - `tenacity` - Retry logic
  - `matplotlib` (optional) - For visualization

## Documentation

Full API documentation and additional examples are available at:
- [Main Repository](https://github.com/deepmarketmaking/api)
- [API Documentation](https://github.com/deepmarketmaking/api#readme)

## Support

For questions, issues, or feature requests:
- [GitHub Issues](https://github.com/deepmarketmaking/api/issues)
- Email: support@deepmm.com

## License

Apache License 2.0 - See [LICENSE](../LICENSE) for details.
