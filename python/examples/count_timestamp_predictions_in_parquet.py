#!/usr/bin/env python3
"""
Count timestamp predictions in parquet files produced by load_timestamp_predictions_jsonl.sh

This script processes a directory of parquet files and for each file reports:
- Unique number of FIGIs
- Number of predictions (rows)
For each calendar day that has more than 0 prediction rows.

The parquet files are expected to have the schema produced by load_timestamp_predictions_jsonl.py:
    - ats_indicator: 'Y' or 'N'
    - date: timestamp
    - figi: string
    - quantity: int
    - side: 'bid' or 'offer'
    - type: 'price' or 'spread'
    - prediction_5, prediction_10, ..., prediction_95: float percentiles

Usage:
    python count_timestamp_predictions_in_parquet.py <parquet_directory>
    python count_timestamp_predictions_in_parquet.py <parquet_directory> --output summary.csv

Example:
    python count_timestamp_predictions_in_parquet.py /data/inferences/output
    python count_timestamp_predictions_in_parquet.py /data/inferences/output --output summary.csv
"""

import os
import sys
import argparse
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime


def process_parquet_file(filepath: str) -> pd.DataFrame:
    """
    Process a single parquet file and return statistics per calendar day.

    Args:
        filepath: Path to the parquet file

    Returns:
        pd.DataFrame with columns: file, date, num_figis, num_predictions
    """
    print(f"Processing: {os.path.basename(filepath)}")

    # Read the parquet file
    table = pq.read_table(filepath, columns=['date', 'figi'])
    df = table.to_pandas()

    if len(df) == 0:
        print(f"  Warning: No data in file")
        return pd.DataFrame(columns=['file', 'date', 'num_figis', 'num_predictions'])

    # Convert date column to datetime if it's not already
    if not pd.api.types.is_datetime64_any_dtype(df['date']):
        df['date'] = pd.to_datetime(df['date'])

    # Extract calendar date (date only, no time)
    df['calendar_date'] = df['date'].dt.date

    # Group by calendar date and compute statistics
    stats = df.groupby('calendar_date').agg(
        num_figis=('figi', 'nunique'),
        num_predictions=('figi', 'count')
    ).reset_index()

    # Add filename column
    stats.insert(0, 'file', os.path.basename(filepath))

    # Rename calendar_date to date for output
    stats.rename(columns={'calendar_date': 'date'}, inplace=True)

    # Filter out days with 0 predictions (shouldn't happen, but just in case)
    stats = stats[stats['num_predictions'] > 0]

    # Sort by date
    stats = stats.sort_values('date')

    print(f"  Found {len(stats)} calendar days with predictions")
    print(f"  Total predictions: {stats['num_predictions'].sum():,}")
    print(f"  Total unique FIGIs across all days: {df['figi'].nunique():,}")

    return stats


def process_directory(directory: str, pattern: str = '*.parquet') -> pd.DataFrame:
    """
    Process all parquet files in a directory and aggregate counts by calendar day.

    Args:
        directory: Directory containing parquet files
        pattern: Glob pattern for parquet files (default: '*.parquet')

    Returns:
        pd.DataFrame with aggregated statistics per calendar day
    """
    parquet_dir = Path(directory)

    if not parquet_dir.exists():
        raise ValueError(f"Directory does not exist: {directory}")

    if not parquet_dir.is_dir():
        raise ValueError(f"Path is not a directory: {directory}")

    # Find all parquet files
    parquet_files = sorted(parquet_dir.glob(pattern))

    if not parquet_files:
        raise ValueError(f"No parquet files found in {directory} matching pattern '{pattern}'")

    print(f"Found {len(parquet_files)} parquet files in {directory}", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(file=sys.stderr)

    # Collect all data from all files to aggregate by date
    all_data = []
    for filepath in parquet_files:
        try:
            print(f"Processing: {os.path.basename(filepath)}", file=sys.stderr)

            # Read the parquet file
            table = pq.read_table(str(filepath), columns=['date', 'figi'])
            df = table.to_pandas()

            if len(df) > 0:
                # Convert date column to datetime if it's not already
                if not pd.api.types.is_datetime64_any_dtype(df['date']):
                    df['date'] = pd.to_datetime(df['date'])

                # Extract calendar date
                df['calendar_date'] = df['date'].dt.date

                # Keep only what we need
                df = df[['calendar_date', 'figi']]
                all_data.append(df)

                print(f"  Loaded {len(df):,} predictions", file=sys.stderr)
            else:
                print(f"  Warning: No data in file", file=sys.stderr)

            print(file=sys.stderr)
        except Exception as e:
            print(f"  Error processing {filepath}: {e}", file=sys.stderr)
            print(file=sys.stderr)

    if not all_data:
        print("Warning: No data loaded from any file", file=sys.stderr)
        return pd.DataFrame(columns=['date', 'num_figis', 'num_predictions'])

    # Combine all data from all files
    print("Aggregating data across all files...", file=sys.stderr)
    combined_df = pd.concat(all_data, ignore_index=True)

    # Group by calendar date and compute aggregated statistics
    # num_figis: count unique FIGIs across all files for each date
    # num_predictions: count total predictions across all files for each date
    stats = combined_df.groupby('calendar_date').agg(
        num_figis=('figi', 'nunique'),
        num_predictions=('figi', 'count')
    ).reset_index()

    # Rename calendar_date to date for output
    stats.rename(columns={'calendar_date': 'date'}, inplace=True)

    # Filter out days with 0 predictions (shouldn't happen, but just in case)
    stats = stats[stats['num_predictions'] > 0]

    # Sort by date
    stats = stats.sort_values('date')

    print(f"Found {len(stats)} calendar days with predictions", file=sys.stderr)
    print(f"Total predictions across all files: {stats['num_predictions'].sum():,}", file=sys.stderr)
    print(f"Total unique FIGIs across all files and dates: {combined_df['figi'].nunique():,}", file=sys.stderr)
    print(file=sys.stderr)

    return stats


def print_summary(stats: pd.DataFrame):
    """
    Print a summary of the statistics.

    Args:
        stats: DataFrame with columns: date, num_figis, num_predictions
    """
    print("=" * 80, file=sys.stderr)
    print("SUMMARY", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(file=sys.stderr)

    if stats.empty:
        print("No data to summarize", file=sys.stderr)
        return

    # Overall statistics
    total_predictions = stats['num_predictions'].sum()
    unique_dates = len(stats)
    min_figis = stats['num_figis'].min()
    max_figis = stats['num_figis'].max()
    avg_figis = stats['num_figis'].mean()
    avg_predictions = stats['num_predictions'].mean()

    print(f"Total calendar days with predictions: {unique_dates}", file=sys.stderr)
    print(f"Total predictions across all files: {total_predictions:,}", file=sys.stderr)
    print(f"Average predictions per day: {avg_predictions:,.1f}", file=sys.stderr)
    print(file=sys.stderr)

    print(f"Unique FIGIs per day:", file=sys.stderr)
    print(f"  Min: {min_figis:,}", file=sys.stderr)
    print(f"  Max: {max_figis:,}", file=sys.stderr)
    print(f"  Avg: {avg_figis:,.1f}", file=sys.stderr)
    print(file=sys.stderr)

    # Date range
    min_date = stats['date'].min()
    max_date = stats['date'].max()
    print(f"Date range: {min_date} to {max_date}", file=sys.stderr)
    print(file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description='Count timestamp predictions in parquet files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Output CSV to stdout:
    python count_timestamp_predictions_in_parquet.py /data/inferences/output

  Save to file:
    python count_timestamp_predictions_in_parquet.py /data/inferences/output --output summary.csv

  Process only specific parquet files:
    python count_timestamp_predictions_in_parquet.py /data/inferences/output --pattern "2024*.parquet"
        """
    )

    parser.add_argument(
        'directory',
        type=str,
        help='Directory containing parquet files'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output CSV file path (default: print CSV to stdout)'
    )

    parser.add_argument(
        '--pattern',
        type=str,
        default='*.parquet',
        help='Glob pattern for parquet files (default: *.parquet)'
    )

    parser.add_argument(
        '--summary',
        action='store_true',
        help='Print summary statistics to stderr (does not affect CSV output)'
    )

    args = parser.parse_args()

    try:
        # Process all parquet files in directory
        stats = process_directory(args.directory, args.pattern)

        if stats.empty:
            print("No data found", file=sys.stderr)
            sys.exit(1)

        # Print summary to stderr if requested (so it doesn't interfere with CSV output)
        if args.summary:
            print_summary(stats)

        # Output CSV
        if args.output:
            stats.to_csv(args.output, index=False)
            print(f"Saved CSV to: {args.output}", file=sys.stderr)
        else:
            # Print CSV to stdout
            print(stats.to_csv(index=False))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
