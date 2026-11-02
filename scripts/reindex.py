#!/usr/bin/env python
"""Reindexação total (atalho para ingest.py --full)."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).with_name("ingest.py")
    sys.exit(subprocess.call([sys.executable, str(script), "--full"]))
