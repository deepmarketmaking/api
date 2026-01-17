#!/usr/bin/env python3
"""
Benchmark script to test if parallel processing is actually faster.

This will test different numbers of workers to find the optimal setting.
"""

import time
import os
import sys
import tempfile
import gzip

# Add the script directory to path to import our module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from load_timestamp_predictions_jsonl import (
    convert_jsonl_to_parquet_parallel,
    load_timestamp_predictions_fast
)


def create_test_file(num_lines, output_path):
    """Create a test JSONL file with the given number of lines."""
    print(f"Creating test file with {num_lines:,} lines...")

    # Sample JSONL line
    sample_line = '{"ats_indicator": "N", "date": "2025-10-29T12:00:00.000Z", "figi": "BBG01WHX0YJ2", "quantity": 1000000, "side": "bid", "price": [100.77, 100.81, 100.84, 100.85, 100.87, 100.88, 100.89, 100.90, 100.91, 100.92, 100.93, 100.95, 100.96, 100.97, 100.98, 101.00, 101.02, 101.04, 101.09]}\n'

    with open(output_path, 'w') as f:
        for i in range(num_lines):
            f.write(sample_line)

    file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
    print(f"Created test file: {file_size:.1f} MB")


def benchmark_single_threaded(input_file, output_file, chunk_size):
    """Benchmark single-threaded processing (1 worker)."""
    print("\n" + "="*60)
    print("Testing SINGLE-THREADED (1 worker)")
    print("="*60)

    start = time.time()
    convert_jsonl_to_parquet_parallel(
        input_file,
        output_file,
        chunk_size=chunk_size,
        num_workers=1
    )
    elapsed = time.time() - start

    print(f"\n⏱️  Time: {elapsed:.2f} seconds")
    return elapsed


def benchmark_multi_threaded(input_file, output_file, chunk_size, num_workers):
    """Benchmark multi-threaded processing."""
    print("\n" + "="*60)
    print(f"Testing MULTI-THREADED ({num_workers} workers)")
    print("="*60)

    start = time.time()
    convert_jsonl_to_parquet_parallel(
        input_file,
        output_file,
        chunk_size=chunk_size,
        num_workers=num_workers
    )
    elapsed = time.time() - start

    print(f"\n⏱️  Time: {elapsed:.2f} seconds")
    return elapsed


def benchmark_no_chunking(input_file, output_file):
    """Benchmark loading entire file at once (no parallelization)."""
    print("\n" + "="*60)
    print("Testing NO CHUNKING (load entire file)")
    print("="*60)

    start = time.time()
    table = load_timestamp_predictions_fast(input_file, return_type='arrow')

    # Also write to parquet for fair comparison
    import pyarrow.parquet as pq
    pq.write_table(table, output_file)

    elapsed = time.time() - start

    print(f"\n⏱️  Time: {elapsed:.2f} seconds")
    return elapsed


def main():
    # Configuration
    NUM_LINES = 500000  # Half a million lines for testing
    CHUNK_SIZE = 50000
    WORKERS_TO_TEST = [1, 2, 4, 8]

    with tempfile.TemporaryDirectory() as tmpdir:
        test_input = os.path.join(tmpdir, 'test.jsonl')

        # Create test file
        create_test_file(NUM_LINES, test_input)

        results = {}

        # Test no chunking (baseline)
        test_output = os.path.join(tmpdir, 'test_no_chunk.parquet')
        try:
            results['no_chunking'] = benchmark_no_chunking(test_input, test_output)
            os.remove(test_output)
        except Exception as e:
            print(f"No chunking failed: {e}")
            results['no_chunking'] = None

        # Test different worker counts
        for num_workers in WORKERS_TO_TEST:
            test_output = os.path.join(tmpdir, f'test_{num_workers}w.parquet')
            results[f'{num_workers}_workers'] = benchmark_multi_threaded(
                test_input, test_output, CHUNK_SIZE, num_workers
            )
            os.remove(test_output)

        # Print summary
        print("\n" + "="*60)
        print("BENCHMARK RESULTS SUMMARY")
        print("="*60)
        print(f"\nTest file: {NUM_LINES:,} lines")
        print(f"Chunk size: {CHUNK_SIZE:,} lines\n")

        # Sort by time
        sorted_results = sorted(
            [(k, v) for k, v in results.items() if v is not None],
            key=lambda x: x[1]
        )

        print(f"{'Configuration':<20} {'Time (s)':<12} {'Speedup':>10}")
        print("-" * 60)

        baseline = sorted_results[0][1] if sorted_results else 1.0

        for config, elapsed in sorted_results:
            speedup = baseline / elapsed
            speedup_str = f"{speedup:.2f}x" if speedup != 1.0 else "baseline"
            print(f"{config:<20} {elapsed:>8.2f}     {speedup_str:>10}")

        # Find optimal
        if sorted_results:
            best_config, best_time = sorted_results[0]
            print(f"\n🏆 Fastest: {best_config} ({best_time:.2f} seconds)")

            # Check if parallelization helps
            single_thread_time = results.get('1_workers')
            if single_thread_time and len(sorted_results) > 1:
                multi_thread_results = [
                    (k, v) for k, v in results.items()
                    if k != '1_workers' and k != 'no_chunking' and v is not None
                ]
                if multi_thread_results:
                    best_multi_thread = min(multi_thread_results, key=lambda x: x[1])[1]
                else:
                    best_multi_thread = None

                if best_multi_thread:
                    improvement = ((single_thread_time - best_multi_thread) / single_thread_time) * 100

                    if improvement > 10:
                        print(f"\n✅ Parallelization helps! {improvement:.1f}% faster than single-threaded")
                    elif improvement > 0:
                        print(f"\n⚠️  Parallelization provides minimal benefit: {improvement:.1f}% faster")
                    else:
                        print(f"\n❌ Parallelization is slower! Consider using single-threaded processing")


if __name__ == '__main__':
    main()
