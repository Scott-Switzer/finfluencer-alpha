from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
LONG_DIR = OUT_DIR / "long_horizon"
FIG_DIR = OUT_DIR / "figures_data"
LONG_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

FORWARD_HORIZONS = [
    ("1D", 1),
    ("2D", 2),
    ("3D", 3),
    ("5D", 5),
    ("10D", 10),
    ("21D", 21),
    ("42D", 42),
    ("63D", 63),
    ("126D", 126),
    ("252D", 252),
    ("504D", 504),
    ("end_of_sample", None),
]
PRE_WINDOWS = [
    ("pre_-5_-1", -5),
    ("pre_-10_-1", -10),
    ("pre_-21_-1", -21),
    ("pre_-42_-1", -42),
    ("pre_-63_-1", -63),
    ("pre_-126_-1", -126),
    ("pre_-252_-1", -252),
]


def clean_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def format_float(value: Any, digits: int = 6) -> str:
    out = clean_float(value)
    return "" if out is None else f"{out:.{digits}f}"


def bool_text(value: bool) -> str:
    return "True" if value else "False"


def market_frames() -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for ticker, rows in base.load_market_data().items():
        frame = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        if frame.empty:
            continue
        frame["daily_stock_return"] = frame["adjusted_close"].pct_change()
        frame["daily_spy_return"] = frame["benchmark_adjusted_close"].pct_change()
        frame["daily_spy_ar"] = frame["daily_stock_return"] - frame["daily_spy_return"]
        frames[ticker] = frame
    return frames


def first_idx(frame: pd.DataFrame, target: Any) -> int | None:
    if target is None or frame.empty:
        return None
    dates = list(frame["date"])
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(dates) else None


def max_drawdown(prices: list[float]) -> float | None:
    if len(prices) < 2:
        return None
    peak = prices[0]
    worst = 0.0
    for price in prices[1:]:
        if price > peak:
            peak = price
        if peak:
            worst = min(worst, price / peak - 1.0)
    return worst


def max_runup(prices: list[float]) -> float | None:
    if len(prices) < 2:
        return None
    trough = prices[0]
    best = 0.0
    for price in prices[1:]:
        if price < trough:
            trough = price
        if trough:
            best = max(best, price / trough - 1.0)
    return best


def window_metrics(
    frame: pd.DataFrame,
    event_idx: int,
    start_idx: int,
    requested_end_idx: int,
    allow_right_censor: bool,
) -> dict[str, Any]:
    last_idx = len(frame) - 1
    left_censored = start_idx < 0
    right_censored = requested_end_idx > last_idx
    if left_censored:
        start_idx = 0
    if right_censored:
        if not allow_right_censor:
            return {
                "status": "missing",
                "missing_price_reason": "insufficient_forward_market_window",
                "left_censored": left_censored,
                "right_censored": True,
            }
        requested_end_idx = last_idx
    if start_idx < 0 or requested_end_idx <= start_idx or requested_end_idx > last_idx:
        return {
            "status": "missing",
            "missing_price_reason": "insufficient_market_window",
            "left_censored": left_censored,
            "right_censored": right_censored,
        }
    start = frame.iloc[start_idx]
    end = frame.iloc[requested_end_idx]
    stock_return = clean_float(end["adjusted_close"] / start["adjusted_close"] - 1.0)
    spy_return = clean_float(
        end["benchmark_adjusted_close"] / start["benchmark_adjusted_close"] - 1.0
    )
    daily = frame.iloc[start_idx + 1 : requested_end_idx + 1]
    daily_ar = [x for x in daily["daily_spy_ar"].tolist() if clean_float(x) is not None]
    daily_stock = [x for x in daily["daily_stock_return"].tolist() if clean_float(x) is not None]
    prices = [float(x) for x in frame.iloc[start_idx : requested_end_idx + 1]["adjusted_close"]]
    volatility = statistics.stdev(daily_stock) if len(daily_stock) > 1 else None
    return {
        "status": "computed",
        "start_trading_date": start["date"].isoformat(),
        "end_trading_date": end["date"].isoformat(),
        "available_trading_days": requested_end_idx - event_idx,
        "window_trading_days": requested_end_idx - start_idx,
        "raw_return": stock_return,
        "spy_bhar": None
        if stock_return is None or spy_return is None
        else stock_return - spy_return,
        "spy_car": sum(daily_ar) if daily_ar else None,
        "benchmark_return": spy_return,
        "max_drawdown": max_drawdown(prices),
        "max_runup": max_runup(prices),
        "realized_volatility": volatility,
        "hit": None if stock_return is None else stock_return > 0,
        "left_censored": left_censored,
        "right_censored": right_censored,
        "missing_price_reason": "",
    }


def first_cluster_event_ids(events: list[base.EventRecord]) -> set[int]:
    first: dict[int, int] = {}
    for event in events:
        first.setdefault(event.duplicate_cluster_id, event.event_id)
        first[event.duplicate_cluster_id] = min(first[event.duplicate_cluster_id], event.event_id)
    return set(first.values())


def sec_clean_ids() -> set[int]:
    path = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
    if not path.exists():
        return set()
    frame = pd.read_csv(path)
    if "sec_clean_flag" not in frame.columns:
        return set()
    return set(frame.loc[frame["sec_clean_flag"].astype(bool), "event_id"].astype(int))


def sec_confounded_ids() -> set[int]:
    path = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
    if not path.exists():
        return set()
    frame = pd.read_csv(path)
    if "sec_confounded_flag" not in frame.columns:
        return set()
    return set(frame.loc[frame["sec_confounded_flag"].astype(bool), "event_id"].astype(int))


def build_event_return_rows() -> list[dict[str, Any]]:
    events = base.fetch_events(base.load_market_data())
    frames = market_frames()
    first_ids = first_cluster_event_ids(events)
    clean_ids = sec_clean_ids()
    confounded_ids = sec_confounded_ids()
    rows: list[dict[str, Any]] = []
    for event in events:
        frame = frames.get(event.data_ticker)
        event_idx = (
            first_idx(frame, event.effective_trading_event_date) if frame is not None else None
        )
        common = {
            "event_id": event.event_id,
            "video_id": event.video_id,
            "creator": event.creator,
            "channel_id": event.channel_id,
            "ticker": event.ticker,
            "data_ticker": event.data_ticker,
            "company_name": event.company_name,
            "recommendation_type": event.recommendation_type,
            "event_date": event.event_date.isoformat() if event.event_date else "",
            "effective_trading_event_date": (
                event.effective_trading_event_date.isoformat()
                if event.effective_trading_event_date
                else ""
            ),
            "upload_timing_bucket": event.timing_bucket,
            "top5_flag": bool_text(event.ticker in base.TOP5_TICKERS),
            "low_lookahead_flag": bool_text(event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS),
            "duplicate_collapsed_flag": bool_text(event.event_id in first_ids),
            "duplicate_cluster_id": event.duplicate_cluster_id,
            "actionability_score": event.actionability_score
            if event.actionability_score is not None
            else "",
            "confidence_score": format_float(event.confidence_score),
            "sec_clean_flag": bool_text(event.event_id in clean_ids),
            "sec_confounded_flag": bool_text(event.event_id in confounded_ids),
        }
        if frame is None or event_idx is None:
            for label, days in FORWARD_HORIZONS:
                rows.append(
                    {
                        **common,
                        "window_type": "forward",
                        "horizon": label,
                        "requested_horizon_days": "" if days is None else days,
                        "status": "missing",
                        "missing_price_reason": "missing_market_data_or_event_date",
                    }
                )
            for label, days in PRE_WINDOWS:
                rows.append(
                    {
                        **common,
                        "window_type": "pre",
                        "horizon": label,
                        "requested_horizon_days": abs(days),
                        "status": "missing",
                        "missing_price_reason": "missing_market_data_or_event_date",
                    }
                )
            continue
        for label, days in FORWARD_HORIZONS:
            end_idx = len(frame) - 1 if days is None else event_idx + days
            metrics = window_metrics(frame, event_idx, event_idx, end_idx, allow_right_censor=True)
            rows.append(
                {
                    **common,
                    "window_type": "forward",
                    "horizon": label,
                    "requested_horizon_days": "" if days is None else days,
                    **metrics,
                }
            )
        for label, days in PRE_WINDOWS:
            metrics = window_metrics(
                frame, event_idx, event_idx + days, event_idx, allow_right_censor=False
            )
            rows.append(
                {
                    **common,
                    "window_type": "pre",
                    "horizon": label,
                    "requested_horizon_days": abs(days),
                    **metrics,
                }
            )
    return rows


def write_table(
    path: Path, rows: list[dict[str, Any]], title: str, columns: list[str] | None = None
) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    if columns is None:
        columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    preview = rows[:80]
    base.write_md(path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(preview, columns))


def t_summary(values: pd.Series) -> dict[str, Any]:
    clean = [float(v) for v in values.dropna().tolist()]
    stats = base.t_test(clean)
    return {
        "n": stats["n"],
        "mean": format_float(stats["mean"]),
        "median": format_float(stats["median"]),
        "t_stat": format_float(stats["t"], 3),
        "p_value": format_float(stats["p"], 6),
        "win_rate": format_float(stats["win_rate"], 4),
    }


def summarize_by_spec(df: pd.DataFrame) -> list[dict[str, Any]]:
    forward = df[(df["window_type"] == "forward") & (df["status"] == "computed")].copy()
    specs = {
        "all": forward.index == forward.index,
        "top5": forward["top5_flag"].eq("True"),
        "non_top": forward["top5_flag"].eq("False"),
        "buy": forward["recommendation_type"].eq("buy"),
        "sell": forward["recommendation_type"].eq("sell"),
        "low_lookahead": forward["low_lookahead_flag"].eq("True"),
        "duplicate_collapsed": forward["duplicate_collapsed_flag"].eq("True"),
        "SEC_clean": forward["sec_clean_flag"].eq("True"),
        "SEC_confounded": forward["sec_confounded_flag"].eq("True"),
    }
    rows = []
    for spec, mask in specs.items():
        selected = forward[mask]
        for horizon, group in selected.groupby("horizon", sort=False):
            stats_bhar = t_summary(pd.to_numeric(group["spy_bhar"], errors="coerce"))
            stats_raw = t_summary(pd.to_numeric(group["raw_return"], errors="coerce"))
            stats_car = t_summary(pd.to_numeric(group["spy_car"], errors="coerce"))
            rows.append(
                {
                    "specification": spec,
                    "horizon": horizon,
                    "requested_horizon_days": group["requested_horizon_days"].iloc[0],
                    "n_events": group["event_id"].nunique(),
                    "n_full_window": int(group["right_censored"].eq(False).sum()),
                    "n_right_censored": int(group["right_censored"].eq(True).sum()),
                    "mean_raw_return": stats_raw["mean"],
                    "mean_spy_bhar": stats_bhar["mean"],
                    "t_spy_bhar": stats_bhar["t_stat"],
                    "p_spy_bhar": stats_bhar["p_value"],
                    "median_spy_bhar": stats_bhar["median"],
                    "win_rate_spy_bhar": stats_bhar["win_rate"],
                    "mean_spy_car": stats_car["mean"],
                    "t_spy_car": stats_car["t_stat"],
                    "p_spy_car": stats_car["p_value"],
                    "notes": "right-censored rows retained and counted",
                }
            )
    return rows


def coverage_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    forward = df[df["window_type"] == "forward"].copy()
    rows = []
    for horizon, group in forward.groupby("horizon", sort=False):
        computed = group[group["status"] == "computed"]
        rows.append(
            {
                "horizon": horizon,
                "requested_horizon_days": group["requested_horizon_days"].iloc[0],
                "total_events": group["event_id"].nunique(),
                "n_with_return": computed["event_id"].nunique(),
                "n_full_window": int(computed["right_censored"].eq(False).sum()),
                "n_right_censored": int(computed["right_censored"].eq(True).sum()),
                "n_missing": int(group["status"].ne("computed").sum()),
                "mean_available_trading_days": format_float(
                    pd.to_numeric(computed["available_trading_days"], errors="coerce").mean(),
                    2,
                ),
                "notes": "long horizons are right-censored for recent recommendations",
            }
        )
    return rows


def group_horizon_summary(df: pd.DataFrame, group_col: str, out_path: Path, title: str) -> None:
    forward = df[(df["window_type"] == "forward") & (df["status"] == "computed")].copy()
    keep_horizons = {"5D", "21D", "63D", "126D", "252D", "504D", "end_of_sample"}
    rows = []
    for (group_value, horizon), group in forward[forward["horizon"].isin(keep_horizons)].groupby(
        [group_col, "horizon"],
        dropna=False,
    ):
        stats_bhar = t_summary(pd.to_numeric(group["spy_bhar"], errors="coerce"))
        rows.append(
            {
                group_col: group_value,
                "horizon": horizon,
                "event_count": group["event_id"].nunique(),
                "mean_spy_bhar": stats_bhar["mean"],
                "t_spy_bhar": stats_bhar["t_stat"],
                "p_spy_bhar": stats_bhar["p_value"],
                "median_spy_bhar": stats_bhar["median"],
                "win_rate_spy_bhar": stats_bhar["win_rate"],
                "right_censored": int(group["right_censored"].eq(True).sum()),
            }
        )
    write_table(out_path, rows, title)


def write_workplan() -> None:
    text = """# V2 Long-Horizon News and Alpha Workplan

The existing v2 package is strong for 1D/5D event windows, but that window is
too narrow to distinguish attention pops from durable alpha, medium-term
reversal, or long-run drift. Longer horizons matter because a recommendation
can coincide with short-lived attention, trend-following, or delayed
underperformance.

Long-horizon tests need both CAR and BHAR. CAR tracks summed daily abnormal
returns, while BHAR captures compounded holding-period performance. Calendar-
time portfolios are needed because overlapping event windows can make event-
level inference look stronger than an implementable strategy. Censoring controls
are required because recent events cannot have one- or two-year follow-up.

The largest credibility gap is still real public-news coverage. Simulated
free-news outputs are not evidence. Real provider status must be reported as
clean, confounded, or unknown.

Causality is treated as a falsification problem. The package tests pretrends,
matched controls, placebo dates, event-time decay, and long-run reversals; it
does not claim random assignment.

Priority list:
1. long-horizon return panel
2. long-horizon alpha / BHAR / CAR
3. event-time decay and reversal
4. real public-news provider repair
5. multi-provider compact news flags
6. long-horizon portfolio tests
7. creator/ticker fixed-effect regressions
8. matched controls / placebos at longer horizons
9. final narrative rewrite
"""
    base.write_md(OUT_DIR / "20_v2_long_horizon_news_alpha_workplan.md", text)


def write_interpretation(
    summary_rows: list[dict[str, Any]], coverage: list[dict[str, Any]]
) -> None:
    summary = pd.DataFrame(summary_rows)
    lines = ["# V2 Long-Horizon Return Interpretation", ""]
    for spec in ["all", "top5", "non_top", "buy", "sell", "SEC_clean"]:
        subset = summary[
            (summary["specification"] == spec)
            & (summary["horizon"].isin(["5D", "21D", "63D", "126D", "252D", "504D"]))
        ]
        if subset.empty:
            continue
        lines.append(f"## {spec}")
        for row in subset.to_dict("records"):
            lines.append(
                f"- {row['horizon']}: mean SPY-adjusted BHAR `{row['mean_spy_bhar']}`, "
                f"p `{row['p_spy_bhar']}`, right-censored `{row['n_right_censored']}`"
            )
        lines.append("")
    coverage_df = pd.DataFrame(coverage)
    if not coverage_df.empty:
        last = coverage_df.iloc[-1]
        lines.append(
            "Long-horizon coverage is explicitly censored: "
            f"`{last['horizon']}` has `{last['n_with_return']}` returns and "
            f"`{last['n_right_censored']}` right-censored rows."
        )
    lines.append(
        "\nInterpret these estimates as event-time associations. They are not "
        "causal proof and do not establish tradable alpha without separate "
        "portfolio, cost, and public-news controls."
    )
    base.write_md(LONG_DIR / "08_v2_long_horizon_interpretation.md", "\n".join(lines))


def main() -> int:
    write_workplan()
    rows = build_event_return_rows()
    columns = list(rows[0]) if rows else ["status"]
    base.write_csv(LONG_DIR / "01_v2_long_horizon_event_returns.csv", rows, columns)
    df = pd.DataFrame(rows)
    coverage = coverage_rows(df)
    write_table(LONG_DIR / "02_v2_long_horizon_coverage", coverage, "V2 Long-Horizon Coverage")
    summary = summarize_by_spec(df)
    write_table(
        LONG_DIR / "03_v2_long_horizon_summary_by_spec", summary, "V2 Long-Horizon Summary by Spec"
    )
    summary_df = pd.DataFrame(summary)
    top_non = summary_df[summary_df["specification"].isin(["top5", "non_top"])].to_dict("records")
    buy_sell = summary_df[summary_df["specification"].isin(["buy", "sell"])].to_dict("records")
    write_table(
        LONG_DIR / "04_v2_long_horizon_top5_vs_non_top", top_non, "V2 Top5 vs Non-Top Long-Horizon"
    )
    write_table(
        LONG_DIR / "05_v2_long_horizon_buy_vs_sell", buy_sell, "V2 Buy vs Sell Long-Horizon"
    )
    group_horizon_summary(
        df,
        "creator",
        LONG_DIR / "06_v2_long_horizon_creator_summary",
        "V2 Creator Long-Horizon Summary",
    )
    group_horizon_summary(
        df,
        "ticker",
        LONG_DIR / "07_v2_long_horizon_ticker_summary",
        "V2 Ticker Long-Horizon Summary",
    )
    write_interpretation(summary, coverage)
    fig_decay = summary_df[summary_df["specification"].eq("all")].to_dict("records")
    fig_top = summary_df[summary_df["specification"].isin(["top5", "non_top"])].to_dict("records")
    base.write_csv(
        FIG_DIR / "v2_long_horizon_decay_curve.csv",
        fig_decay,
        list(fig_decay[0]) if fig_decay else ["status"],
    )
    base.write_csv(
        FIG_DIR / "v2_top5_non_top_long_horizon.csv",
        fig_top,
        list(fig_top[0]) if fig_top else ["status"],
    )
    base.write_csv(
        FIG_DIR / "v2_long_horizon_coverage_funnel.csv",
        coverage,
        list(coverage[0]) if coverage else ["status"],
    )
    print(f"V2 long-horizon returns complete: rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
