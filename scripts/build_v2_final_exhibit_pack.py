"""Regenerate final exhibits from latest exports (after master pipeline run)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_public_news_confound_master_layer as ncm  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "news_confound_master"
BY_PROVIDER = OUT / "news_confound_by_provider.csv"
RETURN_TABLE = OUT / "news_clean_status_return_table.csv"
PANEL = OUT / "news_confound_event_panel.csv"


def main() -> int:
    if not PANEL.exists() or not RETURN_TABLE.exists():
        print("Run build_v2_public_news_confound_master_layer.py first.")
        return 1
    panel = pd.read_csv(PANEL)
    return_table = pd.read_csv(RETURN_TABLE)
    by_provider = pd.read_csv(BY_PROVIDER) if BY_PROVIDER.exists() else pd.DataFrame()
    ncm.write_final_exhibits(panel, return_table, by_provider)
    print("Final exhibit pack updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
