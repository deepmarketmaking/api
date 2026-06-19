#!/usr/bin/env python3
"""Test script to verify the CSV loading logic"""

import json
import boto3
from datetime import datetime
import pytz

def load_ticker_to_figis_mapping():
    """
    Load bond data from S3 and create a mapping from issuer ticker to list of FIGIs
    """
    try:
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket='deepmm.public', Key='bond_data.json')
        content = response['Body'].read().decode('utf-8')
        bond_data = json.loads(content)

        # Create ticker to FIGIs mapping
        ticker_to_figis = {}
        for bond in bond_data:
            ticker = bond['t']
            figi = bond['F']
            if ticker not in ticker_to_figis:
                ticker_to_figis[ticker] = []
            ticker_to_figis[ticker].append(figi)

        print(f"Loaded ticker to FIGI mapping for {len(ticker_to_figis)} unique tickers")
        return ticker_to_figis
    except Exception as e:
        print(f"Error loading bond data from S3: {e}")
        return {}

def test_csv_loading(csv_file_path):
    """Test loading the CSV file"""
    ticker_to_figis = load_ticker_to_figis_mapping()

    eastern_tz = pytz.timezone('US/Eastern')
    date_to_figis = {}
    missing_tickers = set()

    print(f"\nLoading CSV from {csv_file_path}")
    with open(csv_file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            # Split by tab
            parts = line.split('\t')
            if len(parts) != 2:
                print(f"Warning: Line {line_num} does not have exactly 2 tab-separated columns: {line}")
                continue

            date_str, ticker = parts[0].strip(), parts[1].strip()

            # Parse date
            try:
                trade_date = eastern_tz.localize(datetime.strptime(date_str, '%Y-%m-%d'))
            except ValueError as e:
                print(f"Warning: Line {line_num} has invalid date format '{date_str}': {e}")
                continue

            # Get FIGIs for this ticker
            if ticker not in ticker_to_figis:
                missing_tickers.add(ticker)
                print(f"  {date_str}\t{ticker}\t-> TICKER NOT FOUND")
                continue

            figis = ticker_to_figis[ticker]
            print(f"  {date_str}\t{ticker}\t-> {len(figis)} FIGIs: {figis[:3]}{'...' if len(figis) > 3 else ''}")

            if trade_date not in date_to_figis:
                date_to_figis[trade_date] = []
            date_to_figis[trade_date].extend(figis)

    # Report statistics
    if missing_tickers:
        print(f"\nMissing tickers: {sorted(missing_tickers)}")

    total_figis = sum(len(figis) for figis in date_to_figis.values())
    print(f"\nSummary: {len(date_to_figis)} dates with {total_figis} total FIGI-date pairs")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = 'test_date_ticker.csv'

    test_csv_loading(csv_file)
