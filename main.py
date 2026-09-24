#!/usr/bin/env python3
"""CLI entry point for the adaptive questionnaire pipeline.

Usage:
    python main.py -o task0
    python -m adaptive_questionnaires -o task1
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from adaptive_questionnaires.pipeline import main

if __name__ == "__main__":
    main()
