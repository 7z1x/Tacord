#!/usr/bin/env python3
"""Entry point untuk regersi lyric2ttml."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from regersi.main import run

if __name__ == "__main__":
    run()
