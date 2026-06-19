#!/usr/bin/env python3
"""
Segment timestamp predictions Parquet files into smaller files.

This script reads a large Parquet file produced by convert_timestamp_predictions_jsonl_to_parquet.py
and splits it into smaller Parquet files with a maximum number of rows per file.

The output files are named: {input_path_without_extension}_0.parquet, ..., {input_path_without_extension}_n.parquet
where n is the maximum index of the segmented output files.
"""

import argparse
import sys
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    print("Error: pyarrow library not found. Please install it with: pip install pyarrow", file=sys.stderr)
    sys.exit(1)


def segment_parquet_file(input_path: str, max_rows_per_file: int, output_dir: str = None):
    """
    Segment a large Parquet file into smaller files with a maximum number of rows per file.

    Args:
        input_path: Path to input Parquet file
        max_rows_per_file: Maximum number of rows per output file
        output_dir: Optional directory for output files (default: same as input file)
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not input_file.suffix == '.parquet':
        raise ValueError(f"Input file must be a Parquet file: {input_path}")

    if max_rows_per_file <= 0:
        raise ValueError(f"max_rows_per_file must be positive: {max_rows_per_file}")

    # Determine output directory
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = input_file.parent

    # Generate output file name pattern
    # Remove .parquet extension and add segment index
    base_name = input_file.stem
    output_pattern = output_path / f"{base_name}_{{}}.parquet"

    print(f"Segmenting {input_file}...")
    print(f"Max rows per file: {max_rows_per_file:,}")
    print(f"Output pattern: {output_pattern}")

    # Read the input Parquet file
    print("Reading input file...")
    table = pq.read_table(input_path)
    total_rows = table.num_rows
    print(f"Total rows in input file: {total_rows:,}")

    # Calculate number of output files
    num_files = (total_rows + max_rows_per_file - 1) // max_rows_per_file
    print(f"Will create {num_files} output file(s)")

    # Process in exact slices
    file_index = 0
    start_row = 0

    while start_row < total_rows:
        end_row = min(start_row + max_rows_per_file, total_rows)
        rows_in_segment = end_row - start_row

        output_file = Path(str(output_pattern).format(file_index))

        print(f"Writing segment {file_index}: {rows_in_segment:,} rows to {output_file.name}...")

        # Slice the table for this segment
        segment_table = table.slice(start_row, rows_in_segment)

        # Write to Parquet file with same compression as input
        pq.write_table(
            segment_table,
            output_file,
            compression='snappy'
        )

        start_row = end_row
        file_index += 1

        # Print progress
        progress = (end_row / total_rows) * 100
        print(f"Progress: {end_row:,}/{total_rows:,} rows ({progress:.1f}%)")

    print(f"\nSuccessfully segmented {total_rows:,} rows into {file_index} file(s)")

    # Print output file sizes
    total_output_size = 0
    for i in range(file_index):
        output_file = Path(str(output_pattern).format(i))
        file_size_mb = output_file.stat().st_size / (1024 * 1024)
        total_output_size += file_size_mb
        print(f"  {output_file.name}: {file_size_mb:.2f} MB")

    input_size_mb = input_file.stat().st_size / (1024 * 1024)
    print(f"\nInput size: {input_size_mb:.2f} MB")
    print(f"Total output size: {total_output_size:.2f} MB")
    print(f"Size ratio: {total_output_size/input_size_mb:.2f}x")


def main():
    parser = argparse.ArgumentParser(
        description='Segment timestamp predictions Parquet file into smaller files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Segment a file with max 1 million rows per file
  python segment_timestamp_predictions_parquet.py predictions.parquet 1000000

  # Segment with specific output directory
  python segment_timestamp_predictions_parquet.py predictions.parquet 500000 -o output_dir/

  # Segment with smaller files (100k rows each)
  python segment_timestamp_predictions_parquet.py predictions.parquet 100000
"""
    )

    parser.add_argument(
        'input_file',
        type=str,
        help='Input Parquet file to segment'
    )

    parser.add_argument(
        'max_rows_per_file',
        type=int,
        help='Maximum number of rows per output file'
    )

    parser.add_argument(
        '-o', '--output-dir',
        type=str,
        default=None,
        help='Output directory for segmented files (default: same directory as input file)'
    )

    args = parser.parse_args()

    try:
        segment_parquet_file(args.input_file, args.max_rows_per_file, args.output_dir)
    except Exception as e:
        print(f"Failed to segment file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
