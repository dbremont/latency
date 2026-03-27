#!/bin/bash

# ============================================
# include.sh — recursively inline file includes
# ============================================
#
# Usage:
#   ./include.sh <input-file> > <output-file>
#
# Description:
#   Processes a text file and replaces lines of the form:
#       #include "filename"
#   with the contents of the referenced file.
#
#   Includes are resolved **relative to the directory of the file
#   containing the #include directive**. Nested includes are supported.
#
# Options:
#   -h, --help    Show this help message and exit
#
# Example:
#   ./include.sh main.md > full_spec.md
# ============================================

# Show help if requested or no arguments
if [[ $# -eq 0 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    grep '^#' "$0" | sed 's/^# //'
    exit 0
fi

input="$1"

if [[ ! -f "$input" ]]; then
    echo "Error: File not found: $input" >&2
    exit 1
fi

# Function to process a file recursively
process_file() {
    local file="$1"
    local dir
    dir=$(dirname "$file")  # Directory of the current file

    while IFS= read -r line; do
        if [[ $line =~ ^#include[[:space:]]+\"([^\"]+)\" ]]; then
            include_file="$dir/${BASH_REMATCH[1]}"  # Relative to current file
            if [[ -f "$include_file" ]]; then
                process_file "$include_file"  # Recursive include
            else
                echo "Warning: include file not found: $include_file" >&2
            fi
        else
            echo "$line"
        fi
    done < "$file"
}

# Start processing the input file
process_file "$input"