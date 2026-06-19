#!/usr/bin/env python3
"""
Update Universe Script

This script fetches bond data from S3, creates timestamp inference requests for all bonds,
queries the websocket server, and uploads the resulting universe to S3.

The universe includes bonds where we can get at least one inference using a timestamp
on or before the day before the maturity date (configurable via --min-date).
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any

import boto3
import pytz

from authentication import create_get_id_token
from connection import connect


# Timeout in seconds after the last message before closing the connection
TIMEOUT_SECONDS = 20


def load_bond_data() -> List[Dict[str, Any]]:
    """
    Load bond data from S3

    Returns:
        List[Dict]: List of bond dictionaries
    """
    try:
        s3 = boto3.client('s3')
        print('Retrieving bond_data.json from S3...', flush=True)
        response = s3.get_object(Bucket='deepmm.public', Key='bond_data.json')
        content = response['Body'].read().decode('utf-8')
        bonds = json.loads(content)
        print(f'Finished retrieving bond_data.json - loaded {len(bonds)} bonds', flush=True)
        return bonds
    except Exception as e:
        print(f"Error loading bond data from S3: {e}", flush=True)
        raise


def upload_universe_to_s3(universe: List[str]) -> None:
    """
    Upload universe.txt to S3

    Args:
        universe: List of FIGIs to upload
    """
    try:
        s3 = boto3.client('s3')
        print(f'Uploading universe.txt with {len(universe)} FIGIs...', flush=True)

        # Convert universe to text content (one FIGI per line)
        content = '\n'.join(universe)

        s3.put_object(
            Bucket='deepmm.public',
            Key='universe.txt',
            Body=content.encode('utf-8'),
            ContentType='text/plain',
            Tagging='public=true'
        )
        print('Finished uploading universe.txt', flush=True)
    except Exception as e:
        print(f"Error uploading universe to S3: {e}", flush=True)
        raise


def filter_bonds_by_min_date(bonds: List[Dict[str, Any]], min_date: datetime) -> List[Dict[str, Any]]:
    """
    Filter bonds to only include those where we can get an inference using
    a timestamp on or before the day before their maturity date, but not earlier
    than min_date.

    Args:
        bonds: List of bond dictionaries
        min_date: Minimum date for inference timestamp

    Returns:
        List[Dict]: Filtered list of bonds
    """
    eastern_tz = pytz.timezone('US/Eastern')
    filtered_bonds = []

    for bond in bonds:
        # Parse maturity date
        maturity_date_str = bond['m']  # Format: YYYY-MM-DD
        maturity_date = eastern_tz.localize(datetime.strptime(maturity_date_str, '%Y-%m-%d'))

        # Calculate the day before maturity
        day_before_maturity = maturity_date - timedelta(days=1)

        # Include bond if day_before_maturity is on or after min_date
        if day_before_maturity >= min_date:
            filtered_bonds.append(bond)

    print(f'Filtered bonds by min_date {min_date.strftime("%Y-%m-%d")}: {len(bonds)} -> {len(filtered_bonds)} bonds', flush=True)
    return filtered_bonds


async def get_universe_from_server(bonds: List[Dict[str, Any]], get_id_token, server: str = None) -> List[str]:
    """
    Send inference requests to the server and collect universe of FIGIs that return valid inferences

    Args:
        bonds: List of bond dictionaries
        get_id_token: Function that returns a valid authentication token
        server: WebSocket server URL (optional)

    Returns:
        List[str]: List of FIGIs that returned valid inferences
    """
    # Create timestamp inference request for all the bonds
    # Use current timestamp
    current_timestamp = datetime.now(pytz.UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    template = {
        'rfq_label': 'spread',
        'quantity': 1_000_000,
        'side': 'bid',
        'ats_indicator': 'N',
        'subscribe': False,
        'timestamp': [current_timestamp]
    }

    inference_requests = []
    for bond in bonds:
        inference_requests.append({
            **template,
            'figi': bond['F']
        })

    print(f'Created {len(inference_requests)} inference requests', flush=True)

    # Connect to the WebSocket server
    ws = await connect(server)

    try:
        print('Sending inference requests...', flush=True)

        # Create message with token and inference requests
        msg = {
            'token': get_id_token(),
            'inference': inference_requests
        }
        await ws.send(json.dumps(msg))
        print('Finished sending inference requests', flush=True)

        # Listen for responses
        universe = []
        last_message_time = asyncio.get_event_loop().time()

        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - last_message_time
            remaining_timeout = max(0, TIMEOUT_SECONDS - elapsed)

            try:
                # Wait for message with timeout
                msg = await asyncio.wait_for(ws.recv(), timeout=remaining_timeout)
                print('Receiving message...', flush=True)

                msg_json = json.loads(msg)
                last_message_time = asyncio.get_event_loop().time()  # Reset timer

                # Extract FIGIs from inference responses
                if 'inference' in msg_json:
                    inference_data = msg_json['inference']
                    # Handle both single inference and list of inferences
                    if isinstance(inference_data, list):
                        for inference in inference_data:
                            if 'figi' in inference:
                                universe.append(inference['figi'])
                    elif isinstance(inference_data, dict) and 'figi' in inference_data:
                        universe.append(inference_data['figi'])

                    print(f'Received {len(universe)} FIGIs so far...', flush=True)

                print('Finished receiving message', flush=True)

            except asyncio.TimeoutError:
                # Timeout reached - no more messages expected
                print(f'Timeout after {TIMEOUT_SECONDS}s since last message; closing connection', flush=True)
                break

        print(f'Universe length: {len(universe)}', flush=True)
        return universe

    finally:
        # Close the WebSocket
        print('Closing WebSocket...', flush=True)
        await ws.close()


async def main():
    parser = argparse.ArgumentParser(
        description='Update the bond universe based on available inference data'
    )
    parser.add_argument('username', type=str, help='Deep MM username')
    parser.add_argument('password', type=str, help='Deep MM password')
    parser.add_argument(
        '--min-date',
        type=str,
        required=True,
        help='Minimum date (YYYY-MM-DD) - bonds must have at least one inference available on or after this date (using day before maturity)'
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
        '--no-upload',
        action='store_true',
        help='Do not upload universe to S3 (dry run mode)'
    )

    args = parser.parse_args()

    # Get client_id from args or environment variable
    client_id = args.client_id
    if client_id is None:
        client_id = os.getenv('COGNITO_CLIENT_ID')
        if client_id is None:
            print('Error: Cognito client ID must be provided via --client-id or COGNITO_CLIENT_ID environment variable')
            sys.exit(1)

    # Parse min_date
    try:
        eastern_tz = pytz.timezone('US/Eastern')
        min_date = eastern_tz.localize(datetime.strptime(args.min_date, '%Y-%m-%d'))
        print(f'Using minimum date: {min_date.strftime("%Y-%m-%d")}', flush=True)
    except ValueError as e:
        print(f'Error: Invalid date format for --min-date: {e}')
        sys.exit(1)

    # Create authentication function
    print('Authenticating...', flush=True)
    get_id_token = create_get_id_token(args.region, client_id, args.username, args.password)
    # Test authentication by calling once
    get_id_token()
    print('Finished authenticating', flush=True)

    try:
        # Load bond data
        bonds = load_bond_data()

        # Filter bonds by min_date
        bonds = filter_bonds_by_min_date(bonds, min_date)

        if len(bonds) == 0:
            print('Warning: No bonds pass the min_date filter', flush=True)
            sys.exit(0)

        # Get universe from server
        universe = await get_universe_from_server(bonds, get_id_token, args.server)

        if len(universe) == 0:
            print('Warning: No bonds returned valid inferences - universe is empty', flush=True)
            if not args.no_upload:
                print('Skipping upload of empty universe', flush=True)
            sys.exit(0)

        # Upload to S3 (unless --no-upload is specified)
        if args.no_upload:
            print('Dry run mode - skipping S3 upload', flush=True)
            print(f'Would have uploaded {len(universe)} FIGIs:', flush=True)
            for figi in universe[:10]:
                print(f'  {figi}', flush=True)
            if len(universe) > 10:
                print(f'  ... and {len(universe) - 10} more', flush=True)
        else:
            upload_universe_to_s3(universe)
            print(f'Successfully updated universe with {len(universe)} FIGIs', flush=True)

    except Exception as e:
        print(f'Fatal error in main(): {e}', flush=True)
        import traceback
        traceback.print_exc()

        # Could optionally send SNS notification here like the original JS version
        # For now, just re-raise the error
        raise


if __name__ == '__main__':
    asyncio.run(main())
