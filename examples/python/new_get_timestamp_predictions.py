#!/usr/bin/env python3
"""
Timestamp-based Model Evaluation Script (New Version)

This script evaluates models at specific times of day (9 AM and 4 PM US/Eastern time)
on ALL trading days for each bond in a universe file. Unlike the original version,
this script does not filter out any trading days and returns the complete set.

This version uses the JSON API to query the websocket server instead of running
the model directly.
"""

from itertools import chain
import os
import json
import asyncio
import boto3
import pandas as pd
import pytz
import hashlib
from datetime import datetime, time as dt_time, timedelta, date
from typing import List, Dict, Any, Optional, Set
import websockets
from collections import Counter
import time
import aiofiles
import argparse
from pathlib import Path

from authentication import create_get_id_token
from connection import connect

# S3 bucket for results
S3_BUCKET = "deepmm.temp"
S3_FOLDER = "timestamp_predictions"

# Timeout in seconds after the last message before closing the connection
TIMEOUT_SECONDS = 80
# Initial delay between batches (seconds)
BATCH_DELAY = 0.1

# Retry configuration
MAX_RETRIES = 100
INITIAL_BACKOFF = 2.0
BACKOFF_FACTOR = 2.5
MAX_BACKOFF = 60

# Websocket ping interval in seconds
PING_INTERVAL = 8

# Reconnection configuration
MAX_RECONNECT_ATTEMPTS = 20
RECONNECT_BACKOFF = 3.0
MAX_RECONNECT_BACKOFF = 600.0

# Cache directory
CACHE_DIR = Path.home() / '.cache' / 'timestamp_predictions'

def ensure_cache_dir():
    """Ensure cache directory exists"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_cache_key(start_date: datetime, end_date: datetime, suffix: str = '') -> str:
    """
    Generate a cache key based on date range and optional suffix

    Args:
        start_date: Start date
        end_date: End date
        suffix: Optional suffix to differentiate cache types

    Returns:
        Cache filename
    """
    date_str = f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
    if suffix:
        return f"{date_str}_{suffix}.json"
    return f"{date_str}.json"

def load_cached_universe(start_date: datetime, end_date: datetime) -> Optional[List[str]]:
    """
    Load cached historical universe if it exists

    Args:
        start_date: Start date of the period
        end_date: End date of the period

    Returns:
        List of FIGIs if cache exists, None otherwise
    """
    ensure_cache_dir()
    cache_file = CACHE_DIR / get_cache_key(start_date, end_date, 'universe')

    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                print(f"Loaded cached universe from {cache_file} ({len(data['figis'])} FIGIs)", flush=True)
                return data['figis']
        except Exception as e:
            print(f"Error loading cached universe: {e}", flush=True)
            return None
    return None

def save_cached_universe(start_date: datetime, end_date: datetime, figis: List[str]):
    """
    Save historical universe to cache

    Args:
        start_date: Start date of the period
        end_date: End date of the period
        figis: List of FIGIs to cache
    """
    ensure_cache_dir()
    cache_file = CACHE_DIR / get_cache_key(start_date, end_date, 'universe')

    try:
        with open(cache_file, 'w') as f:
            json.dump({
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'created_at': datetime.now().isoformat(),
                'figis': figis
            }, f)
        print(f"Saved universe cache to {cache_file}", flush=True)
    except Exception as e:
        print(f"Error saving universe cache: {e}", flush=True)

def load_cached_batches(start_date: datetime, end_date: datetime, schedule: str, request_mode: str, request_type: str = 'price') -> Optional[List[List[Dict[str, Any]]]]:
    """
    Load cached batch requests if they exist

    Args:
        start_date: Start date
        end_date: End date
        schedule: Schedule type
        request_mode: Request mode
        request_type: Request type (for minimal mode)

    Returns:
        List of batches if cache exists, None otherwise
    """
    ensure_cache_dir()
    suffix = f"batches_{schedule}_{request_mode}"
    if request_mode == 'minimal':
        suffix += f"_{request_type}"
    cache_file = CACHE_DIR / get_cache_key(start_date, end_date, suffix)

    if cache_file.exists():
        try:
            print(f"Loading cached batches from {cache_file}...", flush=True)
            with open(cache_file, 'r') as f:
                data = json.load(f)
                print(f"Loaded {len(data['batches'])} batches from cache", flush=True)
                return data['batches']
        except Exception as e:
            print(f"Error loading cached batches: {e}", flush=True)
            return None
    return None

def save_cached_batches(start_date: datetime, end_date: datetime, schedule: str, request_mode: str, request_type: str, batches: List[List[Dict[str, Any]]]):
    """
    Save batch requests to cache

    Args:
        start_date: Start date
        end_date: End date
        schedule: Schedule type
        request_mode: Request mode
        request_type: Request type (for minimal mode)
        batches: List of batches to cache
    """
    ensure_cache_dir()
    suffix = f"batches_{schedule}_{request_mode}"
    if request_mode == 'minimal':
        suffix += f"_{request_type}"
    cache_file = CACHE_DIR / get_cache_key(start_date, end_date, suffix)

    try:
        print(f"Saving {len(batches)} batches to cache...", flush=True)
        with open(cache_file, 'w') as f:
            json.dump({
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'schedule': schedule,
                'request_mode': request_mode,
                'request_type': request_type,
                'created_at': datetime.now().isoformat(),
                'batches': batches
            }, f)
        print(f"Saved batch cache to {cache_file}", flush=True)
    except Exception as e:
        print(f"Error saving batch cache: {e}", flush=True)

def get_s3_object_version_before_date(bucket: str, key: str, before_date: datetime) -> Optional[str]:
    """
    Get the most recent version ID of an S3 object that was created before a specified date

    Args:
        bucket: S3 bucket name
        key: S3 object key
        before_date: Find the version before this date

    Returns:
        Optional[str]: Version ID of the most recent version before the date, or None if not found
    """
    try:
        s3 = boto3.client('s3')
        paginator = s3.get_paginator('list_object_versions')

        # List all versions of the object
        pages = paginator.paginate(Bucket=bucket, Prefix=key)

        matching_versions = []
        for page in pages:
            if 'Versions' not in page:
                continue

            for version in page['Versions']:
                # Only consider versions with exact key match
                if version['Key'] != key:
                    continue

                version_date = version['LastModified']
                # Make sure before_date is timezone-aware for comparison
                if before_date.tzinfo is None:
                    before_date = pytz.UTC.localize(before_date)

                # Check if this version is before our target date
                if version_date < before_date:
                    matching_versions.append({
                        'VersionId': version['VersionId'],
                        'LastModified': version_date
                    })

        if not matching_versions:
            print(f"Warning: No version of {key} found before {before_date.isoformat()}", flush=True)
            return None

        # Sort by date descending and take the most recent
        matching_versions.sort(key=lambda x: x['LastModified'], reverse=True)
        most_recent = matching_versions[0]

        print(f"Found version of {key} from {most_recent['LastModified'].isoformat()} (before {before_date.isoformat()})", flush=True)
        return most_recent['VersionId']

    except Exception as e:
        print(f"Error finding S3 version: {e}", flush=True)
        return None


def load_bond_data_from_s3(version_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Load bond data from S3, optionally from a specific version

    Args:
        version_id: Optional S3 version ID to load a specific version

    Returns:
        List[Dict[str, Any]]: List of bond data dictionaries
    """
    try:
        s3 = boto3.client('s3')

        if version_id:
            print(f"Loading bond_data.json version {version_id} from S3", flush=True)
            response = s3.get_object(Bucket='deepmm.public', Key='bond_data.json', VersionId=version_id)
        else:
            print("Loading current bond_data.json from S3", flush=True)
            response = s3.get_object(Bucket='deepmm.public', Key='bond_data.json')

        content = response['Body'].read().decode('utf-8')
        bond_data = json.loads(content)

        print(f"Loaded {len(bond_data)} bonds from bond_data.json", flush=True)
        return bond_data

    except Exception as e:
        print(f"Error loading bond data from S3: {e}", flush=True)
        raise


def load_universe() -> List[str]:
    """
    Load the universe of bonds from S3 universe.txt

    Returns:
        List[str]: List of bond FIGIs
    """
    try:
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket='deepmm.public', Key='universe.txt')
        content = response['Body'].read().decode('utf-8')

        # Parse the content (assuming one FIGI per line)
        figi_strings = [line.strip() for line in content.split('\n') if line.strip()]

        print(f"Loaded {len(figi_strings)} bonds from universe.txt", flush=True)

        return figi_strings
    except Exception as e:
        print(f"Error loading universe from S3: {e}", flush=True)
        print("Using a small test set of FIGIs instead", flush=True)
        # Return a small test set of FIGIs
        return ["BBG003LZRTD5", "BBG00BLVJYZ2", "BBG00D3FQP27"]


async def build_historical_universe(start_date: datetime, end_date: datetime, get_id_token=None, server=None) -> tuple[List[str], Optional[str]]:
    """
    Build a universe of bonds by querying the API for the first day of each month
    in the specified date range. Returns the union of all FIGIs that were valid
    during any month in the period.

    This function loads two versions of bond_data.json:
    1. Version from BEFORE start_date (captures bonds that matured during the period)
    2. Version from AFTER end_date or current (captures bonds issued during the period)

    It takes the union of both sets for API queries, ensuring complete coverage of all
    bonds that were active at any point during the evaluation period.

    Filtering: Only includes bonds that have a valid S&P rating (field 'r') in at least
    one of the two versions. Bonds with missing, empty, or 'NR' ratings are excluded.

    Caching: Results are cached to ~/.cache/timestamp_predictions/ keyed by date range.

    Args:
        start_date: Start date of the period
        end_date: End date of the period
        get_id_token: Authentication function (optional)
        server: Server URL (optional)

    Returns:
        tuple[List[str], Optional[str]]: Tuple of (list of unique FIGIs, version_id for bond info)
        The version_id is from after the end_date (or None if using current) for most complete data.
    """
    print(f"Building historical universe for period {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", flush=True)

    # Check cache first
    cached_figis = load_cached_universe(start_date, end_date)
    if cached_figis is not None:
        # Still need to determine the bond_info_version_id
        after_date = end_date + timedelta(days=1)
        after_version_id = get_s3_object_version_before_date('deepmm.public', 'bond_data.json', after_date)
        return cached_figis, after_version_id

    # Get the version of bond_data.json from just before the start date
    # This captures bonds that may have matured during the period
    before_version_id = get_s3_object_version_before_date('deepmm.public', 'bond_data.json', start_date)
    if before_version_id is None:
        print("Warning: Could not find bond_data.json version before start date", flush=True)

    # Get the version from after the end date (or use current)
    # This captures bonds that were issued during the period
    # Add one day to end_date to find versions after it
    after_date = end_date + timedelta(days=1)
    after_version_id = get_s3_object_version_before_date('deepmm.public', 'bond_data.json', after_date)
    if after_version_id is None:
        print("Warning: Could not find bond_data.json version after end date, will use current version", flush=True)

    # Load both versions and take the union
    bonds_before = load_bond_data_from_s3(before_version_id) if before_version_id else []
    bonds_after = load_bond_data_from_s3(after_version_id) if after_version_id else load_bond_data_from_s3(None)

    # Track FIGIs with valid S&P ratings in either version
    figis_with_valid_rating = set()

    def has_valid_sp_rating(bond: Dict[str, Any]) -> bool:
        """Check if bond has a valid S&P rating (not missing, empty, or 'NR')"""
        rating = bond.get('r', '')
        return rating and rating != 'NR' and rating.strip() != ''

    for bond in bonds_before:
        if has_valid_sp_rating(bond):
            figis_with_valid_rating.add(bond['F'])

    for bond in bonds_after:
        if has_valid_sp_rating(bond):
            figis_with_valid_rating.add(bond['F'])

    print(f"Found {len(figis_with_valid_rating)} bonds with valid S&P ratings across both versions", flush=True)

    # Create union of bonds based on FIGI, filtering to only those with valid ratings
    figi_to_bond = {}
    for bond in bonds_before:
        if bond['F'] in figis_with_valid_rating:
            figi_to_bond[bond['F']] = bond
    for bond in bonds_after:
        if bond['F'] in figis_with_valid_rating:
            figi_to_bond[bond['F']] = bond  # Later version takes precedence

    bond_data = list(figi_to_bond.values())
    print(f"Combined {len(bonds_before)} bonds from before start_date with {len(bonds_after)} bonds from after end_date -> {len(bond_data)} unique bonds with valid S&P ratings", flush=True)

    # Use the "after" version for bond info (most complete data)
    # If we couldn't find an "after" version, use None (current)
    bond_info_version_id = after_version_id

    # Generate list of first days of each month in the range
    monthly_timestamps = []
    current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Make sure current is timezone-aware (UTC)
    if current.tzinfo is None:
        current = pytz.UTC.localize(current)
    else:
        current = current.astimezone(pytz.UTC)

    # Make end_date timezone-aware for comparison
    if end_date.tzinfo is None:
        end_date_utc = pytz.UTC.localize(end_date)
    else:
        end_date_utc = end_date.astimezone(pytz.UTC)

    while current <= end_date_utc:
        monthly_timestamps.append(current)
        # Move to first day of next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    print(f"Generated {len(monthly_timestamps)} monthly timestamps to validate universe", flush=True)
    for ts in monthly_timestamps:
        print(f"  - {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}", flush=True)

    # Create inference request template (similar to the JS script)
    template = {
        'rfq_label': 'spread',
        'quantity': 1_000_000,
        'side': 'bid',
        'ats_indicator': 'N',
        'subscribe': False,
    }

    # Collect valid FIGIs across all months
    all_valid_figis = set()

    for monthly_ts in monthly_timestamps:
        print(f"\nValidating bonds for {monthly_ts.strftime('%Y-%m-%d')}...", flush=True)

        # Create inference requests for all bonds at this timestamp
        timestamp_str = format_timestamp_for_api(monthly_ts)
        inference_requests = [
            {**template, 'figi': bond['F'], 'timestamp': [timestamp_str]}
            for bond in bond_data
        ]

        print(f"Sending {len(inference_requests)} inference requests for validation...", flush=True)

        # Query the API
        try:
            valid_inferences = await retrieve_batch(inference_requests, batch_idx=f"universe-{monthly_ts.strftime('%Y-%m')}", get_id_token=get_id_token, server=server)

            # Extract FIGIs from successful responses
            valid_figis_this_month = set()
            for inference in valid_inferences:
                if 'figi' in inference:
                    valid_figis_this_month.add(inference['figi'])

            print(f"Found {len(valid_figis_this_month)} valid FIGIs for {monthly_ts.strftime('%Y-%m-%d')}", flush=True)

            # Add to the union
            all_valid_figis.update(valid_figis_this_month)
            print(f"Total unique FIGIs so far: {len(all_valid_figis)}", flush=True)

        except Exception as e:
            print(f"Error validating bonds for {monthly_ts.strftime('%Y-%m-%d')}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            # Continue with other months even if one fails
            continue

    print(f"\nHistorical universe building complete: {len(all_valid_figis)} unique FIGIs found across all months", flush=True)

    # Save to cache
    figis_list = sorted(list(all_valid_figis))
    save_cached_universe(start_date, end_date, figis_list)

    # Return FIGIs and version_id for bond info
    return figis_list, bond_info_version_id

def load_cusip_to_figi_mapping() -> Dict[str, str]:
    """
    Load CUSIP to FIGI mapping from bond_data.json on S3

    Returns:
        Dict[str, str]: Dictionary mapping CUSIPs to FIGIs
    """
    try:
        bond_data = load_bond_data_from_s3()

        # Create CUSIP to FIGI mapping
        cusip_to_figi = {bond['C']: bond['F'] for bond in bond_data}

        print(f"Loaded CUSIP to FIGI mapping for {len(cusip_to_figi)} bonds", flush=True)

        return cusip_to_figi
    except Exception as e:
        print(f"Error loading bond data from S3: {e}", flush=True)
        return {}

def load_figis_from_cusip_file(cusip_file_path: str) -> List[str]:
    """
    Load CUSIPs from a file and translate them to FIGIs, filtering by universe

    Args:
        cusip_file_path: Path to file containing CUSIPs (one per line)

    Returns:
        List[str]: List of bond FIGIs that are in the universe
    """
    # Load CUSIP to FIGI mapping
    cusip_to_figi = load_cusip_to_figi_mapping()

    if not cusip_to_figi:
        raise Exception("Failed to load CUSIP to FIGI mapping")

    # Load universe to filter against
    print("Loading universe for filtering...", flush=True)
    universe_figis = set(load_universe())
    print(f"Universe contains {len(universe_figis)} FIGIs", flush=True)

    # Read CUSIPs from file
    try:
        with open(cusip_file_path, 'r') as f:
            cusips = [line.strip() for line in f if line.strip()]

        print(f"Read {len(cusips)} CUSIPs from {cusip_file_path}", flush=True)

        # Translate CUSIPs to FIGIs and filter by universe
        figis = []
        missing_cusips = []
        filtered_out = []

        for cusip in cusips:
            if cusip in cusip_to_figi:
                figi = cusip_to_figi[cusip]
                if figi in universe_figis:
                    figis.append(figi)
                else:
                    filtered_out.append((cusip, figi))
            else:
                missing_cusips.append(cusip)

        # Report missing CUSIPs
        if missing_cusips:
            print(f"\nWarning: {len(missing_cusips)} CUSIPs not found in bond_data.json:", flush=True)
            for cusip in missing_cusips:
                print(f"  - {cusip}", flush=True)

        # Report filtered out CUSIPs (not in universe)
        if filtered_out:
            print(f"\nFiltered out {len(filtered_out)} CUSIPs (not in universe):", flush=True)
            for cusip, figi in filtered_out:
                print(f"  - {cusip} (FIGI: {figi})", flush=True)

        print(f"\nSuccessfully translated and filtered: {len(figis)} FIGIs in universe", flush=True)

        return figis

    except Exception as e:
        print(f"Error reading CUSIP file {cusip_file_path}: {e}", flush=True)
        raise

def load_ticker_to_figis_mapping() -> Dict[str, List[str]]:
    """
    Load bond data from S3 and create a mapping from issuer ticker to list of FIGIs

    Returns:
        Dict[str, List[str]]: Dictionary mapping issuer tickers to lists of FIGIs
    """
    try:
        bond_data = load_bond_data_from_s3()

        # Create ticker to FIGIs mapping
        ticker_to_figis = {}
        for bond in bond_data:
            ticker = bond['t']
            figi = bond['F']
            if ticker not in ticker_to_figis:
                ticker_to_figis[ticker] = []
            ticker_to_figis[ticker].append(figi)

        print(f"Loaded ticker to FIGI mapping for {len(ticker_to_figis)} unique tickers", flush=True)

        return ticker_to_figis
    except Exception as e:
        print(f"Error loading bond data from S3: {e}", flush=True)
        return {}

def load_date_ticker_csv(csv_file_path: str) -> Dict[datetime, List[str]]:
    """
    Load a CSV file with date-ticker pairs and return a mapping of dates to FIGIs

    CSV format: First column is date (YYYY-MM-DD), second column is issuer ticker
    Columns are separated by tabs

    Args:
        csv_file_path: Path to CSV file

    Returns:
        Dict[datetime, List[str]]: Dictionary mapping dates to lists of FIGIs for that date
    """
    # Load ticker to FIGIs mapping
    ticker_to_figis = load_ticker_to_figis_mapping()

    if not ticker_to_figis:
        raise Exception("Failed to load ticker to FIGI mapping")

    # Load universe to filter against
    print("Loading universe for filtering...", flush=True)
    universe_figis = set(load_universe())
    print(f"Universe contains {len(universe_figis)} FIGIs", flush=True)

    eastern_tz = pytz.timezone('US/Eastern')
    date_to_figis = {}
    missing_tickers = set()
    filtered_out_count = 0

    try:
        with open(csv_file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                # Split by tab
                parts = line.split('\t')
                if len(parts) != 2:
                    print(f"Warning: Line {line_num} does not have exactly 2 tab-separated columns: {line}", flush=True)
                    continue

                date_str, ticker = parts[0].strip(), parts[1].strip()

                # Parse date
                try:
                    trade_date = eastern_tz.localize(datetime.strptime(date_str, '%Y-%m-%d'))
                except ValueError as e:
                    print(f"Warning: Line {line_num} has invalid date format '{date_str}': {e}", flush=True)
                    continue

                # Get FIGIs for this ticker
                if ticker not in ticker_to_figis:
                    missing_tickers.add(ticker)
                    continue

                # Filter FIGIs by universe
                figis_for_ticker = [figi for figi in ticker_to_figis[ticker] if figi in universe_figis]
                filtered_out_count += len(ticker_to_figis[ticker]) - len(figis_for_ticker)

                if not figis_for_ticker:
                    print(f"Warning: Ticker '{ticker}' on {date_str} has no FIGIs in universe", flush=True)
                    continue

                # Add to date mapping
                if trade_date not in date_to_figis:
                    date_to_figis[trade_date] = []
                date_to_figis[trade_date].extend(figis_for_ticker)

        # Report statistics
        if missing_tickers:
            print(f"\nWarning: {len(missing_tickers)} tickers not found in bond_data.json:", flush=True)
            for ticker in sorted(missing_tickers):
                print(f"  - {ticker}", flush=True)

        if filtered_out_count > 0:
            print(f"\nFiltered out {filtered_out_count} FIGIs (not in universe)", flush=True)

        total_figis = sum(len(figis) for figis in date_to_figis.values())
        print(f"\nSuccessfully loaded {len(date_to_figis)} dates with {total_figis} total FIGI-date pairs", flush=True)

        return date_to_figis

    except Exception as e:
        print(f"Error reading CSV file {csv_file_path}: {e}", flush=True)
        raise
    
# Returns a dictionary mapping FIGIs to objects containing issue date and maturity date
def figi_to_issue_date(version_id: Optional[str] = None) -> Dict[str, Dict[str, datetime]]:
    """
    Load bond data from S3 and create a mapping from FIGI to bond information.

    Args:
        version_id: Optional S3 version ID to load a specific historical version

    Returns:
        Dict[str, Dict[str, datetime]]: A dictionary mapping FIGI to an object containing
        'settlement_date' and 'maturity_date' as datetime objects.
    """
    eastern_tz = pytz.timezone('US/Eastern')

    try:
        bond_data = load_bond_data_from_s3(version_id)

        # Create a mapping of FIGIs to bond information objects
        figi_bond_info = {}

        for bond in bond_data:
            bond_info = {}
            bond_info['settlement_date'] = eastern_tz.localize(datetime.strptime(bond['s'], '%Y-%m-%d'))
            bond_info['maturity_date'] = eastern_tz.localize(datetime.strptime(bond['m'], '%Y-%m-%d'))
            figi_bond_info[bond['F']] = bond_info

        print(f"Loaded bond information for {len(figi_bond_info)} bonds", flush=True)

        return figi_bond_info

    except Exception as e:
        print(f"Error loading bond data from S3: {e}", flush=True)
        return {}
    
def get_trading_days(start_date: datetime, end_date: datetime) -> List[datetime]:
    """
    Get a list of ALL trading days between start_date and end_date
    This version always returns all trading days in the range, with no filtering
    
    Args:
        start_date: Start date
        end_date: End date
        
    Returns:
        List[datetime]: List of all trading days
    """
    # If end_date is today or later, move it back to yesterday
    today = datetime.now().date()
    if end_date.date() >= today:
        end_date = datetime.combine(today - timedelta(days=1), end_date.time())
        print(f"Adjusted end_date to yesterday: {end_date.strftime('%Y-%m-%d')}", flush=True)
    
    # Generate all days in the range
    delta = end_date - start_date
    all_days = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    
    # Filter out weekends (0 = Monday, 6 = Sunday in weekday())
    trading_days = [day for day in all_days if day.weekday() < 5]
    
    print(f"Found {len(trading_days)} trading days between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}", flush=True)
    return trading_days

def generate_timestamps_9am_4pm(day: datetime) -> List[datetime]:
    """
    Generate 9 AM and 4 PM ET timestamps for a single trading day

    Args:
        day: A single trading day

    Returns:
        List[datetime]: List containing 9 AM and 4 PM timestamps
    """
    eastern_tz = pytz.timezone('US/Eastern')
    day_date = day.date()

    timestamps = []
    # 9 AM ET
    morning = eastern_tz.localize(datetime.combine(day_date, dt_time(9, 0)))
    timestamps.append(morning)

    # 4 PM ET
    afternoon = eastern_tz.localize(datetime.combine(day_date, dt_time(16, 0)))
    timestamps.append(afternoon)

    return timestamps


def generate_timestamps_every_30s(day: datetime) -> List[datetime]:
    """
    Generate timestamps every 30 seconds from 8 AM to 6 PM ET for a single trading day

    Args:
        day: A single trading day

    Returns:
        List[datetime]: List of timestamps at 30-second intervals
    """
    eastern_tz = pytz.timezone('US/Eastern')
    day_date = day.date()

    timestamps = []
    # Start at 8 AM ET
    start_time = eastern_tz.localize(datetime.combine(day_date, dt_time(8, 0)))
    # End at 6 PM ET
    end_time = eastern_tz.localize(datetime.combine(day_date, dt_time(18, 0)))

    current_time = start_time
    while current_time <= end_time:
        timestamps.append(current_time)
        current_time += timedelta(seconds=30)

    return timestamps


def generate_timestamps_every_5min(day: datetime) -> List[datetime]:
    """
    Generate timestamps every 5 minutes from 8 AM to 6 PM ET for a single trading day

    Args:
        day: A single trading day

    Returns:
        List[datetime]: List of timestamps at 5-minute intervals
    """
    eastern_tz = pytz.timezone('US/Eastern')
    day_date = day.date()

    timestamps = []
    # Start at 8 AM ET
    start_time = eastern_tz.localize(datetime.combine(day_date, dt_time(8, 0)))
    # End at 6 PM ET
    end_time = eastern_tz.localize(datetime.combine(day_date, dt_time(18, 0)))

    current_time = start_time
    while current_time <= end_time:
        timestamps.append(current_time)
        current_time += timedelta(minutes=5)

    return timestamps


def generate_timestamps_eod(day: datetime) -> List[datetime]:
    """
    Generate 6 PM ET timestamp for a single trading day (end of day)

    Args:
        day: A single trading day

    Returns:
        List[datetime]: List containing single 6 PM timestamp
    """
    eastern_tz = pytz.timezone('US/Eastern')
    day_date = day.date()

    timestamps = []
    # 6 PM ET
    eod = eastern_tz.localize(datetime.combine(day_date, dt_time(18, 0)))
    timestamps.append(eod)

    return timestamps


# Registry of available timestamp schedules
TIMESTAMP_GENERATORS = {
    'default': generate_timestamps_9am_4pm,
    'high_freq': generate_timestamps_every_30s,
    'every_5min': generate_timestamps_every_5min,
    'eod': generate_timestamps_eod,
}


def generate_timestamps(trading_days: List[datetime], schedule: str = 'default') -> List[datetime]:
    """
    Generate timestamps for each trading day using the specified schedule

    Args:
        trading_days: List of trading days
        schedule: Name of the schedule to use (default, high_freq, etc.)

    Returns:
        List[datetime]: List of timestamps
    """
    if schedule not in TIMESTAMP_GENERATORS:
        raise ValueError(f"Unknown schedule '{schedule}'. Available schedules: {', '.join(TIMESTAMP_GENERATORS.keys())}")

    generator_fn = TIMESTAMP_GENERATORS[schedule]
    timestamps = []

    for day in trading_days:
        day_timestamps = generator_fn(day)
        timestamps.extend(day_timestamps)

    print(f"Generated {len(timestamps)} timestamps using '{schedule}' schedule", flush=True)
    return timestamps

def format_timestamp_for_api(timestamp: datetime) -> str:
    """
    Format a timestamp for the API
    
    Args:
        timestamp: Timestamp to format
        
    Returns:
        str: Timestamp in ISO format with Z suffix
    """
    # Convert to UTC
    utc_timestamp = timestamp.astimezone(pytz.UTC)
    
    # Format as ISO string with Z suffix
    return utc_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


async def append_batch_to_jsonl(file_path, batch_results):
    """Append an entire batch of results to JSONL file in one operation"""
    async with aiofiles.open(file_path, 'a') as f:
        # Build the entire batch data at once
        batch_lines = []
        for item in batch_results:
            # Each item is written as a single line of compact JSON
            batch_lines.append(json.dumps(item))

        # Join all items with newlines
        full_data = '\n'.join(batch_lines) + '\n'
        await f.write(full_data)

async def main():
    parser = argparse.ArgumentParser(
        description='Generate timestamp predictions for bond universe',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available schedules: {', '.join(TIMESTAMP_GENERATORS.keys())}"
    )
    parser.add_argument('start_date', type=str, nargs='?', default=None, help='Start date (YYYY-MM-DD). Not used in --date-ticker-csv mode')
    parser.add_argument('end_date', type=str, nargs='?', default=None, help='End date (YYYY-MM-DD). Not used in --date-ticker-csv mode')
    parser.add_argument('start_batch', type=int, help='Starting batch number')
    parser.add_argument(
        '--username',
        type=str,
        default=None,
        help='Deep MM username (not required with --no-auth)'
    )
    parser.add_argument(
        '--password',
        type=str,
        default=None,
        help='Deep MM password (not required with --no-auth)'
    )
    parser.add_argument(
        '--region',
        type=str,
        default='us-east-1',
        help='AWS region for Cognito (default: us-east-1)'
    )
    parser.add_argument(
        '--client-id',
        type=str,
        default=None,
        help='Cognito client ID (default: uses environment variable COGNITO_CLIENT_ID)'
    )
    parser.add_argument(
        '--server',
        type=str,
        default=None,
        help='Server domain name (default: wss://api.deepmm.com or DEEP_MM_SERVER environment variable)'
    )
    parser.add_argument(
        '--schedule',
        type=str,
        default='default',
        choices=list(TIMESTAMP_GENERATORS.keys()),
        help='Timestamp schedule to use (default: default)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file path. Can be a full file path or a directory path ending in / '
             '(default: timestamp_predictions_{YYYYMMDD}_{YYYYMMDD}_{batch}.jsonl in current directory)'
    )
    parser.add_argument(
        '--request-mode',
        type=str,
        default='default',
        choices=list(REQUEST_PARAMETER_MODES.keys()),
        help='Request parameter mode: default (all 8 combinations), minimal (bid/offer with ats=N only), or full (all 8 combinations × 10 quantity levels)'
    )
    parser.add_argument(
        '--request-type',
        type=str,
        default='price',
        choices=['price', 'spread'],
        help='Request type for minimal mode: price or spread (default: price). Only used with --request-mode=minimal'
    )
    parser.add_argument(
        '--cusips',
        type=str,
        default=None,
        help='Path to file containing CUSIPs (one per line). If not specified, uses default universe from S3'
    )
    parser.add_argument(
        '--date-ticker-csv',
        type=str,
        default=None,
        help='Path to CSV file with date-ticker pairs (tab-separated: YYYY-MM-DD<TAB>TICKER). '
             'When used, collects tick data for each issuer on their respective date. '
             'Overrides --cusips if both are specified.'
    )
    parser.add_argument(
        '--use-current-universe',
        action='store_true',
        help='Use the current universe.txt from S3 instead of building a historical universe. '
             'By default, the script builds a universe by querying the API for each month in the date range.'
    )
    parser.add_argument(
        '--no-auth',
        action='store_true',
        help='Skip authentication (for servers with authentication disabled)'
    )

    args = parser.parse_args()

    # Handle authentication setup
    if args.no_auth:
        print("Skipping authentication (--no-auth specified)", flush=True)
        get_id_token = None
    else:
        # Validate that username and password are provided
        if not args.username or not args.password:
            print('Error: --username and --password are required unless --no-auth is specified')
            exit(1)

        # Get client_id from args or environment variable
        client_id = args.client_id
        if client_id is None:
            client_id = os.getenv('COGNITO_CLIENT_ID')
            if client_id is None:
                print('Error: Cognito client ID must be provided via --client-id or COGNITO_CLIENT_ID environment variable')
                exit(1)

        # Create authentication function
        get_id_token = create_get_id_token(args.region, client_id, args.username, args.password)

    try:
        eastern_tz = pytz.timezone('US/Eastern')
        start_batch = args.start_batch
        schedule = args.schedule
        request_mode = args.request_mode
        request_type = args.request_type

        # Warn if request_type is specified for modes that don't use it
        if request_type != 'price' and request_mode in ['default', 'full']:
            print(f"Warning: --request-type is ignored for '{request_mode}' mode (both price and spread are always included)", flush=True)

        # Check if using date-ticker CSV mode
        if args.date_ticker_csv:
            # CSV mode: dates come from the CSV file
            if args.start_date or args.end_date:
                print("Warning: start_date and end_date are ignored when using --date-ticker-csv mode", flush=True)

            print(f"Starting CSV mode processing, batch {start_batch}, schedule '{schedule}', request mode '{request_mode}'", flush=True)

            figi_bond_info = figi_to_issue_date()
            date_to_figis = load_date_ticker_csv(args.date_ticker_csv)

            # Generate inference requests per date
            inference_requests = []
            for trade_date, figis_for_date in sorted(date_to_figis.items()):
                # Generate timestamps for this specific date
                day_timestamps = TIMESTAMP_GENERATORS[schedule](trade_date)
                print(f"Date {trade_date.strftime('%Y-%m-%d')}: {len(figis_for_date)} FIGIs, {len(day_timestamps)} timestamps", flush=True)

                # Generate requests for this date
                date_requests = get_inference_requests(figis_for_date, day_timestamps, figi_bond_info, request_mode=request_mode, request_type=request_type)
                inference_requests.extend(date_requests)

            timestamp_count = sum(len(TIMESTAMP_GENERATORS[schedule](trade_date)) for trade_date in date_to_figis.keys())
            print(f"Total timestamp count across all dates: {timestamp_count}", flush=True)
            print(f"Total inference requests: {len(inference_requests)}", flush=True)

            # Determine date range for output file naming
            sorted_dates = sorted(date_to_figis.keys())
            start_date = sorted_dates[0]
            end_date = sorted_dates[-1]
        else:
            # Original mode: all FIGIs across all dates
            # Validate required arguments
            if not args.start_date or not args.end_date:
                print("Error: start_date and end_date are required when not using --date-ticker-csv mode", flush=True)
                exit(1)

            # Parse dates
            start_date = eastern_tz.localize(datetime.strptime(args.start_date, '%Y-%m-%d'))
            end_date = eastern_tz.localize(datetime.strptime(args.end_date, '%Y-%m-%d'))

            print(f"Starting processing from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}, batch {start_batch}, schedule '{schedule}', request mode '{request_mode}'", flush=True)

            timestamps = generate_timestamps(get_trading_days(start_date, end_date), schedule=schedule)
            timestamp_count = len(timestamps)
            print(f"Timestamp count: {timestamp_count}", flush=True)

            # Load FIGIs from CUSIP file, historical universe, or current universe
            # Also determine which bond_data version to use for bond info
            bond_data_version_id = None
            if args.cusips:
                print(f"Loading FIGIs from CUSIP file: {args.cusips}", flush=True)
                figis = load_figis_from_cusip_file(args.cusips)
            elif args.use_current_universe:
                print("Loading current universe from S3 universe.txt", flush=True)
                figis = load_universe()
            else:
                print("Building historical universe by querying API for each month...", flush=True)
                figis, bond_data_version_id = await build_historical_universe(start_date, end_date, get_id_token, args.server)

            # Load bond info using the same version as the historical universe (if applicable)
            figi_bond_info = figi_to_issue_date(bond_data_version_id)

            # Try to load cached batches
            cached_batches = load_cached_batches(start_date, end_date, schedule, request_mode, request_type)
            if cached_batches is not None:
                batches = cached_batches
            else:
                # Generate inference requests and batches
                inference_requests = get_inference_requests(figis, timestamps, figi_bond_info, request_mode=request_mode, request_type=request_type)

                batch_size = int(128_000 / timestamp_count) # Because each inference request has a list of timestamps.
                batches = [inference_requests[i:i + batch_size] for i in range(0, len(inference_requests), batch_size)]
                print(f"Batches count: {len(batches)}", flush=True)

                # Save batches to cache
                save_cached_batches(start_date, end_date, schedule, request_mode, request_type, batches)

        # Determine output file path
        date_range = f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
        # Include request_mode and request_type (if minimal mode) in filename
        mode_suffix = f"_{request_mode}"
        if request_mode == 'minimal':
            mode_suffix += f"_{request_type}"
        default_filename = f"timestamp_predictions_{date_range}{mode_suffix}_{start_batch}.jsonl"

        if args.output:
            # Check if output path ends with / (directory specification)
            if args.output.endswith('/'):
                output_file = os.path.join(args.output, default_filename)
            else:
                output_file = args.output
        else:
            output_file = default_filename

        print(f"Output file pattern: {output_file}", flush=True)

        # Track inferences per file and current file index
        MAX_INFERENCES_PER_FILE = 100_000_000
        current_file_index = start_batch
        inferences_in_current_file = 0

        def get_output_filename(file_index):
            """Generate output filename with file index"""
            if args.output and not args.output.endswith('/'):
                # User specified full path, add file index before extension
                base = Path(args.output)
                return str(base.parent / f"{base.stem}_{file_index}{base.suffix}")
            else:
                # Use default filename pattern
                default_name = f"timestamp_predictions_{date_range}{mode_suffix}_{file_index}.jsonl"
                if args.output and args.output.endswith('/'):
                    return os.path.join(args.output, default_name)
                return default_name

        # Create first file
        current_output_file = get_output_filename(current_file_index)
        print(f"Starting with output file: {current_output_file}", flush=True)
        try:
            async with aiofiles.open(current_output_file, 'w') as f:
                pass  # Just create/truncate the file
        except Exception as e:
            print(f"Failed to create output file {current_output_file}: {e}", flush=True)
            raise

        lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(3)
        batch_delay = BATCH_DELAY

        async def process_batch(idx):
            nonlocal batch_delay, current_file_index, inferences_in_current_file, current_output_file
            try:
                print(f"Starting batch {idx} of {len(batches)}", flush=True)
                async with semaphore:
                    print(f"Processing batch {idx} of {len(batches)}", flush=True)
                    try:
                        batch_result = await retrieve_batch(batches[idx], idx, get_id_token, args.server)
                        print(f"Batch {idx}: Retrieved {len(batch_result)} results", flush=True)
                        # Write entire batch at once instead of individual results
                        if batch_result:
                            print(f"Batch {idx}: Appending {len(batch_result)} results to file...", flush=True)
                            async with lock:
                                # Check if we need to start a new file
                                if inferences_in_current_file + len(batch_result) > MAX_INFERENCES_PER_FILE:
                                    print(f"Reached {inferences_in_current_file:,} inferences in current file. Starting new file...", flush=True)
                                    current_file_index += 1
                                    inferences_in_current_file = 0
                                    current_output_file = get_output_filename(current_file_index)
                                    print(f"New output file: {current_output_file}", flush=True)
                                    # Create the new file
                                    async with aiofiles.open(current_output_file, 'w') as f:
                                        pass

                                await append_batch_to_jsonl(current_output_file, batch_result)
                                inferences_in_current_file += len(batch_result)
                                print(f"Batch {idx}: Finished appending to file. Total in current file: {inferences_in_current_file:,}", flush=True)
                        return len(batch_result) if batch_result else 0
                    except Exception as e:
                        print(f"Batch {idx} failed during processing: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                        # Increase delay on failure
                        batch_delay = min(batch_delay * BACKOFF_FACTOR, MAX_BACKOFF)
                        # Return 0 instead of crashing
                        return 0
                    finally:
                        # Small delay to prevent overwhelming the server
                        await asyncio.sleep(0.1)

                print(f"Completed batch {idx} of {len(batches)}", flush=True)
            except Exception as e:
                print(f"Batch {idx} failed completely: {e}", flush=True)
                import traceback
                traceback.print_exc()
                return 0

        # Process all batches, not just first 50
        tasks = []
        for i in range(start_batch, len(batches)):
            tasks.append(asyncio.create_task(process_batch(i)))
        
        try:
            print(f"Starting {len(tasks)} batch tasks...", flush=True)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for any exceptions in results
            failed_batches = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"Batch {start_batch + i} failed with exception: {result}", flush=True)
                    failed_batches += 1
            
            if failed_batches > 0:
                print(f"Warning: {failed_batches} out of {len(tasks)} batches failed", flush=True)
            else:
                print(f"All {len(tasks)} batches completed successfully", flush=True)

        except Exception as e:
            print(f"Critical error during batch processing: {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise

        finally:
            # Report all files created
            files_created = current_file_index - start_batch + 1
            if files_created == 1:
                print(f"Successfully completed processing. Output written to {current_output_file}", flush=True)
            else:
                print(f"Successfully completed processing. Created {files_created} output files:", flush=True)
                for i in range(start_batch, current_file_index + 1):
                    filename = get_output_filename(i)
                    print(f"  - {filename}", flush=True)
                
    except Exception as e:
        print(f"Fatal error in main(): {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise


async def retrieve_batch(batch, batch_idx=None, get_id_token=None, server=None):
    inferences = []
    retry_count = 0
    backoff = INITIAL_BACKOFF

    # Calculate expected number of inferences for this batch
    expected_inferences = 0
    for request in batch:
        # Each request has a list of timestamps, so we expect one inference per timestamp
        expected_inferences += len(request["timestamp"])

    batch_prefix = f"Batch {batch_idx}: " if batch_idx is not None else ""
    print(f"{batch_prefix}Expecting {expected_inferences} inferences for batch of {len(batch)} requests", flush=True)

    while retry_count < MAX_RETRIES:
        try:
            # Connect using connection.py
            ws = await connect(server)

            try:
                print(f"{batch_prefix}Requesting batch with {len(batch)} inference requests", flush=True)

                # Create message with token and inference requests
                if get_id_token is not None:
                    msg = {
                        'token': get_id_token(),
                        'inference': batch
                    }
                else:
                    # No authentication - send inference requests without token
                    msg = {
                        'inference': batch
                    }
                await ws.send(json.dumps(msg))
                
                last_message_time = time.time()
                accounted_inferences = 0  # Track inferences received + insufficient data responses
                
                while True:
                    current_time = time.time()
                    elapsed = current_time - last_message_time
                    remaining_timeout = max(0, TIMEOUT_SECONDS - elapsed)
                    
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=remaining_timeout)
                        msg_json = json.loads(msg)
                        last_message_time = time.time()  # Reset timer on any message
                        
                        if "inference" in msg_json:
                            inference_data = msg_json["inference"]
                            inferences.append(inference_data)
                            # Count the actual number of inferences in this message
                            if isinstance(inference_data, list):
                                inference_count = len(inference_data)
                            else:
                                inference_count = 1
                            accounted_inferences += inference_count
                            print(f"{batch_prefix}Received {inference_count} inferences. Total accounted: {accounted_inferences}/{expected_inferences}", flush=True)
                            
                        elif "message" in msg_json and msg_json["message"] == "insufficient data":
                            # Handle insufficient data responses - these count as accounted inferences
                            if "data" in msg_json:
                                insufficient_count = len(msg_json["data"])
                                accounted_inferences += insufficient_count
                                print(f"{batch_prefix}Received insufficient data for {insufficient_count} inferences. Total accounted: {accounted_inferences}/{expected_inferences}", flush=True)
                            else:
                                # If no data field, assume it's for one inference
                                accounted_inferences += 1
                                print(f"{batch_prefix}Received insufficient data response. Total accounted: {accounted_inferences}/{expected_inferences}", flush=True)
                        else:
                            # Check for throttling/error
                            if "error" in msg_json and "throttled" in msg_json["error"].lower():
                                raise Exception("Throttling detected")
                            print(f"{batch_prefix}Non-inference message: {msg[:1000]}...", flush=True)
                        
                        # Check if we have all inferences accounted for
                        if accounted_inferences >= expected_inferences:
                            inferences = list(chain(*inferences))
                            print(f"{batch_prefix}All {expected_inferences} inferences accounted for; batch complete with {len(inferences)} successful inferences", flush=True)
                            break

                    except asyncio.TimeoutError:
                        inferences = list(chain(*inferences))
                        print(f"{batch_prefix}Timeout after {TIMEOUT_SECONDS}s since last message; batch complete with {len(inferences)} inferences ({accounted_inferences}/{expected_inferences} accounted)", flush=True)
                        break

                # If we exit the try block without error, success—return
                return inferences

            finally:
                # Close the websocket connection
                await ws.close()

        except (websockets.ConnectionClosed, Exception) as e:
            # Print out detailed information about the error
            # including the stack trace if available
            if hasattr(e, 'message'):
                print(f"Error in batch retrieval: {e.message}", flush=True)
            
            # Print the stack trace if available
            if hasattr(e, '__traceback__'):
                import traceback
                print("Stack trace:", flush=True)
                traceback.print_tb(e.__traceback__)

            retry_count += 1
            if retry_count >= MAX_RETRIES:
                print(f"{batch_prefix}Max retries ({MAX_RETRIES}) exceeded, giving up on batch", flush=True)
                raise Exception("Max retries exceeded")
            
            print(f"{batch_prefix}Retry {retry_count}/{MAX_RETRIES} after error: {e}", flush=True)
            
            # Exponential backoff, cap at MAX_BACKOFF
            sleep_time = min(backoff, MAX_BACKOFF)
            await asyncio.sleep(sleep_time)
            backoff *= BACKOFF_FACTOR
            
            # Reconnection backoff if connection-related
            if isinstance(e, websockets.ConnectionClosed):
                recon_backoff = min(RECONNECT_BACKOFF * (2 ** retry_count), MAX_RECONNECT_BACKOFF)
                await asyncio.sleep(recon_backoff)

    return inferences

def get_request_parameters_default() -> List[tuple]:
    """
    Get the default set of request parameter combinations
    Returns all combinations of rfq_label, side, and ats_indicator

    Returns:
        List of (rfq_label, side, ats_indicator) tuples
    """
    return [
        ("spread", "bid", "N"),
        ("spread", "offer", "N"),
        ("spread", "bid", "Y"),
        ("spread", "offer", "Y"),
        ("price", "bid", "N"),
        ("price", "offer", "N"),
        ("price", "bid", "Y"),
        ("price", "offer", "Y"),
    ]


def get_request_parameters_minimal(request_type: str = "price") -> List[tuple]:
    """
    Get the minimal set of request parameter combinations
    Returns only bid/offer with ats_indicator = N for the specified request type

    Args:
        request_type: Type of request - "price" or "spread" (default: "price")

    Returns:
        List of (rfq_label, side, ats_indicator) tuples
    """
    if request_type not in ["price", "spread"]:
        raise ValueError(f"Invalid request_type '{request_type}'. Must be 'price' or 'spread'")

    return [
        (request_type, "bid", "N"),
        (request_type, "offer", "N"),
    ]


def get_request_parameters_full() -> List[tuple]:
    """
    Get the full set of request parameter combinations including quantity variations
    Returns all combinations of rfq_label, side, ats_indicator, and quantity

    Returns:
        List of (rfq_label, side, ats_indicator, quantity) tuples
    """
    quantities = [
        1_000,
        10_000,
        100_000,
        250_000,
        500_000,
        1_000_000,
        2_000_000,
        3_000_000,
        4_000_000,
        5_000_000,
    ]

    base_params = [
        ("spread", "bid", "N"),
        ("spread", "offer", "N"),
        ("spread", "bid", "Y"),
        ("spread", "offer", "Y"),
        ("price", "bid", "N"),
        ("price", "offer", "N"),
        ("price", "bid", "Y"),
        ("price", "offer", "Y"),
    ]

    return [
        (rfq_label, side, ats, quantity)
        for rfq_label, side, ats in base_params
        for quantity in quantities
    ]


# Registry of available request parameter modes
REQUEST_PARAMETER_MODES = {
    'default': get_request_parameters_default,
    'minimal': get_request_parameters_minimal,
    'full': get_request_parameters_full,
}


def get_inference_requests(figis, timestamps, figi_bond_info, request_mode: str = 'default', request_type: str = 'price') -> List[Dict[str, Any]]:
    """
    Generate inference requests for each FIGI and timestamp

    Args:
        figis: List of FIGI strings
        timestamps: List of timestamps
        figi_bond_info: Dictionary mapping FIGIs to bond information
        request_mode: Request parameter mode ('default' or 'minimal')
        request_type: Request type ('price' or 'spread') - only used with 'minimal' mode

    Returns:
        List of inference request dictionaries
    """
    if request_mode not in REQUEST_PARAMETER_MODES:
        raise ValueError(f"Unknown request mode '{request_mode}'. Available modes: {', '.join(REQUEST_PARAMETER_MODES.keys())}")

    # Get request parameters based on mode
    if request_mode == 'minimal':
        request_params = REQUEST_PARAMETER_MODES[request_mode](request_type)
    else:
        request_params = REQUEST_PARAMETER_MODES[request_mode]()

    # Pre-filter timestamps for each FIGI
    print("Pre-filtering timestamps based on bond settlement and maturity dates...", flush=True)
    figi_timestamps = {}
    total_timestamps_before = len(figis) * len(timestamps)
    total_timestamps_after = 0
    filtered_out_figis = []

    for figi in figis:
        bond_info = figi_bond_info[figi]
        settlement_date = bond_info['settlement_date']
        maturity_date = bond_info['maturity_date']
        # Filter timestamps for this FIGI
        figi_timestamps[figi] = [
            format_timestamp_for_api(t) for t in timestamps
            if settlement_date <= t <= maturity_date
        ]
        total_timestamps_after += len(figi_timestamps[figi])

        # Track FIGIs with no valid timestamps
        if len(figi_timestamps[figi]) == 0:
            filtered_out_figis.append((figi, settlement_date.strftime('%Y-%m-%d'), maturity_date.strftime('%Y-%m-%d')))

    if filtered_out_figis:
        print(f"Warning: {len(filtered_out_figis)} FIGIs have no valid timestamps (timestamps outside settlement/maturity range):", flush=True)
        for figi, settle, mature in filtered_out_figis[:10]:  # Show first 10
            print(f"  - {figi}: settlement={settle}, maturity={mature}", flush=True)
        if len(filtered_out_figis) > 10:
            print(f"  ... and {len(filtered_out_figis) - 10} more", flush=True)

    print(f"Timestamp filtering: {total_timestamps_before} -> {total_timestamps_after} timestamps ({total_timestamps_after}/{total_timestamps_before} kept)", flush=True)

    # Generate inference requests using pre-filtered timestamps
    # Check if request_params includes quantity (4-tuples) or not (3-tuples)
    if request_params and len(request_params[0]) == 4:
        # Full mode: includes quantity in the parameters
        inferences = [
            {
                "rfq_label": rfq_label,
                "figi": f,
                "quantity": quantity,
                "side": side,
                "ats_indicator": ats,
                "timestamp": figi_timestamps[f],  # Use pre-filtered timestamps
                "subscribe": False,
            }
            for f in figis
            for rfq_label, side, ats, quantity in request_params
        ]
    else:
        # Default/minimal modes: use fixed quantity of 1_000_000
        inferences = [
            {
                "rfq_label": rfq_label,
                "figi": f,
                "quantity": 1_000_000,
                "side": side,
                "ats_indicator": ats,
                "timestamp": figi_timestamps[f],  # Use pre-filtered timestamps
                "subscribe": False,
            }
            for f in figis
            for rfq_label, side, ats in request_params
        ]

    print(f"Generated {len(inferences)} inference requests for {len(figis)} FIGIs using '{request_mode}' mode ({len(request_params)} parameter combinations per FIGI)", flush=True)

    return inferences



if __name__ == '__main__':
    asyncio.run(main())
