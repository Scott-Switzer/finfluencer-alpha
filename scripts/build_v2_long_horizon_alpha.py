from __future__ import annotations

import math
import random
import statistics
import sys
from bisect import bisect_right
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402
import build_v2_factor_adjusted_alpha as factor_base  # noqa: E402
import build_v2_long_horizon_returns as lh  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
ALPHA_DIR = OUT_DIR / "long_horizon_alpha"
ALPHA_DIR.mkdir(parents=True, exist_ok=True)
RNG = random.Random(496)
TARGET_HORIZONS = ["5D", "10D", "21D", "42D", "63D", "126D", "252D", "504D", "end_of_sample"]


def write_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    base.write_md(
        path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(rows[:100], columns)
    )


def t_stats(values: list[float]) -> dict[str, Any]:
    stats = base.t_test(values)
    se = ""
    if stats["n"] and stats["n"] > 1:
        se = lh.format_float(statistics.stdev(values) / math.sqrt(int(stats["n"])))
    return {
        "n": stats["n"],
        "mean": lh.format_float(stats["mean"]),
        "standard_error": se,
        "median": lh.format_float(stats["median"]),
        "t_stat": lh.format_float(stats["t"], 3),
        "p_value": lh.format_float(stats["p"], 6),
        "win_rate": lh.format_float(stats["win_rate"], 4),
    }


def load_long_returns() -> pd.DataFrame:
    path = OUT_DIR / "long_horizon" / "01_v2_long_horizon_event_returns.csv"
    if not path.exists():
        raise FileNotFoundError("Run build_v2_long_horizon_returns.py first")
    df = pd.read_csv(path)
    return df[(df["window_type"] == "forward") & (df["horizon"].isin(TARGET_HORIZONS))].copy()


def sample_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "all": df.index == df.index,
        "top5": df["top5_flag"].eq(True) | df["top5_flag"].eq("True"),
        "non_top": df["top5_flag"].eq(False) | df["top5_flag"].eq("False"),
        "buy": df["recommendation_type"].eq("buy"),
        "sell": df["recommendation_type"].eq("sell"),
        "low_lookahead": df["low_lookahead_flag"].eq(True) | df["low_lookahead_flag"].eq("True"),
        "duplicate_collapsed": df["duplicate_collapsed_flag"].eq(True)
        | df["duplicate_collapsed_flag"].eq("True"),
        "SEC_clean": df["sec_clean_flag"].eq(True) | df["sec_clean_flag"].eq("True"),
    }


def summarize_metric(df: pd.DataFrame, metric: str, benchmark: str) -> list[dict[str, Any]]:
    rows = []
    for sample, mask in sample_masks(df).items():
        selected = df[mask]
        for horizon, group in selected.groupby("horizon", sort=False):
            values = [float(v) for v in pd.to_numeric(group[metric], errors="coerce").dropna()]
            stats = t_stats(values)
            rows.append(
                {
                    "sample": sample,
                    "horizon": horizon,
                    "benchmark_or_model": benchmark,
                    "right_censored": int(group["right_censored"].astype(str).eq("True").sum()),
                    **stats,
                    "notes": "BHAR is compounded holding-period abnormal return; CAR is summed daily abnormal return",
                }
            )
    return rows


def factor_alpha_rows(long_df: pd.DataFrame) -> list[dict[str, Any]]:
    factors, status_rows = factor_base.load_factors()
    write_table(ALPHA_DIR / "00_factor_data_status", status_rows, "Long-Horizon Factor Data Status")
    if factors.empty:
        return []
    factor_dates = list(factors.index)
    factor_cum = factors.cumsum()

    def factor_window_sum(start: Any, end: Any, cols: list[str]) -> float | None:
        if start is None or end is None:
            return None
        left = bisect_right(factor_dates, start) - 1
        right = bisect_right(factor_dates, end) - 1
        if right < 0 or right <= left:
            return None
        needed = cols + ["RF"]
        if any(col not in factor_cum.columns for col in needed):
            return None
        right_vals = factor_cum.iloc[right][needed]
        left_vals = factor_cum.iloc[left][needed] if left >= 0 else 0.0
        diff = right_vals - left_vals
        if pd.isna(diff).any():
            return None
        return float(diff.sum())

    model_specs = {
        "CAPM": ["Mkt-RF"],
        "FF3": ["Mkt-RF", "SMB", "HML"],
        "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
        "Carhart": ["Mkt-RF", "SMB", "HML", "MOM"],
    }
    rows = []
    for row in long_df[long_df["status"].eq("computed")].to_dict("records"):
        raw_return = lh.clean_float(row.get("raw_return"))
        if raw_return is None:
            continue
        start = base.parse_date(row.get("start_trading_date"))
        end = base.parse_date(row.get("end_trading_date"))
        for model, cols in model_specs.items():
            if not all(col in factors.columns for col in cols + ["RF"]):
                status = "missing_factor_columns"
                alpha = None
            else:
                expected = factor_window_sum(start, end, cols)
                alpha = None if expected is None else raw_return - expected
                status = "computed" if alpha is not None else "missing_factor_window"
            rows.append(
                {
                    "event_id": row["event_id"],
                    "ticker": row["ticker"],
                    "creator": row["creator"],
                    "recommendation_type": row["recommendation_type"],
                    "horizon": row["horizon"],
                    "model": model,
                    "alpha": lh.format_float(alpha),
                    "top5_flag": row["top5_flag"],
                    "low_lookahead_flag": row["low_lookahead_flag"],
                    "duplicate_collapsed_flag": row["duplicate_collapsed_flag"],
                    "sec_clean_flag": row["sec_clean_flag"],
                    "right_censored": row["right_censored"],
                    "available_trading_days": row.get("available_trading_days", ""),
                    "status": status,
                    "estimation_model": "factor_basket_stress_test_not_beta_estimated",
                }
            )
    base.write_csv(
        ALPHA_DIR / "00_long_horizon_factor_event_alpha.csv",
        rows if rows else [{"status": "no_rows"}],
        list(rows[0]) if rows else ["status"],
    )
    return rows


def summarize_factor_alpha(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    df = df[df["status"].eq("computed")].copy()
    out = []
    for sample, mask in sample_masks(df).items():
        selected = df[mask]
        for (model, horizon), group in selected.groupby(["model", "horizon"], sort=False):
            values = [float(v) for v in pd.to_numeric(group["alpha"], errors="coerce").dropna()]
            stats = t_stats(values)
            out.append(
                {
                    "sample": sample,
                    "model": model,
                    "horizon": horizon,
                    "right_censored": int(group["right_censored"].astype(str).eq("True").sum()),
                    **stats,
                    "notes": (
                        "factor-basket stress test using free Kenneth French daily factors; "
                        "not beta-estimated asset-pricing proof"
                    ),
                }
            )
    return out


def calendar_time_alpha(
    events: list[base.EventRecord], holding_days: int = 21
) -> list[dict[str, Any]]:
    frames = lh.market_frames()
    daily_rows = []
    for event in events:
        frame = frames.get(event.data_ticker)
        idx = lh.first_idx(frame, event.effective_trading_event_date) if frame is not None else None
        if idx is None:
            continue
        end = min(idx + holding_days, len(frame) - 1)
        for pos in range(idx + 1, end + 1):
            ar = lh.clean_float(frame.iloc[pos]["daily_spy_ar"])
            if ar is None:
                continue
            daily_rows.append(
                {
                    "date": frame.iloc[pos]["date"],
                    "event_id": event.event_id,
                    "ticker": event.ticker,
                    "creator": event.creator,
                    "recommendation_type": event.recommendation_type,
                    "top5_flag": event.ticker in base.TOP5_TICKERS,
                    "low_lookahead_flag": event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS,
                    "daily_ar": ar,
                }
            )
    if not daily_rows:
        return []
    daily = pd.DataFrame(daily_rows)
    samples = {
        "all": daily.index == daily.index,
        "top5": daily["top5_flag"],
        "non_top": ~daily["top5_flag"],
        "buy": daily["recommendation_type"].eq("buy"),
        "sell": daily["recommendation_type"].eq("sell"),
        "low_lookahead": daily["low_lookahead_flag"],
    }
    rows = []
    for sample, mask in samples.items():
        selected = daily[mask]
        portfolio = selected.groupby("date", as_index=False)["daily_ar"].mean()
        values = [float(v) for v in portfolio["daily_ar"]]
        stats = t_stats(values)
        rows.append(
            {
                "sample": sample,
                "holding_days": holding_days,
                "calendar_days": len(portfolio),
                "active_event_days": len(selected),
                "mean_daily_abnormal_return": stats["mean"],
                "annualized_abnormal_return_proxy": lh.format_float(
                    (1 + float(stats["mean"] or 0)) ** 252 - 1 if stats["mean"] else None
                ),
                "t_stat": stats["t_stat"],
                "p_value": stats["p_value"],
                "notes": "daily equal-weighted active recommendation calendar-time portfolio",
            }
        )
    return rows


def bootstrap_ci(values: list[float], iterations: int = 500) -> tuple[str, str]:
    if len(values) < 3:
        return "", ""
    means = []
    for _ in range(iterations):
        sample = [RNG.choice(values) for _ in values]
        means.append(statistics.mean(sample))
    means.sort()
    return lh.format_float(means[int(0.025 * iterations)]), lh.format_float(
        means[int(0.975 * iterations)]
    )


def inference_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    selected = df[
        (df["status"] == "computed") & (df["horizon"].isin(["5D", "21D", "63D", "126D", "252D"]))
    ].copy()
    p_values = []
    pending: list[dict[str, Any]] = []
    for sample, mask in {
        k: v
        for k, v in sample_masks(selected).items()
        if k in {"all", "top5", "non_top", "buy", "sell"}
    }.items():
        group_df = selected[mask]
        for horizon, group in group_df.groupby("horizon", sort=False):
            values = [float(v) for v in pd.to_numeric(group["spy_bhar"], errors="coerce").dropna()]
            stats = t_stats(values)
            lower, upper = bootstrap_ci(values)
            by_ticker = group.groupby("ticker")["spy_bhar"].mean(numeric_only=True)
            by_creator = group.groupby("creator")["spy_bhar"].mean(numeric_only=True)
            ticker_stats = t_stats([float(v) for v in by_ticker.dropna()])
            creator_stats = t_stats([float(v) for v in by_creator.dropna()])
            raw_p = lh.clean_float(stats["p_value"])
            row = {
                "sample": sample,
                "horizon": horizon,
                "n": stats["n"],
                "mean_spy_bhar": stats["mean"],
                "naive_p": stats["p_value"],
                "bootstrap_ci_lower": lower,
                "bootstrap_ci_upper": upper,
                "ticker_cluster_mean_p_proxy": ticker_stats["p_value"],
                "creator_cluster_mean_p_proxy": creator_stats["p_value"],
                "bh_fdr_q": "",
                "notes": "cluster columns use cluster-mean proxy inference",
            }
            pending.append(row)
            if raw_p is not None:
                p_values.append((len(pending) - 1, raw_p))
    ranked = sorted(p_values, key=lambda item: item[1])
    m = len(ranked)
    q_values: dict[int, float] = {}
    prev = 1.0
    for rank, (idx, p_value) in enumerate(reversed(ranked), start=1):
        original_rank = m - rank + 1
        q = min(prev, p_value * m / original_rank)
        q_values[idx] = q
        prev = q
    for idx, q in q_values.items():
        pending[idx]["bh_fdr_q"] = lh.format_float(q, 6)
    rows.extend(pending)
    return rows


def interpretation(
    bhar: list[dict[str, Any]], car: list[dict[str, Any]], factor: list[dict[str, Any]]
) -> None:
    bhar_df = pd.DataFrame(bhar)
    factor_df = pd.DataFrame(factor)
    lines = ["# Long-Horizon Alpha Interpretation", ""]
    for sample in ["all", "top5", "non_top"]:
        subset = bhar_df[
            (bhar_df["sample"] == sample)
            & (bhar_df["horizon"].isin(["21D", "63D", "126D", "252D", "504D"]))
        ]
        if subset.empty:
            continue
        lines.append(f"## {sample} SPY-adjusted BHAR")
        for row in subset.to_dict("records"):
            lines.append(f"- {row['horizon']}: mean `{row['mean']}`, p `{row['p_value']}`")
        lines.append("")
    if not factor_df.empty:
        ff5 = factor_df[
            (factor_df["model"] == "FF5")
            & (factor_df["horizon"].isin(["21D", "63D", "126D", "252D"]))
        ]
        lines.append("## Factor Adjustment")
        for row in ff5[ff5["sample"].isin(["all", "top5", "non_top", "SEC_clean"])].to_dict(
            "records"
        ):
            lines.append(
                f"- {row['sample']} {row['horizon']} FF5 alpha: `{row['mean']}`, p `{row['p_value']}`"
            )
    lines.append(
        "\nBHAR and CAR are both reported because compounding and daily abnormal-return "
        "aggregation can diverge over long horizons. Factor results should be read as "
        "stress tests for momentum and broad market exposure, not as causal evidence."
    )
    base.write_md(ALPHA_DIR / "06_long_horizon_alpha_interpretation.md", "\n".join(lines))


def main() -> int:
    long_df = load_long_returns()
    computed = long_df[long_df["status"].eq("computed")].copy()
    bhar_rows = summarize_metric(computed, "spy_bhar", "SPY_BHAR")
    car_rows = summarize_metric(computed, "spy_car", "SPY_CAR")
    write_table(ALPHA_DIR / "01_bhar_summary", bhar_rows, "Long-Horizon BHAR Summary")
    write_table(ALPHA_DIR / "02_car_summary", car_rows, "Long-Horizon CAR Summary")
    cal_rows = []
    events = base.fetch_events(base.load_market_data())
    for holding in [21, 63]:
        cal_rows.extend(calendar_time_alpha(events, holding))
    write_table(ALPHA_DIR / "03_calendar_time_alpha", cal_rows, "Calendar-Time Alpha")
    factor_event_rows = factor_alpha_rows(computed)
    factor_rows = summarize_factor_alpha(factor_event_rows)
    write_table(
        ALPHA_DIR / "04_long_horizon_factor_alpha", factor_rows, "Long-Horizon Factor Alpha"
    )
    inf_rows = inference_rows(computed)
    write_table(ALPHA_DIR / "05_long_horizon_inference", inf_rows, "Long-Horizon Inference")
    interpretation(bhar_rows, car_rows, factor_rows)
    print(
        "V2 long-horizon alpha complete: "
        f"bhar_rows={len(bhar_rows)} factor_event_rows={len(factor_event_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
