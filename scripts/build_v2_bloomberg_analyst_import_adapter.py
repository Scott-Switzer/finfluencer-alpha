"""Optional Bloomberg analyst export adapter (SKIPPED if private files absent)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import information_environment_utils as ie  # noqa: E402
import research_frontier_utils as rf  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

PRIVATE = REPO_ROOT / "data" / "private" / "bloomberg"
OUT = ie.info_dir("bloomberg_analyst_validation")
INPUTS = [
    PRIVATE / "analyst_recommendations_export.csv",
    PRIVATE / "price_target_history_export.csv",
    PRIVATE / "earnings_estimate_revisions_export.csv",
]


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    colmap = {c.lower().strip(): c for c in df.columns}
    out = df.copy()
    aliases = {
        "ticker": ["ticker", "symbol"],
        "event_date": ["date", "action_datetime", "as_of_date", "period"],
        "recommendation": ["recommendation", "action_type", "rating", "consensus_rating"],
        "target_price": ["target_price", "price_target", "pt"],
    }
    for canon, opts in aliases.items():
        for o in opts:
            if o in colmap:
                out[canon] = out[colmap[o]]
                break
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    existing = [p for p in INPUTS if p.exists()]
    if not existing:
        schema = """
Expected optional files under `data/private/bloomberg/`:
- `analyst_recommendations_export.csv` — columns: ticker, date, recommendation, broker, target_price
- `price_target_history_export.csv` — columns: ticker, date, target_price, consensus_rating
- `earnings_estimate_revisions_export.csv` — columns: ticker, date, revision_type, eps_estimate

Future command:
```bash
.venv/bin/python3 scripts/build_v2_bloomberg_analyst_import_adapter.py
```
"""
        utils.write_md(
            OUT / "bloomberg_analyst_validation_summary.md",
            "Bloomberg Analyst Validation",
            "# SKIPPED\n\nNo Bloomberg private exports found.\n" + schema,
        )
        print("Bloomberg adapter SKIPPED (no private files)")
        return 0

    events = rf.build_event_feature_table()
    rows: list[dict[str, Any]] = []
    for path in existing:
        df = normalize_columns(pd.read_csv(path))
        if "ticker" not in df.columns or "event_date" not in df.columns:
            continue
        for _, ev in events.iterrows():
            ticker = str(ev["ticker"]).upper()
            ed = ie.parse_iso_date(ev["event_date"])
            if ed is None:
                continue
            sub = df[df["ticker"].astype(str).str.upper() == ticker].copy()
            sub["d"] = pd.to_datetime(sub["event_date"], errors="coerce").dt.date
            pre = sub[sub["d"] <= ed].sort_values("d")
            if pre.empty:
                continue
            latest = pre.iloc[-1]
            rows.append(
                {
                    "event_id": ev["event_id"],
                    "ticker": ticker,
                    "event_date": ed.isoformat(),
                    "bloomberg_source_file": path.name,
                    "bloomberg_recommendation": str(latest.get("recommendation", ""))[:80],
                    "bloomberg_target_price": latest.get("target_price"),
                    "bloomberg_event_time_usable": True,
                }
            )

    panel = pd.DataFrame(rows)
    panel.to_csv(OUT / "bloomberg_analyst_event_panel.csv", index=False)
    summary = f"""# Bloomberg analyst validation

- Input files: {len(existing)}
- Event matches with pre-event Bloomberg rows: **{len(panel)}**

Bloomberg exports are **authoritative validation** when present; they do not replace FMP/Finnhub in the public repo pipeline until manually imported.
"""
    utils.write_md(OUT / "bloomberg_analyst_validation_summary.md", "Bloomberg Validation", summary)
    print("Bloomberg adapter complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
