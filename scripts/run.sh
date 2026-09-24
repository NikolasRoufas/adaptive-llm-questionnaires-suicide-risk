#!/usr/bin/env bash
# Run the full adaptive-questionnaire pipeline in order.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 main.py -o task0
python3 main.py -o task1_preparation
python3 main.py -o task1
python3 main.py -o task1_analyze_results
python3 main.py -o task1_visualize_results
