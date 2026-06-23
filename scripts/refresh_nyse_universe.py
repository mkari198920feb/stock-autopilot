#!/usr/bin/env python3
"""Deprecated wrapper — use scripts/refresh_us_equities.py (NASDAQ + NYSE)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_us_equities import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
