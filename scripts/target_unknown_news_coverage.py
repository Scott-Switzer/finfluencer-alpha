"""Targeted budgeted fetches for unknown_news_coverage events only."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT = utils.OUT_DIR / "news_confound_master" / "query_plan"
PANEL = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"
DERIVED = utils.OUT_DIR / "news_confound_master" / "fnspid" / "fnspid_derived_event_panel.csv"
TARGET_PLAN = OUT / "targeted_unknown_query_plan.csv"
SUMMARY = OUT / "targeted_unknown_summary.md"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--max-total-calls", type=int, default=100)
    p.add_argument("--no-network", action="store_true")
    return p.parse_args()


def priority_unknown(manifest: pd.DataFrame, panel: pd.DataFrame, top5: set[str]) -> pd.DataFrame:
    col = "news_clean_status_final" if "news_clean_status_final" in panel.columns else "news_clean_status"
    unk = panel[panel[col].astype(str).eq("unknown_news_coverage")].copy()
    m = manifest.merge(unk[["event_id"]], on="event_id", how="inner")
    m["event_date_dt"] = pd.to_datetime(m["event_date"], errors="coerce")
    m["year"] = m["event_date_dt"].dt.year

    fnspid_hit = pd.Series(False, index=m.index)
    if DERIVED.exists():
        fd = pd.read_csv(DERIVED, usecols=["event_id", "fnspid_news_hit"])
        hit = fd["fnspid_news_hit"].astype(str).str.lower().isin({"true", "1"})
        fnspid_map = dict(zip(fd["event_id"].astype(int), hit, strict=False))
        fnspid_hit = m["event_id"].map(lambda x: bool(fnspid_map.get(int(x), False)))

    long = utils.forward_panel(["5D"])
    if not long.empty:
        m5 = long[long["horizon"].eq("5D") & long["status"].eq("computed")][["event_id", "spy_bhar"]]
        m = m.merge(m5, on="event_id", how="left")
    else:
        m["spy_bhar"] = 0.0

    m["top5"] = m["ticker"].astype(str).isin(top5)
    m["pre2024_fnspid_miss"] = (m["year"] < 2024) & (~fnspid_hit)
    m["abs_bhar"] = m["spy_bhar"].abs().fillna(0)

    def score(row: pd.Series) -> int:
        s = 0
        if row["pre2024_fnspid_miss"]:
            s += 0
        if row["top5"]:
            s += 10
        s += int(min(float(row["abs_bhar"]) * 50, 20))
        if row["year"] >= 2024:
            s += 5
        return s

    m["priority_score"] = m.apply(score, axis=1)
    return m.sort_values(["priority_score", "event_date", "event_id"], ascending=[False, True, True])


def build_plan(targets: pd.DataFrame, cap: int) -> pd.DataFrame:
    rows: list[dict] = []
    proceed_providers = [
        "marketaux",
        "massive_polygon",
        "finnhub",
        "fmp_stock_news",
        "alpha_vantage_news_sentiment",
    ]
    for _, row in targets.iterrows():
        if len(rows) >= cap:
            break
        week = pd.Timestamp(row["event_date_dt"]).strftime("%G-W%V")
        prov = proceed_providers[len(rows) % len(proceed_providers)]
        rows.append(
            {
                "provider": prov,
                "ticker": row["ticker"],
                "iso_year_week": week,
                "event_id_anchor": int(row["event_id"]),
                "priority_score": int(row["priority_score"]),
                "planned_calls": 1,
                "collapse": "targeted_unknown",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not PANEL.exists():
        print("Missing news_confound_event_panel.csv")
        return 1

    panel = pd.read_csv(PANEL)
    manifest = utils.event_manifest()
    targets = priority_unknown(manifest, panel, utils.TOP5)
    targets.to_csv(OUT / "targeted_unknown_events.csv", index=False)

    plan = build_plan(targets, args.max_total_calls)
    plan.to_csv(TARGET_PLAN, index=False)

    summary = f"""# Targeted unknown news coverage

Unknown events in panel: **{int(panel['news_clean_status_final'].eq('unknown_news_coverage').sum() if 'news_clean_status_final' in panel.columns else 0)}**
Prioritized target rows: **{len(targets)}**
Planned provider calls (cap {args.max_total_calls}): **{len(plan)}**

Priorities: pre-2024 FNSPID miss, top-5 unknowns, large |5D BHAR|, then recent years.
403/401/429 are provider-limited — not clean no-news.
"""
    SUMMARY.write_text(summary, encoding="utf-8")

    if args.dry_run:
        print(plan.groupby("provider").size().to_string() if not plan.empty else "empty plan")
        print(f"targets={len(targets)} plan_rows={len(plan)}")
        return 0

    if not args.execute:
        print("Use --dry-run or --execute")
        return 0

    fetch = SCRIPT_DIR / "fetch_budgeted_news_providers.py"
    cmd = [
        sys.executable,
        str(fetch),
        "--execute",
        "--resume",
        f"--max-total-calls={args.max_total_calls}",
        f"--plan-path={TARGET_PLAN}",
    ]
    if args.no_network:
        cmd.append("--no-network")
    return subprocess.call(cmd, cwd=str(REPO))


if __name__ == "__main__":
    raise SystemExit(main())
