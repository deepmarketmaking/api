#!/bin/bash
#
# Convert timestamp prediction JSONL files to Parquet format
#
# This script processes files sequentially.
#
# Usage:
#   ./load_timestamp_predictions_jsonl.sh <input_directory> <output_directory>
#
# Arguments:
#   input_directory: Directory containing .jsonl files to convert
#   output_directory: Directory where .parquet files will be saved
#
# Example:
#   ./load_timestamp_predictions_jsonl.sh /data/inferences/input /data/inferences/output
#

set -e  # Exit on error

# Check arguments
if [ $# -lt 2 ]; then
    echo "Error: Missing required arguments"
    echo ""
    echo "Usage: $0 <input_directory> <output_directory>"
    echo ""
    echo "Arguments:"
    echo "  input_directory:  Directory containing .jsonl files to convert"
    echo "  output_directory: Directory where .parquet files will be saved"
    echo ""
    echo "Example:"
    echo "  $0 /data/inferences/input /data/inferences/output"
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_DIR="$2"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONVERTER_SCRIPT="$SCRIPT_DIR/load_timestamp_predictions_jsonl.py"

# Validate input directory
if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Input directory does not exist: $INPUT_DIR"
    exit 1
fi

# Validate converter script exists
if [ ! -f "$CONVERTER_SCRIPT" ]; then
    echo "Error: Converter script not found: $CONVERTER_SCRIPT"
    exit 1
fi

# Create output directory if it doesn't exist
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "Creating output directory: $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"
fi

# Count total files to process
TOTAL_FILES=$(find "$INPUT_DIR" -maxdepth 1 -name "*.jsonl" -o -name "*.jsonl.gz" | wc -l)

if [ "$TOTAL_FILES" -eq 0 ]; then
    echo "Error: No .jsonl or .jsonl.gz files found in $INPUT_DIR"
    exit 1
fi

echo "=========================================="
echo "Timestamp Predictions JSONL to Parquet Converter"
echo "=========================================="
echo "Input directory:  $INPUT_DIR"
echo "Output directory: $OUTPUT_DIR"
echo "Total files:      $TOTAL_FILES"
echo "=========================================="
echo ""

# Start processing
START_TIME=$(date +%s)

# Counter for tracking progress
FILE_NUM=0
FAILED_FILES=0

# Process each file sequentially
while IFS= read -r input_file; do
    FILE_NUM=$((FILE_NUM + 1))

    # Get the base filename without path
    basename="$(basename "$input_file")"

    # Replace .jsonl or .jsonl.gz extension with .parquet
    if [[ "$basename" == *.jsonl.gz ]]; then
        output_file="$OUTPUT_DIR/${basename%.jsonl.gz}.parquet"
    else
        output_file="$OUTPUT_DIR/${basename%.jsonl}.parquet"
    fi

    echo "=========================================="
    echo "File $FILE_NUM/$TOTAL_FILES: $basename"
    echo "=========================================="

    # Execute conversion
    if python "$CONVERTER_SCRIPT" "$input_file" --output "$output_file" --return-type arrow; then
        echo "✓ Success: $(basename "$output_file")"
        echo ""
    else
        echo "✗ Failed: $basename" >&2
        FAILED_FILES=$((FAILED_FILES + 1))
        echo ""
    fi

done < <(find "$INPUT_DIR" -maxdepth 1 \( -name "*.jsonl" -o -name "*.jsonl.gz" \) | sort)

# Calculate elapsed time
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))

echo ""
echo "=========================================="
echo "Conversion complete!"
echo "Total time: ${MINUTES}m ${SECONDS}s"
echo "Output directory: $OUTPUT_DIR"
echo "=========================================="

# Count successful conversions
PARQUET_COUNT=$(find "$OUTPUT_DIR" -maxdepth 1 -name "*.parquet" | wc -l)
echo "Parquet files created: $PARQUET_COUNT / $TOTAL_FILES"

if [ "$FAILED_FILES" -gt 0 ]; then
    echo ""
    echo "Warning: $FAILED_FILES file(s) failed to convert"
    exit 1
fi
