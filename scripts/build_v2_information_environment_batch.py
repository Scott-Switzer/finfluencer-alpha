"""Run all information-environment build scripts in order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
ANALYST_PANEL = (
    REPO_ROOT
    / "data/exports/final_paper_package_v2_expanded/information_environment/analyst_relay/analyst_relay_event_panel.csv"
)
STEPS = [
    "build_v2_analyst_relay_layer.py",
    "build_v2_market_sentiment_regime_layer.py",
    "build_v2_transcript_narrative_relay_layer.py",
    "build_v2_information_originality_taxonomy.py",
    "build_v2_incremental_predictive_value.py",
]


def main() -> int:
    import os

    steps = list(STEPS)
    if ANALYST_PANEL.exists() and os.environ.get("FIN496_FORCE_ANALYST_RELAY", "").lower() not in ("1", "true"):
        print("Skipping analyst relay (existing panel). Set FIN496_FORCE_ANALYST_RELAY=1 to rebuild.")
        steps = [s for s in steps if s != "build_v2_analyst_relay_layer.py"]

    for step in steps:
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
