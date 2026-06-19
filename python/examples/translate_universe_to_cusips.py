#!/usr/bin/env python3
"""
Universe FIGI to CUSIP Translator

This script downloads the universe.txt file from S3 (containing FIGIs),
translates them to CUSIPs using bond_data.json, and outputs the results
to a text file.
"""

import argparse
import boto3
import json
from typing import Dict, List, Set


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
        raise


def load_figi_to_cusip_mapping() -> Dict[str, str]:
    """
    Load FIGI to CUSIP mapping from bond_data.json on S3

    Returns:
        Dict[str, str]: Dictionary mapping FIGIs to CUSIPs
    """
    try:
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket='deepmm.public', Key='bond_data.json')
        content = response['Body'].read().decode('utf-8')
        bond_data = json.loads(content)

        # Create FIGI to CUSIP mapping
        figi_to_cusip = {bond['F']: bond['C'] for bond in bond_data}

        print(f"Loaded FIGI to CUSIP mapping for {len(figi_to_cusip)} bonds")

        return figi_to_cusip
    except Exception as e:
        print(f"Error loading bond data from S3: {e}")
        raise


def translate_universe_to_cusips(output_file: str):
    """
    Download universe, translate FIGIs to CUSIPs, and write to output file

    Args:
        output_file: Path to output text file
    """
    print("Loading universe from S3...")
    figis = load_universe()

    print("Loading FIGI to CUSIP mapping from S3...")
    figi_to_cusip = load_figi_to_cusip_mapping()

    print("Translating FIGIs to CUSIPs...")
    cusips = []
    missing_figis = []

    for figi in figis:
        if figi in figi_to_cusip:
            cusips.append(figi_to_cusip[figi])
        else:
            missing_figis.append(figi)

    # Report any missing FIGIs
    if missing_figis:
        print(f"\nWarning: {len(missing_figis)} FIGIs not found in bond_data.json:")
        for figi in missing_figis[:10]:  # Show first 10
            print(f"  - {figi}")
        if len(missing_figis) > 10:
            print(f"  ... and {len(missing_figis) - 10} more")

    # Write CUSIPs to output file
    print(f"\nWriting {len(cusips)} CUSIPs to {output_file}...")
    with open(output_file, 'w') as f:
        for cusip in cusips:
            f.write(f"{cusip}\n")

    print(f"Successfully wrote {len(cusips)} CUSIPs to {output_file}")
    print(f"Success rate: {len(cusips)}/{len(figis)} ({100 * len(cusips) / len(figis):.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description='Download universe.txt and translate FIGIs to CUSIPs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python translate_universe_to_cusips.py universe_cusips.txt

This will:
  1. Download universe.txt from s3://deepmm.public/universe.txt
  2. Download bond_data.json from s3://deepmm.public/bond_data.json
  3. Translate each FIGI in the universe to its CUSIP
  4. Write one CUSIP per line to universe_cusips.txt
"""
    )
    parser.add_argument('output_file', type=str, help='Output text file for CUSIPs (one per line)')

    args = parser.parse_args()

    try:
        translate_universe_to_cusips(args.output_file)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == '__main__':
    main()
