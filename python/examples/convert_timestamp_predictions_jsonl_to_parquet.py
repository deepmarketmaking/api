#!/usr/bin/env python3
"""
Convert timestamp predictions JSONL to Parquet format.

This script reads JSONL files produced by new_get_timestamp_predictions.py
and converts them to Parquet format, extracting only the 50th percentile
(median) prediction value from each record.

The input JSONL format contains records like:
{
    "figi": "BBG010RZL837",
    "date": "2025-09-02T12:00:00.000Z",
    "ats_indicator": "N",
    "price_type": "bid",
    "price": [99.5, 99.6, 99.7, ...],  // percentiles 5-95 in 5% increments
    ...
}

The output Parquet will have columns:
- figi: string
- cusip: string (mapped from FIGI)
- date: timestamp
- ats_indicator: string
- side: string (renamed from price_type: bid/offer)
- predicted_price_p50: float (the 50th percentile value)
- other columns from the input (excluding 'price' array)
"""

import argparse
import sys
import json
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    print("Error: pyarrow library not found. Please install it with: pip install pyarrow", file=sys.stderr)
    sys.exit(1)

try:
    import boto3
except ImportError:
    print("Error: boto3 library not found. Please install it with: pip install boto3", file=sys.stderr)
    sys.exit(1)


def load_figi_to_cusip_mapping():
    """
    Load FIGI-to-CUSIP mapping from S3.

    Returns:
        dict: Mapping of FIGI (F field) to CUSIP (C field)
    """
    print("Loading FIGI-to-CUSIP mapping from S3...")

    s3 = boto3.client('s3')
    bucket = 'deepmm.public'
    key = 'bond_data.json'

    try:
        # Download the file
        response = s3.get_object(Bucket=bucket, Key=key)
        bond_data = json.loads(response['Body'].read().decode('utf-8'))

        # Build FIGI -> CUSIP mapping
        figi_to_cusip = {}
        for bond in bond_data:
            if 'F' in bond and 'C' in bond:
                figi_to_cusip[bond['F']] = bond['C']

        print(f"Loaded {len(figi_to_cusip)} FIGI-to-CUSIP mappings")
        return figi_to_cusip

    except Exception as e:
        print(f"Warning: Failed to load FIGI-to-CUSIP mapping: {e}", file=sys.stderr)
        print("Continuing without CUSIP mapping...", file=sys.stderr)
        return {}


def convert_jsonl_to_parquet(input_path: str, output_path: str = None, batch_size: int = 100000):
    """
    Convert JSONL timestamp predictions to Parquet format.

    Args:
        input_path: Path to input JSONL file
        output_path: Path to output Parquet file (default: input_path with .parquet extension)
        batch_size: Number of records to process at once (default: 100000)
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Determine output path
    if output_path is None:
        output_file = input_file.with_suffix('.parquet')
    else:
        output_file = Path(output_path)

    print(f"Converting {input_file} to {output_file}...")
    print(f"Extracting 50th percentile (median) values from price arrays...")

    # Load FIGI-to-CUSIP mapping
    figi_to_cusip = load_figi_to_cusip_mapping()

    # Process the JSONL file in batches
    records = []
    total_count = 0
    writer = None
    schema = None

    try:
        with open(input_file, 'r') as infile:
            for line_num, line in enumerate(infile, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)

                    # Add CUSIP column by mapping from FIGI
                    if 'figi' in record and figi_to_cusip:
                        record['cusip'] = figi_to_cusip.get(record['figi'], None)
                    else:
                        record['cusip'] = None

                    # Rename price_type to side
                    if 'price_type' in record:
                        record['side'] = record['price_type']
                        del record['price_type']

                    # Extract the 50th percentile value from price array
                    # The 'price' array contains percentiles 5-95 in 5% increments (19 values total)
                    # Index mapping: [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95]
                    # So the 50th percentile is at index 9 (0-based)
                    if 'price' in record and isinstance(record['price'], list):
                        if len(record['price']) >= 10:
                            record['predicted_price_p50'] = record['price'][9]  # Index 9 = 50th percentile
                        else:
                            print(f"Warning: Line {line_num} has price array with length {len(record['price'])}, expected 19", file=sys.stderr)
                            record['predicted_price_p50'] = None

                        # Remove the full array to save space
                        del record['price']
                    else:
                        record['predicted_price_p50'] = None

                    records.append(record)
                    total_count += 1

                    # Write batch when we reach batch_size
                    if len(records) >= batch_size:
                        # Convert to PyArrow table
                        table = pa.Table.from_pylist(records)

                        if writer is None:
                            # Initialize schema and writer on first batch
                            schema = table.schema
                            writer = pq.ParquetWriter(output_file, schema, compression='snappy')

                        writer.write_table(table)
                        records = []

                        if total_count % 100000 == 0:
                            print(f"Processed {total_count} records...")

                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse JSON on line {line_num}: {e}", file=sys.stderr)
                    continue

        # Write remaining records
        if records:
            table = pa.Table.from_pylist(records)

            if writer is None:
                # Initialize schema and writer if we haven't yet (small file case)
                schema = table.schema
                writer = pq.ParquetWriter(output_file, schema, compression='snappy')

            writer.write_table(table)

        # Close the writer
        if writer is not None:
            writer.close()

        print(f"\nSuccessfully converted {total_count} records to {output_file}")

        # Print file sizes
        input_size_mb = input_file.stat().st_size / (1024 * 1024)
        output_size_mb = output_file.stat().st_size / (1024 * 1024)
        compression_ratio = input_size_mb / output_size_mb if output_size_mb > 0 else 0

        print(f"Input size: {input_size_mb:.2f} MB")
        print(f"Output size: {output_size_mb:.2f} MB")
        print(f"Compression ratio: {compression_ratio:.2f}x")

    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(
        description='Convert timestamp predictions JSONL to Parquet format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert a single file (output will be input.parquet)
  python convert_timestamp_predictions_jsonl_to_parquet.py predictions.jsonl

  # Convert with specific output path
  python convert_timestamp_predictions_jsonl_to_parquet.py predictions.jsonl -o output.parquet

  # Use larger batch size for better performance
  python convert_timestamp_predictions_jsonl_to_parquet.py predictions.jsonl --batch-size 500000
"""
    )

    parser.add_argument(
        'input_file',
        type=str,
        help='Input JSONL file to convert'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Output Parquet file path (default: input file with .parquet extension)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=100000,
        help='Number of records to process at once (default: 100000)'
    )

    args = parser.parse_args()

    try:
        convert_jsonl_to_parquet(args.input_file, args.output, args.batch_size)
    except Exception as e:
        print(f"Failed to convert file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
