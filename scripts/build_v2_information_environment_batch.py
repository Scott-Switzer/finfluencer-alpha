"""Run all information-environment build scripts in order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STEPS = [
    "build_v2_analyst_relay_layer.py",
    "build_v2_market_sentiment_regime_layer.py",
    "build_v2_transcript_narrative_relay_layer.py",
    "build_v2_information_originality_taxonomy.py",
    "build_v2_incremental_predictive_value.py",
]


def main() -> int:
    for step in STEPS:
        path = SCRIPT_DIR / step
        print(f"Running {step}...")
        rc = subprocess.call([sys.executable, str(path)])
        if rc != 0:
            print(f"FAILED: {step} (exit {rc})")
            return rc
    print("Information environment batch complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
