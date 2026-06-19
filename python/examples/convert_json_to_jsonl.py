#!/usr/bin/env python3
"""
Convert pretty-printed JSON array files to JSONL format

This script converts JSON files containing arrays of inference results
into JSONL (JSON Lines) format, where each inference is written as a
single line of compact JSON.

The script processes files in a streaming fashion to avoid loading
large files entirely into memory.
"""

import json
import argparse
import sys
import time
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

# Try to import ijson for fast streaming, fall back to manual parsing
try:
    import ijson
    HAS_IJSON = True
except ImportError:
    HAS_IJSON = False

# Try to import ujson for faster JSON serialization
try:
    import ujson
    HAS_UJSON = True
except ImportError:
    HAS_UJSON = False

# Choose the fastest JSON dumps function available
if HAS_UJSON:
    json_dumps = ujson.dumps
else:
    json_dumps = lambda obj: json.dumps(obj, separators=(',', ':'))


def process_file_worker_parallel(args_tuple):
    """Worker function to process a single file in parallel mode (one worker per file)"""
    input_file, buffer_size = args_tuple
    try:
        import tempfile
        import os

        temp_fd, temp_path = tempfile.mkstemp(suffix='.jsonl')
        os.close(temp_fd)

        print(f"\n[Worker] Processing {input_file}...")
        input_path = Path(input_file)

        start_time = time.time()
        item_count = 0

        with open(input_path, 'rb', buffering=1024*1024) as infile, \
             open(temp_path, 'w', buffering=1024*1024) as outfile:
            write_buffer = []

            for item in ijson.items(infile, 'item'):
                write_buffer.append(json_dumps(item))
                item_count += 1

                if len(write_buffer) >= buffer_size:
                    outfile.write('\n'.join(write_buffer) + '\n')
                    write_buffer = []

                    # Progress update
                    if item_count % 50000 == 0:
                        elapsed = time.time() - start_time
                        items_per_sec = item_count / elapsed if elapsed > 0 else 0
                        print(f"[Worker] {input_file}: {item_count} items ({items_per_sec:.0f} items/sec)")

            # Write remaining
            if write_buffer:
                outfile.write('\n'.join(write_buffer) + '\n')

        elapsed = time.time() - start_time
        print(f"[Worker] Completed {input_file}: {item_count} items in {elapsed:.2f}s ({item_count/elapsed:.0f} items/sec)")
        return (temp_path, item_count, None)

    except Exception as e:
        print(f"[Worker] Failed to process {input_file}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return (None, 0, str(e))


def process_chunk_worker(args_tuple):
    """Worker function to process a chunk of items from a file"""
    input_file, start_idx, end_idx, buffer_size, worker_id = args_tuple
    try:
        import tempfile
        import os

        temp_fd, temp_path = tempfile.mkstemp(suffix='.jsonl')
        os.close(temp_fd)

        input_path = Path(input_file)
        start_time = time.time()
        item_count = 0
        current_idx = 0

        with open(input_path, 'rb', buffering=1024*1024) as infile, \
             open(temp_path, 'w', buffering=1024*1024) as outfile:
            write_buffer = []

            for item in ijson.items(infile, 'item'):
                # Skip items before our start index
                if current_idx < start_idx:
                    current_idx += 1
                    continue

                # Stop if we've reached our end index
                if current_idx >= end_idx:
                    break

                write_buffer.append(json_dumps(item))
                item_count += 1
                current_idx += 1

                if len(write_buffer) >= buffer_size:
                    outfile.write('\n'.join(write_buffer) + '\n')
                    write_buffer = []

            # Write remaining
            if write_buffer:
                outfile.write('\n'.join(write_buffer) + '\n')

        elapsed = time.time() - start_time
        if elapsed > 0:
            items_per_sec = item_count / elapsed
            print(f"[Worker {worker_id}] Completed chunk [{start_idx}:{end_idx}]: {item_count} items in {elapsed:.2f}s ({items_per_sec:.0f} items/sec)")
        return (temp_path, item_count, None, worker_id)

    except Exception as e:
        print(f"[Worker {worker_id}] Failed to process chunk [{start_idx}:{end_idx}]: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return (None, 0, str(e), worker_id)


def count_items_in_file(file_path: str) -> int:
    """Quickly count the number of items in a JSON array file"""
    count = 0
    try:
        with open(file_path, 'rb', buffering=1024*1024) as f:
            for _ in ijson.items(f, 'item'):
                count += 1
    except ijson.common.IncompleteJSONError as e:
        print(f"Warning: File {file_path} appears to be incomplete or corrupted: {e}", file=sys.stderr)
        print(f"Counted {count} valid items before error", file=sys.stderr)
        # Return the count we got before the error
    return count


def convert_json_to_jsonl(input_path: str, output_path: str = None, buffer_size: int = 100):
    """
    Convert a JSON array file to JSONL format using streaming approach

    Args:
        input_path: Path to input JSON file
        output_path: Path to output JSONL file (default: input_path with .jsonl extension)
        buffer_size: Number of items to buffer before writing (default: 100)
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Determine output path
    if output_path is None:
        output_file = input_file.with_suffix('.jsonl')
    else:
        output_file = Path(output_path)

    print(f"Converting {input_file} to {output_file}...")

    item_count = 0

    try:
        with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
            # Read and parse the JSON file
            # For very large files, we use a streaming JSON parser approach

            # First, try to load the entire file if it's reasonable
            # For extremely large files, this may need a more sophisticated streaming parser
            content = infile.read()

            # Parse the JSON array
            data = json.loads(content)

            if not isinstance(data, list):
                raise ValueError("Input file must contain a JSON array at the top level")

            print(f"Found {len(data)} items to convert...")

            # Write each item as a line of compact JSON
            buffer = []
            for item in data:
                buffer.append(json.dumps(item))
                item_count += 1

                # Write buffer when it reaches the buffer_size
                if len(buffer) >= buffer_size:
                    outfile.write('\n'.join(buffer) + '\n')
                    buffer = []

                    # Progress update
                    if item_count % 10000 == 0:
                        print(f"Processed {item_count} items...")

            # Write remaining items in buffer
            if buffer:
                outfile.write('\n'.join(buffer) + '\n')

        print(f"Successfully converted {item_count} items to {output_file}")

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON file: {e}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        raise


def convert_json_to_jsonl_streaming_fast(input_path: str, output_path: str = None, buffer_size: int = 10000):
    """
    Convert a JSON array file to JSONL format using ijson for fast streaming

    This version uses the ijson library for efficient streaming parsing.
    Much faster than the manual character-by-character parser.

    Args:
        input_path: Path to input JSON file
        output_path: Path to output JSONL file (default: input_path with .jsonl extension)
        buffer_size: Number of items to buffer before writing (default: 10000)
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Determine output path
    if output_path is None:
        output_file = input_file.with_suffix('.jsonl')
    else:
        output_file = Path(output_path)

    print(f"Converting {input_file} to {output_file} (fast streaming mode with ijson)...")

    item_count = 0

    try:
        # Use larger buffer for file I/O
        with open(input_file, 'rb', buffering=1024*1024) as infile, \
             open(output_file, 'wb', buffering=1024*1024) as outfile:
            # Use ijson to iterate through array items
            # The 'item' prefix means we want each item in the top-level array
            write_buffer = []

            # Pre-allocate newline byte
            newline = b'\n'

            for item in ijson.items(infile, 'item'):
                # Use the fastest JSON serializer available
                write_buffer.append(json_dumps(item))
                item_count += 1

                # Write buffer when it reaches the buffer_size
                if len(write_buffer) >= buffer_size:
                    # Join once and encode once for efficiency
                    outfile.write('\n'.join(write_buffer).encode('utf-8'))
                    outfile.write(newline)
                    write_buffer = []

                    # Progress update
                    if item_count % 50000 == 0:
                        print(f"Processed {item_count} items...")

            # Write remaining items in buffer
            if write_buffer:
                outfile.write('\n'.join(write_buffer).encode('utf-8'))
                outfile.write(newline)

        print(f"Successfully converted {item_count} items to {output_file}")

    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        raise


def convert_json_to_jsonl_streaming(input_path: str, output_path: str = None):
    """
    Convert a JSON array file to JSONL format using a more memory-efficient streaming approach

    This version uses a simple state machine to parse JSON objects one at a time
    without loading the entire array into memory. This is more complex but handles
    very large files better.

    Args:
        input_path: Path to input JSON file
        output_path: Path to output JSONL file (default: input_path with .jsonl extension)
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Determine output path
    if output_path is None:
        output_file = input_file.with_suffix('.jsonl')
    else:
        output_file = Path(output_path)

    print(f"Converting {input_file} to {output_file} (streaming mode)...")

    item_count = 0

    try:
        with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
            # Read the file and extract individual JSON objects
            # This approach reads the file and identifies complete JSON objects

            buffer = ""
            brace_count = 0
            in_string = False
            escape_next = False
            in_array = False
            object_start = -1

            while True:
                chunk = infile.read(8192)  # Read in 8KB chunks
                if not chunk:
                    break

                for i, char in enumerate(chunk):
                    buffer += char

                    # Handle string escaping
                    if escape_next:
                        escape_next = False
                        continue

                    if char == '\\':
                        escape_next = True
                        continue

                    # Track string state
                    if char == '"':
                        in_string = not in_string
                        continue

                    # Only process structural characters outside of strings
                    if in_string:
                        continue

                    # Track array start
                    if char == '[' and brace_count == 0:
                        in_array = True
                        buffer = ""  # Reset buffer after array start
                        continue

                    # Track object boundaries
                    if char == '{':
                        if brace_count == 0:
                            object_start = len(buffer) - 1
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1

                        # Complete object found
                        if brace_count == 0 and object_start >= 0:
                            # Extract the complete object
                            obj_str = buffer[object_start:]

                            # Parse and write as compact JSON
                            try:
                                obj = json.loads(obj_str)
                                outfile.write(json.dumps(obj) + '\n')
                                item_count += 1

                                if item_count % 10000 == 0:
                                    print(f"Processed {item_count} items...")
                            except json.JSONDecodeError:
                                # If we can't parse it, continue accumulating
                                pass

                            # Reset buffer, keeping any text after the object
                            buffer = ""
                            object_start = -1

        print(f"Successfully converted {item_count} items to {output_file}")

    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(
        description='Convert pretty-printed JSON array files to JSONL format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert a single file (output will be input.jsonl)
  python convert_json_to_jsonl.py /path/to/input.json

  # Convert with specific output path
  python convert_json_to_jsonl.py /path/to/input.json -o /path/to/output.jsonl

  # Use streaming mode for very large files
  python convert_json_to_jsonl.py /path/to/input.json --streaming

  # Convert multiple files (each gets its own .jsonl output)
  python convert_json_to_jsonl.py file1.json file2.json file3.json

  # Merge multiple files into a single JSONL output
  python convert_json_to_jsonl.py file1.json file2.json --merge -o merged_output.jsonl

  # Merge two large files with streaming mode (memory-efficient)
  python convert_json_to_jsonl.py \\
    /data/nathan/inferences/september_sample/timestamp_predictions_20250902_20250924_396.json \\
    /data/nathan/inferences/september_sample/timestamp_predictions_20250902_20250924_396.json \\
    --merge --streaming -o combined_predictions.jsonl
"""
    )

    parser.add_argument(
        'input_files',
        nargs='+',
        help='Input JSON file(s) to convert'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='Output JSONL file path. For single file: defaults to input.jsonl. For multiple files: required if --merge is used'
    )

    parser.add_argument(
        '--streaming',
        action='store_true',
        help='Use streaming mode for very large files (more memory efficient)'
    )

    parser.add_argument(
        '--buffer-size',
        type=int,
        default=10000,
        help='Number of items to buffer before writing (default: 10000). Larger values = fewer I/O operations but more memory. Try 50000-100000 if you have plenty of RAM.'
    )

    parser.add_argument(
        '--merge',
        action='store_true',
        help='Merge multiple input files into a single output file (requires --output)'
    )

    parser.add_argument(
        '--parallel',
        type=int,
        default=1,
        help='Number of parallel workers for processing (default: 1). Use 0 for auto-detect CPU count.'
    )

    parser.add_argument(
        '--workers-per-file',
        type=int,
        default=1,
        help='Number of workers to use per file (default: 1). Values >1 will chunk each file for parallel processing. Only works with --merge and --streaming modes.'
    )

    args = parser.parse_args()

    # Auto-detect CPU count if parallel=0
    if args.parallel == 0:
        args.parallel = multiprocessing.cpu_count()
        print(f"Auto-detected {args.parallel} CPU cores")

    # Check if performance libraries are available
    if args.streaming and not HAS_IJSON:
        print("Warning: ijson library not found. Streaming mode will use slower fallback parser.", file=sys.stderr)
        print("For better performance, install ijson: pip install ijson", file=sys.stderr)
        print()

    if not HAS_UJSON:
        print("Tip: Install ujson for 2-5x faster JSON serialization: pip install ujson", file=sys.stderr)
        print()

    # Validate arguments
    if args.merge and not args.output:
        print("Error: --merge requires --output to specify the merged output file", file=sys.stderr)
        sys.exit(1)

    if args.merge and len(args.input_files) < 2:
        print("Warning: --merge specified but only one input file provided", file=sys.stderr)

    # Process files based on merge flag
    success_count = 0
    error_count = 0

    if args.merge:
        # Merge mode: all files go to one output
        print(f"Merging {len(args.input_files)} files into {args.output}...")

        if args.streaming:
            print("Using streaming mode for merge...")

        if args.parallel > 1 and HAS_IJSON:
            import tempfile
            import shutil

            if args.workers_per_file > 1:
                # Chunked parallel processing: split each file into chunks
                print(f"Using {args.workers_per_file} workers per file (chunked processing)...")

                # First, count items in each file to determine chunk sizes
                print("Counting items in files for chunking...")
                file_item_counts = {}
                has_incomplete = False
                for input_file in args.input_files:
                    print(f"  Counting {input_file}...")
                    count = count_items_in_file(input_file)
                    if count == 0:
                        print(f"  ERROR: Could not count items in {input_file}. File may be corrupted.", file=sys.stderr)
                        has_incomplete = True
                    file_item_counts[input_file] = count
                    print(f"  Found {count} items in {input_file}")

                if has_incomplete:
                    print("\nWARNING: Some files could not be counted. Falling back to non-chunked parallel processing.", file=sys.stderr)
                    # Fall back to file-level parallelism
                    worker_args = [(f, args.buffer_size) for f in args.input_files]
                    with ProcessPoolExecutor(max_workers=args.parallel) as executor:
                        results = list(executor.map(process_file_worker_parallel, worker_args))

                    # Concatenate temporary files
                    print(f"\nConcatenating {len(results)} temporary files...")
                    with open(args.output, 'w', buffering=1024*1024) as outfile:
                        for temp_path, item_count, error in results:
                            if error:
                                error_count += 1
                                continue
                            if temp_path:
                                with open(temp_path, 'r', buffering=1024*1024) as infile:
                                    shutil.copyfileobj(infile, outfile, length=1024*1024)
                                # Clean up temp file
                                Path(temp_path).unlink()
                                success_count += 1

                    print(f"\nSuccessfully merged {success_count} files into {args.output}")
                    return

                # Create worker args for all chunks
                worker_args = []
                worker_id = 0
                for input_file in args.input_files:
                    total_items = file_item_counts[input_file]
                    chunk_size = total_items // args.workers_per_file

                    for i in range(args.workers_per_file):
                        start_idx = i * chunk_size
                        # Last chunk gets any remainder
                        end_idx = total_items if i == args.workers_per_file - 1 else (i + 1) * chunk_size
                        worker_args.append((input_file, start_idx, end_idx, args.buffer_size, worker_id))
                        worker_id += 1

                print(f"\nProcessing {len(worker_args)} chunks across {len(args.input_files)} files...")

                # Process chunks in parallel
                with ProcessPoolExecutor(max_workers=args.parallel) as executor:
                    results = list(executor.map(process_chunk_worker, worker_args))

                # Sort results by worker_id to maintain order
                results.sort(key=lambda x: x[3] if len(x) > 3 else 0)

                # Concatenate temporary files
                print(f"\nConcatenating {len(results)} chunk files...")
                with open(args.output, 'w', buffering=1024*1024) as outfile:
                    for temp_path, item_count, error, wid in results:
                        if error:
                            error_count += 1
                            continue
                        if temp_path:
                            with open(temp_path, 'r', buffering=1024*1024) as infile:
                                shutil.copyfileobj(infile, outfile, length=1024*1024)
                            # Clean up temp file
                            Path(temp_path).unlink()

                success_count = len(args.input_files)
                print(f"\nSuccessfully merged {success_count} files into {args.output}")

            else:
                # File-level parallel processing: one worker per file
                print(f"Using {args.parallel} parallel workers for conversion (one worker per file)...")

                # Process files in parallel using module-level worker function
                worker_args = [(f, args.buffer_size) for f in args.input_files]
                with ProcessPoolExecutor(max_workers=args.parallel) as executor:
                    results = list(executor.map(process_file_worker_parallel, worker_args))

                # Concatenate temporary files
                print(f"\nConcatenating {len(results)} temporary files...")
                with open(args.output, 'w', buffering=1024*1024) as outfile:
                    for temp_path, item_count, error in results:
                        if error:
                            error_count += 1
                            continue
                        if temp_path:
                            with open(temp_path, 'r', buffering=1024*1024) as infile:
                                shutil.copyfileobj(infile, outfile, length=1024*1024)
                            # Clean up temp file
                            Path(temp_path).unlink()
                            success_count += 1

                print(f"\nSuccessfully merged {success_count} files into {args.output}")

        else:
            # Serial processing mode
            # Open output file once
            try:
                with open(args.output, 'w') as outfile:
                    for input_file in args.input_files:
                        try:
                            print(f"\nProcessing {input_file}...")
                            input_path = Path(input_file)

                            if not input_path.exists():
                                raise FileNotFoundError(f"Input file not found: {input_file}")

                            if args.streaming:
                                # Streaming mode: parse JSON objects one at a time
                                item_count = 0

                                if HAS_IJSON:
                                    # Fast path: use ijson
                                    start_time = time.time()
                                    parse_time = 0
                                    serialize_time = 0
                                    io_time = 0

                                    with open(input_path, 'rb') as infile:
                                        write_buffer = []

                                        for item in ijson.items(infile, 'item'):
                                            # Measure JSON serialization time
                                            t0 = time.time()
                                            write_buffer.append(json_dumps(item))
                                            serialize_time += time.time() - t0
                                            item_count += 1

                                            if len(write_buffer) >= args.buffer_size:
                                                # Measure I/O time
                                                t0 = time.time()
                                                outfile.write('\n'.join(write_buffer) + '\n')
                                                io_time += time.time() - t0
                                                write_buffer = []

                                                if item_count % 50000 == 0:
                                                    elapsed = time.time() - start_time
                                                    items_per_sec = item_count / elapsed if elapsed > 0 else 0
                                                    parse_pct = (elapsed - serialize_time - io_time) / elapsed * 100 if elapsed > 0 else 0
                                                    serialize_pct = serialize_time / elapsed * 100 if elapsed > 0 else 0
                                                    io_pct = io_time / elapsed * 100 if elapsed > 0 else 0
                                                    print(f"  Processed {item_count} items from {input_file} ({items_per_sec:.0f} items/sec)")
                                                    print(f"    Time breakdown - Parse: {parse_pct:.1f}%, Serialize: {serialize_pct:.1f}%, I/O: {io_pct:.1f}%")

                                        # Write remaining buffer
                                        if write_buffer:
                                            t0 = time.time()
                                            outfile.write('\n'.join(write_buffer) + '\n')
                                            io_time += time.time() - t0

                                    # Final statistics
                                    total_time = time.time() - start_time
                                    if total_time > 0:
                                        items_per_sec = item_count / total_time
                                        parse_time = total_time - serialize_time - io_time
                                        print(f"  File statistics:")
                                        print(f"    Total time: {total_time:.2f}s ({items_per_sec:.0f} items/sec)")
                                        print(f"    Parse time: {parse_time:.2f}s ({parse_time/total_time*100:.1f}%)")
                                        print(f"    Serialize time: {serialize_time:.2f}s ({serialize_time/total_time*100:.1f}%)")
                                        print(f"    I/O time: {io_time:.2f}s ({io_time/total_time*100:.1f}%)")

                                else:
                                    # Fallback: manual character-by-character parsing
                                    with open(input_path, 'r') as infile:
                                        buffer = ""
                                        brace_count = 0
                                        in_string = False
                                        escape_next = False
                                        object_start = -1
                                        write_buffer = []

                                        while True:
                                            chunk = infile.read(8192)  # Read in 8KB chunks
                                            if not chunk:
                                                break

                                            for char in chunk:
                                                buffer += char

                                                # Handle string escaping
                                                if escape_next:
                                                    escape_next = False
                                                    continue

                                                if char == '\\':
                                                    escape_next = True
                                                    continue

                                                # Track string state
                                                if char == '"':
                                                    in_string = not in_string
                                                    continue

                                                # Only process structural characters outside of strings
                                                if in_string:
                                                    continue

                                                # Track array start
                                                if char == '[' and brace_count == 0:
                                                    buffer = ""  # Reset buffer after array start
                                                    continue

                                                # Track object boundaries
                                                if char == '{':
                                                    if brace_count == 0:
                                                        object_start = len(buffer) - 1
                                                    brace_count += 1
                                                elif char == '}':
                                                    brace_count -= 1

                                                    # Complete object found
                                                    if brace_count == 0 and object_start >= 0:
                                                        # Extract the complete object
                                                        obj_str = buffer[object_start:]

                                                        # Parse and write as compact JSON
                                                        try:
                                                            obj = json.loads(obj_str)
                                                            write_buffer.append(json.dumps(obj))
                                                            item_count += 1

                                                            # Flush write buffer periodically
                                                            if len(write_buffer) >= args.buffer_size:
                                                                outfile.write('\n'.join(write_buffer) + '\n')
                                                                write_buffer = []

                                                            if item_count % 50000 == 0:
                                                                print(f"  Processed {item_count} items from {input_file}...")
                                                        except json.JSONDecodeError:
                                                            # If we can't parse it, continue accumulating
                                                            pass

                                                        # Reset buffer
                                                        buffer = ""
                                                        object_start = -1

                                        # Write remaining buffer
                                        if write_buffer:
                                            outfile.write('\n'.join(write_buffer) + '\n')

                                print(f"Completed {input_file}: {item_count} items")

                            else:
                                # Non-streaming mode: load entire file
                                with open(input_path, 'r') as infile:
                                    content = infile.read()
                                    data = json.loads(content)

                                    if not isinstance(data, list):
                                        raise ValueError("Input file must contain a JSON array at the top level")

                                    print(f"Found {len(data)} items in {input_file}...")

                                    # Write items as JSONL
                                    item_count = 0
                                    buffer = []
                                    for item in data:
                                        buffer.append(json.dumps(item))
                                        item_count += 1

                                        if len(buffer) >= args.buffer_size:
                                            outfile.write('\n'.join(buffer) + '\n')
                                            buffer = []

                                            if item_count % 50000 == 0:
                                                print(f"  Processed {item_count} items from {input_file}...")

                                    # Write remaining buffer
                                    if buffer:
                                        outfile.write('\n'.join(buffer) + '\n')

                                    print(f"Completed {input_file}: {item_count} items")

                            success_count += 1

                        except Exception as e:
                            print(f"Failed to process {input_file}: {e}", file=sys.stderr)
                            error_count += 1
                            continue

                print(f"\nSuccessfully merged {success_count} files into {args.output}")

            except Exception as e:
                print(f"Error creating output file: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        # Individual mode: each file gets its own output
        for input_file in args.input_files:
            try:
                if args.streaming:
                    if HAS_IJSON:
                        convert_json_to_jsonl_streaming_fast(input_file, args.output, args.buffer_size)
                    else:
                        convert_json_to_jsonl_streaming(input_file, args.output)
                else:
                    convert_json_to_jsonl(input_file, args.output, args.buffer_size)
                success_count += 1
            except Exception as e:
                print(f"Failed to convert {input_file}: {e}", file=sys.stderr)
                error_count += 1

    # Summary
    print(f"\nConversion complete:")
    print(f"  Success: {success_count}")
    print(f"  Failed: {error_count}")

    if error_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
