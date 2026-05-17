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
    "build_v2_yfinance_analyst_diagnostic_layer.py",
    "build_v2_analyst_relay_layer.py",
    "build_v2_market_sentiment_regime_layer.py",
    "build_v2_transcript_narrative_relay_layer.py",
    "build_v2_information_originality_taxonomy.py",
    "build_v2_incremental_predictive_value.py",
]


def main() -> int:
    import os

    steps = list(STEPS)
    force = os.environ.get("FIN496_FORCE_ANALYST_RELAY", "").lower() in ("1", "true")
    if ANALYST_PANEL.exists() and not force:
        print("Skipping analyst relay fetch (existing panel). Set FIN496_FORCE_ANALYST_RELAY=1 to rebuild providers.")
        steps = [s for s in steps if s != "build_v2_analyst_relay_layer.py"]
        if "build_v2_yfinance_analyst_diagnostic_layer.py" in steps:
            steps = ["build_v2_yfinance_analyst_diagnostic_layer.py", "build_v2_analyst_relay_layer.py"] + [
                s for s in steps if s not in ("build_v2_yfinance_analyst_diagnostic_layer.py", "build_v2_analyst_relay_layer.py")
            ]
            os.environ.setdefault("FIN496_SKIP_PROVIDER_FETCH", "1")

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
