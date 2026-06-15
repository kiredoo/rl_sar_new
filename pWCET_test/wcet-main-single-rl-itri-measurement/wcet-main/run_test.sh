#!/bin/bash
set -x
set -e
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
for py in *_test.py; do
  "$PYTHON_BIN" "$py"
done
