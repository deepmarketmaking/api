#!/usr/bin/env python3
"""
Timestamp-based Model Evaluation Script

This script evaluates models at specific times of day (9 AM and 4 PM US/Eastern time)
on trading days for each bond in a universe file. For each bond and timestamp,
it runs four inferences (combinations of bid/offer side and ATS=Y/N).

This version uses the JSON API to query the websocket server instead of running
the model directly.

Error Handling:
- "insufficient data" errors: These are logged but don't affect the saving of other data.
  The script will continue to process and save all valid inference results.
- "throttling" errors: When these occur, the script implements exponential backoff and
  retries the batch that caused the throttling. The maximum number of retries and
  initial backoff delay are configurable.
- Connection errors: The script implements a ping/pong mechanism to keep the connection
  alive and will attempt to reconnect if the connection is lost.
"""

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
import argparse
from collections import Counter

# S3 bucket for results
S3_BUCKET = "deepmm.temp"
S3_FOLDER = "timestamp_predictions"

# Timeout in seconds after the last message before closing the connection
TIMEOUT_SECONDS = 60

# Initial delay between batches (seconds)
BATCH_DELAY = 0.1

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # Initial backoff delay in seconds
BACKOFF_FACTOR = 2.0   # Multiply delay by this factor for each retry

# Websocket ping interval in seconds
PING_INTERVAL = 15  # Reduced from 30 to 15 seconds to prevent timeouts

# Reconnection configuration
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BACKOFF = 2.0  # Initial backoff delay for reconnection in seconds

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
        
        print(f"Loaded {len(figi_strings)} bonds from universe.txt")
        
        return figi_strings
    except Exception as e:
        print(f"Error loading universe from S3: {e}")
        print("Using a small test set of FIGIs instead")
        # Return a small test set of FIGIs
        return ["BBG003LZRTD5", "BBG00BLVJYZ2", "BBG00D3FQP27"]

def get_trading_days(start_date: datetime, end_date: datetime, test_mode: bool = False) -> List[datetime]:
    """
    Get a list of trading days between start_date and end_date
    Simplified version that just excludes weekends
    
    Args:
        start_date: Start date
        end_date: End date
        test_mode: If True, only return the most recent trading day
        
    Returns:
        List[datetime]: List of trading days
    """
    # Generate all days in the range
    delta = end_date - start_date
    all_days = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    
    # Filter out weekends (0 = Monday, 6 = Sunday in weekday())
    trading_days = [day for day in all_days if day.weekday() < 5]
    
    if test_mode:
        # Filter to only the most recent trading day
        current_time = datetime.now()
        
        # Filter out future trading days
        past_trading_days = [day for day in trading_days if day.date() <= current_time.date()]
        
        if past_trading_days:
            # Get the most recent trading day
            most_recent_day = max(past_trading_days)
            trading_days = [most_recent_day]
            print(f"TEST MODE: Using only the most recent trading day: {most_recent_day.strftime('%Y-%m-%d')}")
        else:
            print("WARNING: No past trading days found in the specified range")
    
    print(f"Found {len(trading_days)} trading days between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}")
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
    
    print(f"Generated {len(timestamps)} timestamps")
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

def save_results(results: List[Dict], eval_year: str, rfq_label: str) -> str:
    """
    Save results to a CSV file and optionally upload to S3
    
    Args:
        results: List of result dictionaries
        eval_year: Year of evaluation
        rfq_label: RFQ label (price or spread)
        
    Returns:
        str: Path where results were saved
    """
    # Create a filename based on eval_year and rfq_label
    filename = f"timestamp_predictions_{eval_year}_{rfq_label}.csv"
    
    # Create a local file path in the current directory
    local_path = os.path.join(os.getcwd(), filename)
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)
    
    # Convert timestamp strings to datetime objects if present
    if 'timestamp' in results_df.columns and len(results_df) > 0:
        results_df['timestamp'] = pd.to_datetime(results_df['timestamp'])
    
    # Sort by timestamp, figi, side, and ats_indicator if present
    sort_columns = [col for col in ['timestamp', 'figi', 'side', 'ats_indicator'] if col in results_df.columns]
    if sort_columns:
        results_df = results_df.sort_values(sort_columns)
    
    # Save to CSV
    results_df.to_csv(local_path, index=False)
    print(f"Results saved to {local_path} ({len(results)} records)")
    
    # Try to upload to S3 if possible
    try:
        s3 = boto3.client('s3')
        s3_path = f"{S3_FOLDER}/{filename}"
        s3.upload_file(local_path, S3_BUCKET, s3_path)
        print(f"Results uploaded to s3://{S3_BUCKET}/{s3_path}")
        return f"s3://{S3_BUCKET}/{s3_path}"
    except Exception as e:
        print(f"Warning: Could not upload to S3: {e}")
        print(f"Results are still available locally at {local_path}")
        return local_path

# Shared variable for communication between coroutines
class SharedState:
    def __init__(self):
        self.throttling = False
        self.message_counts = Counter()
        self.last_message_time = datetime.now()
        self.last_ping_time = datetime.now()
        
        # Retry state
        self.current_batch_index = 0
        self.retry_batch_index = None
        self.retry_count = 0
        self.backoff_delay = INITIAL_BACKOFF
        
        # Connection state
        self.connection_active = True
        self.reconnect_count = 0
        self.reconnect_delay = RECONNECT_BACKOFF
        
        # Progress tracking
        self.processed_batch_indices = set()
        self.total_batches = 0

    def start_retry(self, batch_index: int):
        """
        Start retrying a batch
        
        Args:
            batch_index: Index of the batch to retry
        """
        self.throttling = True
        self.retry_batch_index = batch_index
        self.retry_count += 1
        self.backoff_delay = INITIAL_BACKOFF * (BACKOFF_FACTOR ** (self.retry_count - 1))
    
    def reset_retry(self):
        """
        Reset retry state
        """
        self.throttling = False
        self.retry_batch_index = None
        self.retry_count = 0
        self.backoff_delay = INITIAL_BACKOFF
    
    def mark_batch_processed(self, batch_index: int):
        """
        Mark a batch as processed
        
        Args:
            batch_index: Index of the batch to mark as processed
        """
        self.processed_batch_indices.add(batch_index)
    
    def is_batch_processed(self, batch_index: int) -> bool:
        """
        Check if a batch has been processed
        
        Args:
            batch_index: Index of the batch to check
            
        Returns:
            bool: True if the batch has been processed, False otherwise
        """
        return batch_index in self.processed_batch_indices
    
    def get_next_unprocessed_batch_index(self, start_index: int = 0) -> Optional[int]:
        """
        Get the next unprocessed batch index
        
        Args:
            start_index: Index to start searching from
            
        Returns:
            Optional[int]: The next unprocessed batch index, or None if all batches are processed
        """
        for i in range(start_index, self.total_batches):
            if not self.is_batch_processed(i):
                return i
        return None

async def ping_websocket(ws, shared_state):
    """
    Coroutine to send periodic pings to keep the websocket connection alive
    
    Args:
        ws: Websocket connection
        shared_state: Shared state between coroutines
    """
    ping_count = 0
    pong_count = 0
    
    # Set up a pong waiter
    pong_waiter = None
    
    # Register a pong handler
    async def pong_handler(data):
        nonlocal pong_count
        pong_count += 1
        print(f"Received pong response (ping: {ping_count}, pong: {pong_count})")
        shared_state.last_message_time = datetime.now()  # Update last message time on pong
    
    # Register the pong handler
    ws.pong_handlers.append(pong_handler)
    
    while shared_state.connection_active:
        try:
            # Check if it's time to send a ping
            time_since_last_ping = (datetime.now() - shared_state.last_ping_time).total_seconds()
            if time_since_last_ping >= PING_INTERVAL:
                # Send a ping
                ping_count += 1
                await ws.ping(f"ping-{ping_count}".encode())
                shared_state.last_ping_time = datetime.now()
                print(f"Sent websocket ping #{ping_count} to keep connection alive")
            
            # Wait a bit before checking again, but not too long
            await asyncio.sleep(2)  # Check more frequently
            
            # Check if we're missing pongs
            if ping_count > pong_count + 3:
                print(f"WARNING: Missing pong responses (ping: {ping_count}, pong: {pong_count})")
                # Force a reconnection if we're missing too many pongs
                if ping_count > pong_count + 5:
                    print("Too many missing pongs, forcing reconnection")
                    shared_state.connection_active = False
                    break
                
        except Exception as e:
            print(f"Error in ping task: {e}")
            # Don't break the loop, just try again soon
            await asyncio.sleep(2)
    
    # Clean up
    if ws.pong_handlers and pong_handler in ws.pong_handlers:
        ws.pong_handlers.remove(pong_handler)
    
    print("Ping task ending")

async def send_batches(ws, batches, batch_size, shared_state):
    """
    Coroutine to send batches of requests to the websocket server
    
    Args:
        ws: Websocket connection
        batches: List of batches to send
        batch_size: Size of each batch
        shared_state: Shared state between coroutines
    """
    total_batches = len(batches)
    shared_state.total_batches = total_batches
    
    # Start from the first unprocessed batch
    i = shared_state.get_next_unprocessed_batch_index(0)
    if i is None:
        print("All batches have been processed")
        return
    
    while i < total_batches and shared_state.connection_active:
        # Check if we're retrying a specific batch due to throttling
        if shared_state.throttling and shared_state.retry_batch_index is not None:
            # Get the batch to retry
            retry_index = shared_state.retry_batch_index
            batch = batches[retry_index]
            
            # Calculate backoff delay with exponential backoff
            backoff_delay = shared_state.backoff_delay
            
            print(f"Throttling detected, retrying batch {retry_index+1}/{total_batches} (attempt {shared_state.retry_count}/{MAX_RETRIES}) after {backoff_delay:.2f}s delay")
            await asyncio.sleep(backoff_delay)
            
            # Check if we've exceeded the maximum number of retries
            if shared_state.retry_count >= MAX_RETRIES:
                print(f"Maximum retries ({MAX_RETRIES}) exceeded for batch {retry_index+1}, moving to next batch")
                shared_state.reset_retry()
                i = retry_index + 1  # Move to the next batch
                continue
            
            # Send the retry batch
            try:
                msg = {'inference': batch}
                await ws.send(json.dumps(msg))
                print(f"Retrying batch {retry_index+1}/{total_batches} ({len(batch)} requests)")
                
                # Update the current batch index
                shared_state.current_batch_index = retry_index
                
                # Wait for the receiver to process the response
                # We don't increment i here because we're retrying the same batch
                await asyncio.sleep(0.5)  # Short delay to allow receiver to process
            except Exception as e:
                print(f"Error sending retry batch {retry_index+1}: {e}")
                shared_state.connection_active = False
                break
            
        else:
            # Skip already processed batches
            if shared_state.is_batch_processed(i):
                i += 1
                continue
            
            # Normal batch sending (not retrying)
            batch = batches[i]
            
            # Normal delay between batches
            await asyncio.sleep(BATCH_DELAY)
            
            # Prepare the request message
            msg = {'inference': batch}
            
            # Send the request
            try:
                await ws.send(json.dumps(msg))
                print(f"Sent batch {i+1}/{total_batches} ({len(batch)} requests)")
                
                # Update the current batch index
                shared_state.current_batch_index = i
                
                # Move to the next batch
                i += 1
            except Exception as e:
                print(f"Error sending batch {i+1}: {e}")
                shared_state.connection_active = False
                break
    
    if i >= total_batches:
        print(f"All {total_batches} batches sent")

async def receive_messages(ws, eval_year, rfq_label, shared_state, all_results):
    """
    Coroutine to receive and process messages from the websocket server
    
    Args:
        ws: Websocket connection
        eval_year: Year of evaluation
        rfq_label: RFQ label (price or spread)
        shared_state: Shared state between coroutines
        all_results: List of all results received so far
    
    Returns:
        List[Dict]: List of all results received
    """
    last_save_time = datetime.now()
    save_interval = 10  # Save every 10 seconds
    
    # Track unexpected formats to avoid repeated warnings
    unexpected_formats = set()
    max_warnings = 3  # Maximum number of unique warnings to show
    
    # Track message counts for summary
    last_count_report_time = datetime.now()
    count_report_interval = 5  # Report counts every 5 seconds
    
    # Heartbeat tracking
    last_heartbeat_time = datetime.now()
    heartbeat_interval = 5  # Check connection every 5 seconds
    
    print(f"Starting to receive messages (will timeout after {TIMEOUT_SECONDS} seconds of inactivity)")
    
    # Flag to indicate if we're still expecting messages
    expecting_messages = True
    
    while expecting_messages and shared_state.connection_active:
        try:
            # Wait for a message with a timeout
            message_task = asyncio.create_task(ws.recv())
            done, pending = await asyncio.wait(
                [message_task], 
                timeout=1.0  # Short timeout to check frequently
            )
            
            # If we got a message, process it
            if message_task in done:
                response = await message_task
                response_json = json.loads(response)
                
                # Update the last message time
                shared_state.last_message_time = datetime.now()
                
                # Process the response
                if 'inference' in response_json and isinstance(response_json['inference'], list):
                    # This is a normal inference response with results
                    batch_results = response_json['inference']
                    all_results.extend(batch_results)
                    
                    # Print progress update (just the count, not the actual data)
                    print(f"Received {len(batch_results)} results, total: {len(all_results)}")
                    
                    # Save results periodically (not on every message to avoid excessive I/O)
                    time_since_last_save = (datetime.now() - last_save_time).total_seconds()
                    if time_since_last_save >= save_interval:
                        save_results(all_results, eval_year, rfq_label)
                        last_save_time = datetime.now()
                    
                    # Update message counts
                    shared_state.message_counts['inference'] += 1
                    
                    # If we were retrying a batch and got a successful response, reset retry state
                    if shared_state.throttling and shared_state.retry_batch_index is not None:
                        print(f"Retry successful for batch {shared_state.retry_batch_index+1}")
                        # Mark the batch as processed
                        shared_state.mark_batch_processed(shared_state.retry_batch_index)
                        shared_state.reset_retry()
                    else:
                        # Mark the current batch as processed
                        shared_state.mark_batch_processed(shared_state.current_batch_index)
                    
                elif 'message' in response_json:
                    # This is a message response (like 'insufficient data' or 'throttling')
                    # These messages don't affect the saving of other data - they're just informational
                    message = response_json['message']
                    
                    # Update message counts
                    shared_state.message_counts[message] += 1
                    
                    # Special handling for specific messages
                    if message == 'deactivated':
                        print("Received deactivation message from server")
                        expecting_messages = False
                    elif message == 'throttling':
                        # Start retrying the current batch
                        if not shared_state.throttling:  # Only start a new retry if we're not already retrying
                            shared_state.start_retry(shared_state.current_batch_index)
                            print(f"Server is throttling requests for batch {shared_state.current_batch_index+1}")
                        else:
                            # Only print throttling messages occasionally
                            if shared_state.message_counts[message] <= 1 or shared_state.message_counts[message] % 10 == 0:
                                print(f"Server is throttling requests (count: {shared_state.message_counts[message]})")
                    elif message == 'insufficient data':
                        # Only print insufficient data messages occasionally
                        if shared_state.message_counts[message] <= 1 or shared_state.message_counts[message] % 10 == 0:
                            print(f"Server reports insufficient data (count: {shared_state.message_counts[message]})")
                            print("Note: 'insufficient data' errors don't affect the saving of other valid results")
                    else:
                        print(f"Received message: {message}")
                else:
                    # Handle unexpected formats
                    format_key = str(sorted(response_json.keys()))
                    if format_key not in unexpected_formats and len(unexpected_formats) < max_warnings:
                        unexpected_formats.add(format_key)
                        print(f"Note: Received message with keys: {format_key}")
                        
                        # If this is a heartbeat or acknowledgment, don't treat it as an error
                        if 'status' in response_json or 'ack' in response_json:
                            print("This appears to be a status or acknowledgment message")
                            shared_state.message_counts['status/ack'] += 1
                        else:
                            shared_state.message_counts['unknown'] += 1
                
                # Periodically report message counts
                time_since_last_count_report = (datetime.now() - last_count_report_time).total_seconds()
                if time_since_last_count_report >= count_report_interval:
                    # Only report if we have a significant number of messages
                    if sum(shared_state.message_counts.values()) > 10:
                        print(f"Message counts: {dict(shared_state.message_counts)}")
                    last_count_report_time = datetime.now()
                
                # Heartbeat check
                time_since_last_heartbeat = (datetime.now() - last_heartbeat_time).total_seconds()
                if time_since_last_heartbeat >= heartbeat_interval:
                    # Check connection health
                    time_since_last_message = (datetime.now() - shared_state.last_message_time).total_seconds()
                    if time_since_last_message > PING_INTERVAL * 3:
                        print(f"WARNING: No messages for {time_since_last_message:.1f} seconds, connection may be stale")
                        
                        # If it's been too long, force a reconnection
                        if time_since_last_message > PING_INTERVAL * 5:
                            print("Connection appears stale, forcing reconnection")
                            shared_state.connection_active = False
                            break
                    
                    last_heartbeat_time = datetime.now()
                
            else:
                # If we timed out, check if it's been long enough since the last message
                time_since_last = (datetime.now() - shared_state.last_message_time).total_seconds()
                if time_since_last >= TIMEOUT_SECONDS:
                    print(f"No messages received for {TIMEOUT_SECONDS} seconds. Stopping receiver.")
                    expecting_messages = False
                
                # Cancel the pending task
                for task in pending:
                    task.cancel()
                
        except asyncio.CancelledError:
            # Task was cancelled, continue the loop
            continue
        except Exception as e:
            print(f"Error receiving message: {e}")
            shared_state.connection_active = False
            break
    
    # Print final message counts
    print("\nFinal message counts:")
    for message_type, count in sorted(shared_state.message_counts.items()):
        print(f"  {message_type}: {count}")
    
    return all_results

async def evaluate_at_timestamps(eval_year: str, server_address: str, 
                               rfq_label: str = 'spread', test_mode: bool = False):
    """
    Evaluate at specific timestamps using the websocket API
    
    Args:
        eval_year: Year to evaluate on
        server_address: Domain:port of the websocket server
        rfq_label: RFQ label (price or spread)
        test_mode: If True, only evaluate on the most recent trading day
    """
    if test_mode:
        print(f"TEST MODE: Evaluating for year {eval_year} with RFQ label '{rfq_label}' on most recent trading day only")
    else:
        print(f"Evaluating for year {eval_year} with RFQ label '{rfq_label}'")
    
    # Load the universe of bonds
    figi_strings = load_universe()
    
    # Set date range for evaluation
    start_date = datetime(int(eval_year), 1, 1)
    end_date = datetime(int(eval_year), 12, 31)
    
    # Get trading days
    trading_days = get_trading_days(start_date, end_date, test_mode)
    
    # Generate timestamps
    timestamps = generate_timestamps(trading_days)
    
    # Filter out future timestamps if evaluating the current year
    current_year = datetime.now().year
    if int(eval_year) == current_year and not test_mode:
        current_time = datetime.now(pytz.timezone('US/Eastern'))
        timestamps = [ts for ts in timestamps if ts <= current_time]
        print(f"Filtered timestamps to only include past timestamps for current year {current_year}")
        print(f"Remaining timestamps: {len(timestamps)}")
    elif test_mode and len(timestamps) == 0:
        # In test mode, if no timestamps remain after filtering, use a timestamp from yesterday
        eastern_tz = pytz.timezone('US/Eastern')
        yesterday = datetime.now(eastern_tz) - timedelta(days=1)
        yesterday_9am = eastern_tz.localize(datetime.combine(yesterday.date(), dt_time(9, 0)))
        timestamps = [yesterday_9am]
        print(f"Test mode: Using 9 AM timestamp from yesterday ({yesterday.date()}) since no valid timestamps were found")
    
    # Define the four combinations
    combinations = [
        ('bid', 'Y'),    # Bid, ATS=Y
        ('bid', 'N'),    # Bid, ATS=N
        ('offer', 'Y'),  # Offer, ATS=Y
        ('offer', 'N'),  # Offer, ATS=N
    ]
    
    # Calculate total number of inferences
    total_inferences = len(figi_strings) * len(timestamps) * len(combinations)
    print(f"Total inferences to run: {total_inferences}")
    
    # Create all combinations of FIGI, timestamp, and side/ATS
    all_combinations = []
    for figi in figi_strings:
        for ts in timestamps:
            for side, ats in combinations:
                all_combinations.append((figi, ts, side, ats))
    
    print(f"Generated {len(all_combinations)} combinations")
    
    # Process combinations in batches of 1,500
    batch_size = 1500
    
    # Create batches of inference requests
    batches = []
    for i in range(0, len(all_combinations), batch_size):
        batch_combinations = all_combinations[i:i+batch_size]
        
        # Create batch of inference requests
        batch_requests = []
        for figi, ts, side, ats in batch_combinations:
            # Format timestamp for API
            ts_str = format_timestamp_for_api(ts)
            
            # Create inference request
            request = {
                'rfq_label': rfq_label,
                'figi': figi,
                'quantity': 1_000_000,
                'side': side,
                'ats_indicator': ats,
                'timestamp': [ts_str],
                'subscribe': False,
            }
            batch_requests.append(request)
        
        batches.append(batch_requests)
    
    print(f"Created {len(batches)} batches")
    
    # Create shared state for communication between coroutines
    shared_state = SharedState()
    
    # Try to load existing results if available
    all_results = []
    filename = f"timestamp_predictions_{eval_year}_{rfq_label}.csv"
    local_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(local_path):
        try:
            print(f"Found existing results file: {local_path}")
            results_df = pd.read_csv(local_path)
            all_results = results_df.to_dict('records')
            print(f"Loaded {len(all_results)} existing results")
        except Exception as e:
            print(f"Error loading existing results: {e}")
            all_results = []
    
    # Reconnection loop
    reconnect_attempts = 0
    while reconnect_attempts <= MAX_RECONNECT_ATTEMPTS:
        try:
            # Reset connection state
            shared_state.connection_active = True
            
            print(f"Connecting to websocket server at {server_address} (attempt {reconnect_attempts+1}/{MAX_RECONNECT_ATTEMPTS+1})")
            # Configure websocket with ping_interval and ping_timeout
            async with websockets.connect(
                f"ws://{server_address}",
                ping_interval=PING_INTERVAL,
                ping_timeout=PING_INTERVAL*2,
                close_timeout=10
            ) as ws:
                print("Connected to websocket server")
                
                # Start the ping task to keep the connection alive
                ping_task = asyncio.create_task(ping_websocket(ws, shared_state))
                
                # Run the send and receive coroutines concurrently
                sender = asyncio.create_task(send_batches(ws, batches, batch_size, shared_state))
                receiver = asyncio.create_task(receive_messages(ws, eval_year, rfq_label, shared_state, all_results))
                
                # Wait for both coroutines to complete
                await asyncio.gather(sender, receiver)
                
                # Cancel the ping task
                ping_task.cancel()
                
                # If we got here without an exception, we're done
                break
        
        except Exception as e:
            print(f"Error with websocket connection: {e}")
            
            # Save results before reconnecting
            if all_results:
                save_results(all_results, eval_year, rfq_label)
                print(f"Saved {len(all_results)} results before reconnecting")
            
            # Increment reconnect attempts
            reconnect_attempts += 1
            
            if reconnect_attempts <= MAX_RECONNECT_ATTEMPTS:
                # Calculate backoff delay with exponential backoff
                reconnect_delay = RECONNECT_BACKOFF * (2 ** (reconnect_attempts - 1))
                print(f"Reconnecting in {reconnect_delay:.2f} seconds...")
                await asyncio.sleep(reconnect_delay)
            else:
                print(f"Maximum reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) exceeded")
    
    # Final save of results
    if all_results:
        save_results(all_results, eval_year, rfq_label)
        print(f"Final results saved: {len(all_results)} total results")
    else:
        print("No results to save - no inferences were successful")

def main():
    """
    Main function
    """
    parser = argparse.ArgumentParser(description='Evaluate at specific timestamps using the websocket API')
    parser.add_argument('eval_year', help='Year to evaluate on')
    parser.add_argument('server_address', help='Domain:port of the websocket server (e.g., localhost:8855)')
    parser.add_argument('--rfq-label', choices=['price', 'spread'], default='spread',
                        help='RFQ label (price or spread, default: spread)')
    parser.add_argument('--test', action='store_true', help='Test mode: only evaluate on the most recent trading day')
    parser.add_argument('--timeout', type=int, default=120,
                        help='Timeout in seconds after the last message before closing the connection (default: 120)')
    parser.add_argument('--batch-delay', type=float, default=0.2,
                        help='Delay in seconds between sending batches (default: 0.2)')
    parser.add_argument('--max-retries', type=int, default=3,
                        help='Maximum number of retries for throttled batches (default: 3)')
    parser.add_argument('--backoff-factor', type=float, default=2.0,
                        help='Exponential backoff factor for retries (default: 2.0)')
    parser.add_argument('--ping-interval', type=int, default=15,
                        help='Interval in seconds between websocket pings (default: 15)')
    parser.add_argument('--max-reconnect', type=int, default=5,
                        help='Maximum number of reconnection attempts (default: 5)')
    
    args = parser.parse_args()
    
    # Set the global parameters
    global TIMEOUT_SECONDS, BATCH_DELAY, MAX_RETRIES, BACKOFF_FACTOR, PING_INTERVAL, MAX_RECONNECT_ATTEMPTS
    TIMEOUT_SECONDS = args.timeout
    BATCH_DELAY = args.batch_delay
    MAX_RETRIES = args.max_retries
    BACKOFF_FACTOR = args.backoff_factor
    PING_INTERVAL = args.ping_interval
    MAX_RECONNECT_ATTEMPTS = args.max_reconnect
    
    asyncio.run(evaluate_at_timestamps(
        args.eval_year,
        args.server_address,
        args.rfq_label,
        args.test
    ))

if __name__ == "__main__":
    main()