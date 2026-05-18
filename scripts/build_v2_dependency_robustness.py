"""Refresh dependency robustness tables from saved news panel + return table."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_public_news_confound_master_layer as ncm  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

PANEL_PATH = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"
RETURN_TABLE_PATH = utils.OUT_DIR / "news_confound_master" / "news_clean_status_return_table.csv"


def main() -> int:
    if not PANEL_PATH.exists() or not RETURN_TABLE_PATH.exists():
        print("Requires news_confound_event_panel.csv and news_clean_status_return_table.csv.")
        return 1
    panel = pd.read_csv(PANEL_PATH)
    return_table = pd.read_csv(RETURN_TABLE_PATH)
    ncm.write_dependency_outputs(panel, return_table)
    print("Wrote statistical_robustness outputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
