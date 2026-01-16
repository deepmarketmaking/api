# new_get_timestamp_predictions.py

A Python script for generating timestamp-based model predictions for corporate bonds via WebSocket API. This script queries the Deep MM API at specific times throughout trading days and collects inference results for analysis.

## Overview

This script evaluates bond pricing models at specific timestamps across trading days. It supports multiple scheduling options (9am/4pm, every 5 minutes, every 30 seconds, or end-of-day) and can work with different bond universes including historical data.

**Key Feature**: By default, the script builds a **historical universe** by querying the API on the first day of each month in your date range. This ensures you're working with all bonds that were active at any point during the period, including bonds that have since matured.

## Requirements

- Python 3.7+
- Required packages: `boto3`, `websockets`, `pytz`, `aiofiles`, `pandas`
- AWS credentials configured for S3 access (unless using `--no-auth` with local server)
- Deep MM API credentials (unless using `--no-auth`)

## Basic Usage

```bash
python3 new_get_timestamp_predictions.py [START_DATE] [END_DATE] START_BATCH [OPTIONS]
```

### Positional Arguments

- `START_DATE` (optional): Start date in YYYY-MM-DD format - not used with `--date-ticker-csv`
- `END_DATE` (optional): End date in YYYY-MM-DD format - not used with `--date-ticker-csv`
- `START_BATCH` (required): Starting batch number (typically `0` to process all batches)

## Command-Line Options

### Authentication & Server

- `--username USERNAME`
  Deep MM username (required unless using `--no-auth`)

- `--password PASSWORD`
  Deep MM password (required unless using `--no-auth`)

- `--no-auth`
  Skip authentication for servers with authentication disabled

- `--region REGION`
  AWS region for Cognito authentication (default: `us-east-1`)

- `--client-id CLIENT_ID`
  Cognito client ID (or use `COGNITO_CLIENT_ID` environment variable)

- `--server SERVER_URL`
  Server domain name (default: `wss://api.deepmm.com` or `DEEP_MM_SERVER` environment variable)

### Universe Selection

- `--use-current-universe`
  Use the current universe.txt from S3 instead of building a historical universe.
  **Default behavior** (without this flag): Builds a historical universe by querying the API for the first day of each month in the date range.

- `--cusips CUSIP_FILE`
  Path to file containing CUSIPs (one per line). Overrides universe selection.

- `--date-ticker-csv CSV_FILE`
  Path to CSV file with date-ticker pairs (tab-separated: `YYYY-MM-DD<TAB>TICKER`).
  Collects data for specific issuers on specific dates. Overrides `--cusips` and date arguments.

### Timestamp Scheduling

- `--schedule SCHEDULE`
  Timestamp schedule to use. Options:
  - `default`: 9 AM and 4 PM ET (default)
  - `every_5min`: Every 5 minutes from 8 AM to 6 PM ET
  - `high_freq`: Every 30 seconds from 8 AM to 6 PM ET
  - `eod`: End of day only (6 PM ET)

### Request Parameters

- `--request-mode MODE`
  Request parameter mode:
  - `default`: All 8 combinations (bid/offer × spread/price × ats Y/N)
  - `minimal`: Only bid/offer with ats=N for specified type (faster)
  - `full`: All 8 combinations × 10 quantity levels (1K to 5M)

- `--request-type TYPE`
  Request type for minimal mode: `price` or `spread` (default: `price`)
  Only used with `--request-mode=minimal`

### Output

- `--output OUTPUT_PATH`
  Output file path. Can be:
  - Full file path: `/path/to/output.jsonl`
  - Directory path ending in `/`: `/path/to/dir/` (uses default filename)
  - Default: `timestamp_predictions_{YYYYMMDD}_{YYYYMMDD}_{mode}_{batch}.jsonl`

## Usage Examples

### Example 1: Basic Usage with Authentication

Query all trading days from Jan 1 to Dec 31, 2024, using 9 AM and 4 PM timestamps:

```bash
python3 new_get_timestamp_predictions.py \
  2024-01-01 \
  2024-12-31 \
  0 \
  --username myusername \
  --password mypassword
```

This will:
- Build a historical universe by querying the API on the 1st of each month (Jan-Dec 2024)
- Generate timestamps at 9 AM and 4 PM ET for every trading day
- Use all 8 parameter combinations (default mode)
- Start from batch 0 (process all batches)
- Output: `timestamp_predictions_20240101_20241231_default_0.jsonl`

### Example 2: Local Server without Authentication

Using a local development server with authentication disabled:

```bash
python3 new_get_timestamp_predictions.py \
  --no-auth \
  --server wss://localhost:8080 \
  2024-01-01 \
  2024-12-31 \
  0
```

### Example 3: Every 5 Minutes with Minimal Parameters

Generate predictions every 5 minutes (8 AM - 6 PM ET) using only bid/offer spread requests:

```bash
python3 new_get_timestamp_predictions.py \
  2024-01-01 \
  2024-12-31 \
  0 \
  --username myusername \
  --password mypassword \
  --schedule every_5min \
  --request-mode minimal \
  --request-type spread
```

This generates:
- Timestamps every 5 minutes throughout trading hours
- Only 2 requests per bond (bid price, offer price)
- Much faster than default mode
- Output: `timestamp_predictions_20240101_20241231_minimal_price_0.jsonl`

### Example 4: High Frequency with Full Parameters

Every 30 seconds with all quantity levels:

```bash
python3 new_get_timestamp_predictions.py \
  2024-06-01 \
  2024-06-30 \
  0 \
  --username myusername \
  --password mypassword \
  --schedule high_freq \
  --request-mode full
```

This generates:
- Timestamps every 30 seconds from 8 AM to 6 PM ET
- 80 requests per bond (8 parameter combinations × 10 quantity levels)
- Very large dataset
- Output: `timestamp_predictions_20240601_20240630_full_0.jsonl`

### Example 5: End of Day Only

Get predictions only at market close (6 PM ET):

```bash
python3 new_get_timestamp_predictions.py \
  2024-01-01 \
  2024-12-31 \
  0 \
  --username myusername \
  --password mypassword \
  --schedule eod
```

### Example 6: Using Current Universe (Old Behavior)

Use the current universe.txt instead of building historical universe:

```bash
python3 new_get_timestamp_predictions.py \
  2024-01-01 \
  2024-12-31 \
  0 \
  --username myusername \
  --password mypassword \
  --use-current-universe
```

**Note**: This will only include bonds that are currently active (not matured), which may exclude bonds that were active during your date range but have since matured.

### Example 7: Specific Bonds via CUSIP File

Query only specific bonds listed in a CUSIP file:

```bash
python3 new_get_timestamp_predictions.py \
  2024-01-01 \
  2024-12-31 \
  0 \
  --username myusername \
  --password mypassword \
  --cusips my_bonds.txt
```

**CUSIP file format** (one CUSIP per line):
```
037833100
02079K305
14149YAR6
```

### Example 8: Date-Ticker CSV Mode

Query specific issuers on specific dates:

```bash
python3 new_get_timestamp_predictions.py \
  0 \
  --username myusername \
  --password mypassword \
  --date-ticker-csv my_events.csv \
  --schedule every_5min
```

**CSV file format** (tab-separated):
```
2024-01-15	AAPL
2024-02-20	MSFT
2024-03-10	GOOGL
```

### Example 9: Custom Output Directory

Save output to a specific directory:

```bash
python3 new_get_timestamp_predictions.py \
  2024-01-01 \
  2024-12-31 \
  0 \
  --username myusername \
  --password mypassword \
  --output /data/predictions/
```

Output: `/data/predictions/timestamp_predictions_20240101_20241231_default_0.jsonl`

### Example 10: Resume from Specific Batch

If processing was interrupted, resume from batch 50:

```bash
python3 new_get_timestamp_predictions.py \
  2024-01-01 \
  2024-12-31 \
  50 \
  --username myusername \
  --password mypassword
```

This skips batches 0-49 and processes from batch 50 onwards.

## Understanding Batches

The script splits inference requests into batches to manage API load and memory:

- **Batch size** is calculated as `128,000 / timestamp_count`
- **START_BATCH** determines where to start processing (default: `0` for all batches)
- Useful for:
  - **Parallel processing**: Run multiple instances with different batch numbers
  - **Resuming**: If interrupted, resume from the last completed batch
  - **Output files**: Multiple output files are created if results exceed 100M inferences per file

Example of parallel processing:
```bash
# Terminal 1
python3 new_get_timestamp_predictions.py 2024-01-01 2024-12-31 0 --username user --password pass &

# Terminal 2
python3 new_get_timestamp_predictions.py 2024-01-01 2024-12-31 50 --username user --password pass &

# Terminal 3
python3 new_get_timestamp_predictions.py 2024-01-01 2024-12-31 100 --username user --password pass &
```

## Historical Universe Building (Default Behavior)

By default, the script builds a **historical universe** to ensure complete coverage:

1. Retrieves the S3 version of `bond_data.json` from just before your start date
2. Generates timestamps for the **1st of each month** at midnight UTC
3. Sends inference requests to the API for all bonds at each monthly timestamp
4. Collects the **union** of all FIGIs that returned valid responses across all months
5. Uses this universe for the actual data collection

**Why this matters**: The current `universe.txt` on S3 only contains bonds that are currently active. If you're analyzing historical data (e.g., 2023), many bonds that were active then have since matured and won't be in the current universe. The historical universe building ensures you capture all bonds that were active during your analysis period.

**To skip this** (use current universe only): Add `--use-current-universe` flag.

## Request Modes

### Default Mode (8 requests per bond)
All combinations of:
- RFQ label: `spread`, `price`
- Side: `bid`, `offer`
- ATS indicator: `N`, `Y`
- Quantity: `1,000,000` (fixed)

### Minimal Mode (2 requests per bond)
Only the specified request type (price or spread):
- Side: `bid`, `offer`
- ATS indicator: `N` (only)
- Quantity: `1,000,000` (fixed)

**Use case**: Faster data collection when you only need one request type.

### Full Mode (80 requests per bond)
All 8 parameter combinations × 10 quantity levels:
- Quantities: 1K, 10K, 100K, 250K, 500K, 1M, 2M, 3M, 4M, 5M

**Use case**: Analyzing price/spread sensitivity to trade size.

## Output Format

Output is written as JSONL (JSON Lines), where each line is a valid JSON object representing one inference result:

```json
{"figi": "BBG003LZRTD5", "timestamp": "2024-01-15T14:00:00.000Z", "rfq_label": "spread", "side": "bid", "quantity": 1000000, "ats_indicator": "N", "result": 0.45, ...}
{"figi": "BBG00BLVJYZ2", "timestamp": "2024-01-15T14:00:00.000Z", "rfq_label": "price", "side": "offer", "quantity": 1000000, "ats_indicator": "N", "result": 102.35, ...}
```

Files automatically split when exceeding 100M inferences, creating sequential files:
- `timestamp_predictions_20240101_20241231_default_0.jsonl`
- `timestamp_predictions_20240101_20241231_default_1.jsonl`
- etc.

## Performance Considerations

- **High frequency schedules** (`high_freq`, `every_5min`) generate significantly more data
- **Full request mode** creates 10× more requests than default mode
- **Historical universe building** adds initial setup time but ensures complete coverage
- Use `--request-mode minimal` for faster initial testing
- Consider running batches in parallel for large date ranges

## Error Handling

The script includes robust error handling:
- **Automatic retries** with exponential backoff (up to 100 retries)
- **Reconnection logic** for dropped WebSocket connections
- **Timeout handling** (80 seconds after last message)
- **Partial results**: Continues with other batches even if some fail
- **Progress logging**: Detailed output for monitoring long-running jobs

## Environment Variables

- `COGNITO_CLIENT_ID`: Default Cognito client ID for authentication
- `DEEP_MM_SERVER`: Default server URL (falls back to `wss://api.deepmm.com`)

## Notes

- **Trading days only**: Weekends are automatically excluded
- **Date adjustment**: If end_date is today or later, it's automatically adjusted to yesterday
- **Timezone handling**: All timestamps respect US/Eastern timezone for market hours
- **Bond filtering**: Only bonds active during each timestamp (based on settlement/maturity dates) are queried
- **S3 versioning**: Requires versioning enabled on the `deepmm.public` bucket

## Troubleshooting

### "No version of bond_data.json found before {date}"
The start date is before the oldest S3 version. The script will use the current version instead.

### "Error loading universe from S3"
Check AWS credentials and S3 bucket permissions.

### Connection timeouts
- Increase `TIMEOUT_SECONDS` constant in the script (default: 80)
- Check server connectivity
- Verify authentication credentials

### Memory issues
- Reduce batch size by increasing the number of timestamps
- Process batches sequentially instead of parallel
- Use `--request-mode minimal` to reduce requests

## See Also

- `authentication.py`: Authentication helper functions
- `connection.py`: WebSocket connection management
- Related scripts for data analysis and visualization
