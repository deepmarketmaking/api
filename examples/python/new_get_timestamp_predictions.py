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
import sys
import json
import asyncio
import boto3
import pandas as pd
import pytz
from datetime import datetime, time as dt_time, timedelta, date
from typing import List, Dict, Any, Optional, Set
import websockets
from collections import Counter
import time
import aiofiles

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

def load_universe() -> List[str]:
    """
    Load the universe of bonds from S3
    
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
    
# Returns a dictionary mapping FIGIs to objects containing issue date and maturity date
def figi_to_issue_date() -> Dict[str, Dict[str, datetime]]:
    """
    Load bond data from S3 and create a mapping from FIGI to bond information.
    
    Returns:
        Dict[str, Dict[str, datetime]]: A dictionary mapping FIGI to an object containing
        'issue_date' and 'maturity_date' as datetime objects.
    """
    # Download bond data from S3
    try:
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket='deepmm.public', Key='bond_data.json')
        content = response['Body'].read().decode('utf-8')
        bond_data = json.loads(content)
        
        # Create a mapping of FIGIs to bond information objects
        figi_bond_info = {}
        
        eastern_tz = pytz.timezone('US/Eastern')
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
    # Generate all days in the range
    delta = end_date - start_date
    all_days = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    
    # Filter out weekends (0 = Monday, 6 = Sunday in weekday())
    trading_days = [day for day in all_days if day.weekday() < 5]
    
    print(f"Found {len(trading_days)} trading days between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}", flush=True)
    return trading_days

def generate_timestamps(trading_days: List[datetime]) -> List[datetime]:
    """
    Generate timestamps for 9 AM and 4 PM ET on each trading day
    
    Args:
        trading_days: List of trading days
        
    Returns:
        List[datetime]: List of timestamps
    """
    eastern_tz = pytz.timezone('US/Eastern')
    timestamps = []
    
    for day in trading_days:
        # Create date object from the day
        day_date = day.date()
        
        # 9 AM ET
        morning = eastern_tz.localize(datetime.combine(day_date, dt_time(9, 0)))
        timestamps.append(morning)
        
        # 4 PM ET
        afternoon = eastern_tz.localize(datetime.combine(day_date, dt_time(16, 0)))
        timestamps.append(afternoon)
    
    print(f"Generated {len(timestamps)} timestamps", flush=True)
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


def add_indent(s, indent='    '):
    return '\n'.join(indent + line for line in s.splitlines())

async def append_item_to_json(file_path, item):
    async with aiofiles.open(file_path, 'rb+') as f:
        await f.seek(0, 2)
        pos = await f.tell()
        indented = add_indent(json.dumps(item, indent=4))
        data = indented.encode('utf-8')
        if pos == 1:
            await f.write(b'\n' + data)
        else:
            await f.write(b',\n' + data)

async def main():
    if len(sys.argv) < 2:
        print("Usage: python new_get_timestamp_predictions.py <evaluation year> <starting batch>", flush=True)
    
    year = int(sys.argv[1])
    start_batch = int(sys.argv[2])
    
    timestamps = generate_timestamps(get_trading_days(*get_start_and_end_date(year)))
    timestamp_count = len(timestamps)
    print(f"Timestamp count: {timestamp_count}", flush=True)
    figis = load_universe()
    figi_bond_info = figi_to_issue_date()
    inference_requests = get_inference_requests(figis, timestamps, figi_bond_info)

    batch_size = int(32_000 / timestamp_count) # Because each inference request has a list of timestamps.
    batches = [inference_requests[i:i + batch_size] for i in range(0, len(inference_requests), batch_size)]
    print(f"Batches count: {len(batches)}", flush=True)

    output_file = f"timestamp_predictions_{year}_{start_batch}.json"
    async with aiofiles.open(output_file, 'wb') as f:
        await f.write(b'[')

    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(6)  # Keep at 6 as you found this works well
    batch_delay = BATCH_DELAY
    
    async def process_batch(idx):
        nonlocal batch_delay
        async with semaphore:
            print(f"Processing batch {idx} of {len(batches)}", flush=True)
            try:
                batch_result = await retrieve_batch(batches[idx], idx)
                for result in batch_result:
                    async with lock:
                        await append_item_to_json(output_file, result)
            except Exception as e:
                print(f"Batch {idx} failed: {e}", flush=True)
                # Increase delay on failure
                batch_delay = min(batch_delay * BACKOFF_FACTOR, MAX_BACKOFF)
            finally:
                # Minimal delay to prevent overwhelming the server
                await asyncio.sleep(max(0.5, batch_delay))

    # Create all tasks at once - the semaphore will control concurrency
    tasks = [process_batch(i) for i in range(start_batch, len(batches))]
    
    try:
        await asyncio.gather(*tasks)

    finally:
        print(f"Saving results to local file for year {year} starting batch {start_batch}", flush=True)
        async with aiofiles.open(output_file, 'ab+') as f:
            await f.seek(0, 2)
            pos = await f.tell()
            if pos == 1:
                await f.write(b']')
            else:
                await f.write(b'\n]')


async def retrieve_batch(batch, batch_idx=None):
    uri = "ws://localhost:8855"
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
            async with websockets.connect(
                uri,
                max_size=10 ** 9,
                open_timeout=1,
                ping_timeout=None  # Detect dead connections quickly
            ) as ws:
                print(f"{batch_prefix}Requesting batch with {len(batch)} inference requests", flush=True)
                await ws.send(json.dumps({"inference":batch}))
                
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
                    
            # If we exit the with block without error, success—return
            return inferences

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
                raise Exception("Max retries exceeded")
            
            # Exponential backoff, cap at MAX_BACKOFF
            sleep_time = min(backoff, MAX_BACKOFF)
            await asyncio.sleep(sleep_time)
            backoff *= BACKOFF_FACTOR
            
            # Reconnection backoff if connection-related
            if isinstance(e, websockets.ConnectionClosed):
                recon_backoff = min(RECONNECT_BACKOFF * (2 ** retry_count), MAX_RECONNECT_BACKOFF)
                await asyncio.sleep(recon_backoff)

    return inferences

    

def get_start_and_end_date(year):
    start_date = datetime(year = year, month = 8, day = 1)
    end_date = datetime(year=year, month = 12, day = 31)
    end_date = min(end_date, datetime.now())
    return start_date,end_date

def get_inference_requests(figis, timestamps, figi_bond_info) -> List[Dict[str, Any]]:
    # Pre-filter timestamps for each FIGI
    print("Pre-filtering timestamps based on bond settlement and maturity dates...", flush=True)
    figi_timestamps = {}
    for figi in figis:
        bond_info = figi_bond_info[figi]
        settlement_date = bond_info['settlement_date']
        maturity_date = bond_info['maturity_date']
        # Filter timestamps for this FIGI
        figi_timestamps[figi] = [
            format_timestamp_for_api(t) for t in timestamps
            if settlement_date <= t <= maturity_date
        ]
    
    # Generate inference requests using pre-filtered timestamps
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
        for rfq_label, side, ats in [
            ("spread", "bid", "N"),
            ("spread", "offer", "N"),
            ("spread", "bid", "Y"),
            ("spread", "offer", "Y"),
            ("price", "bid", "N"),
            ("price", "offer", "N"),
            ("price", "bid", "Y"),
            ("price", "offer", "Y"),
        ]
    ]

    print(f"Generated {len(inferences)} inference requests for {len(figis)} FIGIs and {len(timestamps)} timestamps", flush=True)
    
    return inferences



if __name__ == '__main__':
    asyncio.run(main())
