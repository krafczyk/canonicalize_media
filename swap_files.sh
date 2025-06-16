#!/bin/bash

set -e

# Swap two files. Must take two arguments

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <file1> <file2>"
  exit 1
fi

file1="$1"
file2="$2"

mv "$file1" "${file1}.tmp"
mv "$file2" "$file1"
mv "${file1}.tmp" "$file2"
