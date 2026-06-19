# Update Universe Script

This Python script replicates the functionality of the JavaScript Lambda function for updating the bond universe. It fetches bond data from S3, queries the websocket server for inferences, and uploads the resulting universe to S3.

## Key Features

- **Maturity Date Filtering**: Bonds are included in the universe only if we can get an inference using a timestamp on or before the day before their maturity date, and that date is on or after the specified `--min-date`.

- **Uses Existing Infrastructure**: Leverages the `authentication.py` and `connection.py` modules from this repository for authentication and WebSocket connection management.

- **Dry Run Mode**: Use `--no-upload` to test without uploading to S3.

## Usage

Basic usage:

```bash
./update_universe.py USERNAME PASSWORD --min-date YYYY-MM-DD
```

With all options:

```bash
./update_universe.py USERNAME PASSWORD \
    --min-date 2024-01-01 \
    --region us-east-1 \
    --client-id YOUR_COGNITO_CLIENT_ID \
    --server wss://api.deepmm.com \
    --no-upload
```

## Required Arguments

- `username`: Your Deep MM username
- `password`: Your Deep MM password
- `--min-date`: Minimum date (YYYY-MM-DD format) - bonds must have maturity dates where (maturity_date - 1 day) >= min_date

## Optional Arguments

- `--region`: AWS region for Cognito (default: `us-east-1`)
- `--client-id`: Cognito client ID (default: uses `COGNITO_CLIENT_ID` environment variable)
- `--server`: WebSocket server URL (default: `wss://api.deepmm.com` or `DEEP_MM_SERVER` environment variable)
- `--no-upload`: Dry run mode - don't upload results to S3

## How It Works

1. **Load Bond Data**: Fetches `bond_data.json` from S3 (`deepmm.public` bucket)

2. **Filter by Maturity Date**: Filters bonds to include only those where we can get an inference at least one day before maturity, and that date is >= `min_date`. This ensures we only include bonds that:
   - Have sufficient life remaining (maturity date - 1 day >= min_date)
   - Can be evaluated with at least one day of historical data before maturity

3. **Create Inference Requests**: For each bond, creates an inference request with:
   - Current timestamp
   - `rfq_label: 'spread'`
   - `quantity: 1,000,000`
   - `side: 'bid'`
   - `ats_indicator: 'N'`

4. **Query Server**: Connects to the WebSocket server, sends all inference requests, and collects FIGIs that return valid inferences

5. **Upload Results**: Uploads the list of FIGIs (one per line) to `universe.txt` in S3

## Example Output

```
Using minimum date: 2024-01-01
Authenticating...
Finished authenticating
Retrieving bond_data.json from S3...
Finished retrieving bond_data.json - loaded 23117 bonds
Filtered bonds by min_date 2024-01-01: 23117 -> 15234 bonds
Created 15234 inference requests
Attempting connection to wss://api.deepmm.com
Successful connection to wss://api.deepmm.com
Sending inference requests...
Finished sending inference requests
Receiving message...
Received 1523 FIGIs so far...
...
Universe length: 15234
Closing WebSocket...
Uploading universe.txt with 15234 FIGIs...
Finished uploading universe.txt
Successfully updated universe with 15234 FIGIs
```

## Differences from JavaScript Version

The Python version has these key differences:

1. **Maturity Date Filtering**: The new `--min-date` parameter filters bonds based on whether we can get an inference on or before the day before maturity, and that date is >= min_date. The original JS version included all bonds.

2. **No SNS Notifications**: The Python version doesn't send SNS alerts on failure (though this could be easily added).

3. **Command-line Interface**: Uses command-line arguments instead of AWS Lambda environment variables.

4. **Timeout**: Uses 20-second timeout (same as the JS version) after the last message.

## Dependencies

- `boto3`: AWS SDK for Python
- `websockets`: WebSocket client library
- `pytz`: Timezone handling
- `aiofiles`: Async file operations (used by other scripts in this repo)

Install with:

```bash
pip install boto3 websockets pytz aiofiles
```
