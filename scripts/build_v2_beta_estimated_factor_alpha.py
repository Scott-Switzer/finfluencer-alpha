
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402
import build_v2_factor_adjusted_alpha as factor_base  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "factor_alpha_beta_estimated"
HORIZON_DAYS = {"5D": 5, "21D": 21, "63D": 63, "126D": 126, "252D": 252}
MODELS = {
    "CAPM": ["Mkt-RF"],
    "FF3": ["Mkt-RF", "SMB", "HML"],
    "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    "Carhart": ["Mkt-RF", "SMB", "HML", "MOM"],
    "FF5_MOM": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
}


def market_frames() -> dict[str, pd.DataFrame]:
    frames = {}
    for ticker, rows in base.load_market_data().items():
        frame = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        frame["daily_return"] = frame["adjusted_close"].pct_change()
        frames[ticker] = frame
    return frames


def first_idx(frame: pd.DataFrame, target: Any) -> int | None:
    if target is None or frame.empty:
        return None
    matches = frame.index[frame["date"] >= target].tolist()
    return int(matches[0]) if matches else None


def fit_beta_cached(
    frame: pd.DataFrame,
    idx: int,
    factors: pd.DataFrame,
    cols: list[str],
) -> tuple[str, np.ndarray | None, int]:
    for start_offset, end_offset in [(-252, -21), (-504, -21), (-126, -21)]:
        start = max(1, idx + start_offset)
        end = max(1, idx + end_offset)
        rows = []
        for pos in range(start, min(end + 1, len(frame))):
            d = frame.loc[pos, "date"]
            if d not in factors.index:
                continue
            factor_row = factors.loc[d]
            if any(pd.isna(factor_row.get(col)) for col in cols + ["RF"]):
                continue
            y = frame.loc[pos, "daily_return"] - float(factor_row["RF"])
            if pd.isna(y):
                continue
            rows.append((float(y), [float(factor_row[col]) for col in cols]))
        if len(rows) >= max(60, len(cols) * 12):
            y = np.array([row[0] for row in rows])
            x = np.array([[1.0] + row[1] for row in rows])
            try:
                beta = np.linalg.lstsq(x, y, rcond=None)[0]
            except np.linalg.LinAlgError:
                return "singular_beta_window", None, len(rows)
            return f"{abs(start_offset)}to{abs(end_offset)}", beta, len(rows)
    return "insufficient_beta_history", None, 0


def expected_sum(frame: pd.DataFrame, idx: int, horizon: int, factors: pd.DataFrame, cols: list[str], beta: np.ndarray) -> float | None:
    if idx + horizon >= len(frame):
        return None
    total = 0.0
    for pos in range(idx + 1, idx + horizon + 1):
        d = frame.loc[pos, "date"]
        if d not in factors.index:
            return None
        factor_row = factors.loc[d]
        if any(pd.isna(factor_row.get(col)) for col in cols + ["RF"]):
            return None
        total += float(factor_row["RF"]) + float(beta[0])
        total += float(np.dot(beta[1:], [float(factor_row[col]) for col in cols]))
    return total


def build_rows() -> list[dict[str, Any]]:
    factors, status_rows = factor_base.load_factors()
    utils.table_pair(OUT_DIR / "00_factor_download_status", status_rows, "Factor Download Status")
    if factors.empty:
        return []
    frames = market_frames()
    manifest = utils.event_manifest()
    panel = utils.forward_panel(list(HORIZON_DAYS)).set_index(["event_id", "horizon"])
    beta_cache: dict[tuple[str, str, str], tuple[str, np.ndarray | None, int]] = {}
    rows = []
    for _, event in manifest.iterrows():
        ticker = str(event.ticker)
        frame = frames.get(ticker)
        event_date = utils.parse_date(event.effective_trading_event_date or event.event_date)
        if event_date is not None and pd.isna(event_date):
            event_date = None
        idx = first_idx(frame, event_date) if frame is not None else None
        month_key = event_date.strftime("%Y-%m") if event_date else "missing"
        for model, cols in MODELS.items():
            beta_key = (ticker, model, month_key)
            if frame is None or idx is None:
                beta_window, beta, observations = "missing_market_or_event_date", None, 0
            elif not all(col in factors.columns for col in cols + ["RF"]):
                beta_window, beta, observations = "missing_factor_columns", None, 0
            elif beta_key in beta_cache:
                beta_window, beta, observations = beta_cache[beta_key]
            else:
                beta_window, beta, observations = fit_beta_cached(frame, idx, factors, cols)
                beta_cache[beta_key] = (beta_window, beta, observations)
            for horizon, days in HORIZON_DAYS.items():
                actual = None
                right_censored = ""
                if (int(event.event_id), horizon) in panel.index:
                    lp = panel.loc[(int(event.event_id), horizon)]
                    actual = utils.clean_float(lp.get("raw_return"))
                    right_censored = str(lp.get("right_censored", ""))
                if actual is None or beta is None or frame is None or idx is None:
                    alpha = None
                    status = beta_window if beta is None else "missing_actual_return"
                else:
                    expected = expected_sum(frame, idx, days, factors, cols, beta)
                    alpha = None if expected is None else actual - expected
                    status = "computed" if alpha is not None else "missing_event_window_factor_or_price"
                rows.append(
                    {
                        "event_id": int(event.event_id),
                        "ticker": ticker,
                        "creator": event.creator,
                        "recommendation_type": event.recommendation_type,
                        "event_date": event.event_date,
                        "horizon": horizon,
                        "model": model,
                        "alpha": utils.fmt(alpha),
                        "top5_flag": ticker in utils.TOP5,
                        "low_lookahead_flag": str(event.upload_timing_bucket) in {"before_open", "weekend_or_holiday"},
                        "duplicate_cluster_id": "",
                        "right_censored": right_censored,
                        "beta_window": beta_window,
                        "beta_observations": observations,
                        "status": status,
                    }
                )
    return rows


def summarize(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    frame["alpha_num"] = pd.to_numeric(frame["alpha"], errors="coerce")
    specs = {
        "all": pd.Series(True, index=frame.index),
        "top5": frame["top5_flag"].astype(str).str.lower().eq("true"),
        "non_top": ~frame["top5_flag"].astype(str).str.lower().eq("true"),
        "buy": frame["recommendation_type"].eq("buy"),
        "sell": frame["recommendation_type"].eq("sell"),
        "low_lookahead": frame["low_lookahead_flag"].astype(str).str.lower().eq("true"),
    }
    out = []
    for sample, mask in specs.items():
        selected = frame[mask & frame["status"].eq("computed")]
        for (model, horizon), group in selected.groupby(["model", "horizon"]):
            stats = utils.t_stats(group["alpha_num"].dropna().tolist())
            out.append(
                {
                    "sample": sample,
                    "model": model,
                    "horizon": horizon,
                    "n": stats["n"],
                    "mean_alpha": utils.fmt(stats["mean"]),
                    "mean_alpha_pct": utils.fmt_pct(stats["mean"]),
                    "standard_error": utils.fmt(stats["standard_error"]),
                    "t_stat": utils.fmt(stats["t_stat"], 3),
                    "p_value": utils.fmt(stats["p_value"], 6),
                    "win_rate": utils.fmt(stats["win_rate"]),
                }
            )
    q_values = utils.bh_q_values([utils.clean_float(row["p_value"]) for row in out])
    for row, q_value in zip(out, q_values, strict=True):
        row["bh_q_value"] = utils.fmt(q_value)
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    utils.write_csv(OUT_DIR / "01_event_level_factor_alpha.csv", rows)
    frame = pd.DataFrame(rows)
    coverage = []
    if not frame.empty:
        for (model, horizon), group in frame.groupby(["model", "horizon"]):
            coverage.append(
                {
                    "model": model,
                    "horizon": horizon,
                    "rows": len(group),
                    "computed": int(group["status"].eq("computed").sum()),
                    "insufficient_or_missing": int((~group["status"].eq("computed")).sum()),
                }
            )
    utils.table_pair(OUT_DIR / "02_factor_alpha_coverage", coverage, "Factor Alpha Coverage")
    summary = summarize(frame)
    utils.table_pair(OUT_DIR / "03_factor_alpha_summary_by_spec", summary, "Factor Alpha Summary By Spec")
    cal_rows = [
        {**row, "regression_type": "event_level_beta_estimated_summary_not_hac_calendar_time"}
        for row in summary
        if row["sample"] in {"all", "top5", "non_top", "buy", "sell"} and row["horizon"] in {"21D", "63D"}
    ]
    utils.table_pair(OUT_DIR / "04_calendar_time_factor_regressions", cal_rows, "Calendar-Time Factor Regression Proxy")
    utils.write_csv(OUT_DIR / "05_factor_alpha_multiple_testing.csv", summary)
    utils.write_md(
        OUT_DIR / "06_factor_alpha_interpretation.md",
        "Beta-Estimated Factor Alpha Interpretation",
        "This layer estimates pre-event rolling ticker factor betas using month-level caching. It is stronger than the prior factor-basket stress test, but HAC calendar-time regressions remain approximated and should not be overclaimed.",
    )
    print(f"Beta-estimated factor alpha complete: rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
