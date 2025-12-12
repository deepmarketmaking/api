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
