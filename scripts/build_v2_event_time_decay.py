from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402
import build_v2_long_horizon_returns as lh  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
DECAY_DIR = OUT_DIR / "decay"
FIG_DIR = OUT_DIR / "figures_data"
DECAY_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

INTERVALS = [
    ("0_5", 0, 5),
    ("6_20", 5, 20),
    ("21_63", 20, 63),
    ("64_126", 63, 126),
    ("127_252", 126, 252),
    ("253_504", 252, 504),
    ("505_end_of_sample", 504, None),
]
PATH_OFFSETS = range(-252, 505)


def write_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    base.write_md(
        path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(rows[:120], columns)
    )


def masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "all": df.index == df.index,
        "top5": df["top5_flag"].eq("True"),
        "non_top": df["top5_flag"].eq("False"),
        "buy": df["recommendation_type"].eq("buy"),
        "sell": df["recommendation_type"].eq("sell"),
        "low_lookahead": df["low_lookahead_flag"].eq("True"),
        "duplicate_collapsed": df["duplicate_collapsed_flag"].eq("True"),
        "SEC_clean": df["sec_clean_flag"].eq("True"),
        "high_quality": pd.to_numeric(df["actionability_score"], errors="coerce").fillna(0) >= 3.0,
    }


def t_summary(values: pd.Series) -> dict[str, str | int]:
    stats = base.t_test([float(v) for v in values.dropna()])
    return {
        "n": stats["n"],
        "mean_ar": lh.format_float(stats["mean"]),
        "median_ar": lh.format_float(stats["median"]),
        "t_stat": lh.format_float(stats["t"], 3),
        "p_value": lh.format_float(stats["p"], 6),
        "win_rate": lh.format_float(stats["win_rate"], 4),
    }


def interval_rows() -> list[dict[str, Any]]:
    events = base.fetch_events(base.load_market_data())
    frames = lh.market_frames()
    first_ids = lh.first_cluster_event_ids(events)
    clean_ids = lh.sec_clean_ids()
    rows = []
    for event in events:
        frame = frames.get(event.data_ticker)
        idx = lh.first_idx(frame, event.effective_trading_event_date) if frame is not None else None
        if idx is None or frame is None:
            continue
        common = {
            "event_id": event.event_id,
            "ticker": event.ticker,
            "creator": event.creator,
            "recommendation_type": event.recommendation_type,
            "top5_flag": lh.bool_text(event.ticker in base.TOP5_TICKERS),
            "low_lookahead_flag": lh.bool_text(event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS),
            "duplicate_collapsed_flag": lh.bool_text(event.event_id in first_ids),
            "sec_clean_flag": lh.bool_text(event.event_id in clean_ids),
            "actionability_score": event.actionability_score
            if event.actionability_score is not None
            else "",
        }
        for label, start_offset, end_offset in INTERVALS:
            end = len(frame) - 1 if end_offset is None else idx + end_offset
            metrics = lh.window_metrics(
                frame, idx, idx + start_offset, end, allow_right_censor=True
            )
            rows.append(
                {
                    **common,
                    "interval": label,
                    "start_offset": start_offset,
                    "end_offset": "end_of_sample" if end_offset is None else end_offset,
                    "spy_interval_ar": lh.format_float(metrics.get("spy_bhar")),
                    "spy_interval_car": lh.format_float(metrics.get("spy_car")),
                    "right_censored": lh.bool_text(bool(metrics.get("right_censored"))),
                    "status": metrics.get("status", "missing"),
                    "missing_price_reason": metrics.get("missing_price_reason", ""),
                }
            )
    return rows


def path_rows() -> list[dict[str, Any]]:
    events = base.fetch_events(base.load_market_data())
    frames = lh.market_frames()
    first_ids = lh.first_cluster_event_ids(events)
    clean_ids = lh.sec_clean_ids()
    rows = []
    for event in events:
        frame = frames.get(event.data_ticker)
        idx = lh.first_idx(frame, event.effective_trading_event_date) if frame is not None else None
        if idx is None or frame is None:
            continue
        for offset in PATH_OFFSETS:
            pos = idx + offset
            if pos <= 0 or pos >= len(frame):
                continue
            daily_ar = lh.clean_float(frame.iloc[pos]["daily_spy_ar"])
            if daily_ar is None:
                continue
            rows.append(
                {
                    "event_id": event.event_id,
                    "ticker": event.ticker,
                    "creator": event.creator,
                    "recommendation_type": event.recommendation_type,
                    "event_time_day": offset,
                    "daily_spy_ar": daily_ar,
                    "top5_flag": event.ticker in base.TOP5_TICKERS,
                    "low_lookahead_flag": event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS,
                    "duplicate_collapsed_flag": event.event_id in first_ids,
                    "sec_clean_flag": event.event_id in clean_ids,
                    "high_quality": (event.actionability_score or 0) >= 3,
                }
            )
    if not rows:
        return []
    df = pd.DataFrame(rows)
    specs = {
        "all": df.index == df.index,
        "top5": df["top5_flag"],
        "non_top": ~df["top5_flag"],
        "buy": df["recommendation_type"].eq("buy"),
        "sell": df["recommendation_type"].eq("sell"),
        "low_lookahead": df["low_lookahead_flag"],
        "duplicate_collapsed": df["duplicate_collapsed_flag"],
        "SEC_clean": df["sec_clean_flag"],
        "high_quality": df["high_quality"],
    }
    out = []
    for spec, mask in specs.items():
        selected = df[mask]
        for day, group in selected.groupby("event_time_day"):
            stats = t_summary(group["daily_spy_ar"])
            out.append({"specification": spec, "event_time_day": day, **stats})
    return out


def summarize_intervals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(rows)
    df = df[df["status"].eq("computed")].copy()
    df["spy_interval_ar"] = pd.to_numeric(df["spy_interval_ar"], errors="coerce")
    out = []
    for spec, mask in masks(df).items():
        selected = df[mask]
        for interval, group in selected.groupby("interval", sort=False):
            out.append(
                {
                    "specification": spec,
                    "interval": interval,
                    "right_censored": int(group["right_censored"].eq("True").sum()),
                    **t_summary(group["spy_interval_ar"]),
                }
            )
    return out


def reversal_rows(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(summary)
    rows = []
    for spec in ["all", "top5", "non_top", "buy", "sell", "SEC_clean"]:
        subset = df[df["specification"].eq(spec)].set_index("interval")
        if subset.empty or "0_5" not in subset.index:
            continue
        early = lh.clean_float(subset.loc["0_5", "mean_ar"])
        for later in ["6_20", "21_63", "64_126", "127_252", "253_504"]:
            if later not in subset.index:
                continue
            later_mean = lh.clean_float(subset.loc[later, "mean_ar"])
            rows.append(
                {
                    "specification": spec,
                    "early_interval": "0_5",
                    "later_interval": later,
                    "early_mean_ar": lh.format_float(early),
                    "later_mean_ar": lh.format_float(later_mean),
                    "fade_or_reversal": lh.format_float(
                        None if early is None or later_mean is None else later_mean - early
                    ),
                    "interpretation": "negative means post-event fade relative to first week",
                }
            )
    return rows


def interpretation(summary: list[dict[str, Any]], reversals: list[dict[str, Any]]) -> None:
    df = pd.DataFrame(summary)
    lines = ["# V2 Event-Time Decay Interpretation", ""]
    for spec in ["all", "top5", "non_top"]:
        sub = df[df["specification"].eq(spec)]
        if sub.empty:
            continue
        lines.append(f"## {spec}")
        for row in sub.to_dict("records"):
            lines.append(f"- {row['interval']}: mean AR `{row['mean_ar']}`, p `{row['p_value']}`")
        lines.append("")
    rev = pd.DataFrame(reversals)
    if not rev.empty:
        lines.append(
            "Reversal rows compare later intervals with the first post-event week. Negative values imply fade; positive values imply drift."
        )
    lines.append(
        "\nThis decomposition separates the first-week attention effect from later drift or reversal. "
        "It remains associative because event timing can coincide with momentum and public news."
    )
    base.write_md(DECAY_DIR / "04_decay_interpretation.md", "\n".join(lines))


def main() -> int:
    intervals = interval_rows()
    base.write_csv(
        DECAY_DIR / "00_interval_event_returns.csv",
        intervals,
        list(intervals[0]) if intervals else ["status"],
    )
    summary = summarize_intervals(intervals)
    write_table(DECAY_DIR / "01_interval_decomposition", summary, "V2 Interval Decomposition")
    path = path_rows()
    write_table(DECAY_DIR / "02_event_time_path", path, "V2 Event-Time Path")
    reversals = reversal_rows(summary)
    write_table(DECAY_DIR / "03_reversal_tests", reversals, "V2 Reversal Tests")
    interpretation(summary, reversals)
    base.write_csv(
        FIG_DIR / "v2_event_time_path.csv",
        path if path else [{"status": "no_rows"}],
        list(path[0]) if path else ["status"],
    )
    base.write_csv(
        FIG_DIR / "v2_reversal_decomposition.csv",
        reversals if reversals else [{"status": "no_rows"}],
        list(reversals[0]) if reversals else ["status"],
    )
    print(f"V2 event-time decay complete: intervals={len(intervals)} path_rows={len(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
