from __future__ import annotations

import io
import math
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
FACTOR_DIR = OUT_DIR / "factors"
FACTOR_DIR.mkdir(parents=True, exist_ok=True)

FACTOR_URLS = {
    "FF3": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip",
    "FF5": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "MOM": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip",
}


def parse_french_zip(content: bytes, label: str) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        name = zf.namelist()[0]
        text = zf.read(name).decode("utf-8", errors="replace")
    lines = text.splitlines()
    header_idx = None
    for idx, line in enumerate(lines):
        if "Mkt-RF" in line or "Mom" in line:
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError(f"could not find factor header for {label}")
    data_lines = []
    for line in lines[header_idx:]:
        first = line.split(",", 1)[0].strip()
        if data_lines and (not first or not first.isdigit()):
            break
        data_lines.append(line)
    df = pd.read_csv(io.StringIO("\n".join(data_lines)))
    date_col = df.columns[0]
    df = df.rename(columns={date_col: "date"})
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce").dt.date
    df = df.dropna(subset=["date"]).set_index("date")
    df.columns = [str(c).strip() for c in df.columns]
    return df.apply(pd.to_numeric, errors="coerce") / 100.0


def load_factors() -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frames = {}
    status_rows = []
    for label, url in FACTOR_URLS.items():
        try:
            response = requests.get(url, timeout=40)
            if response.status_code != 200:
                status_rows.append({"factor_set": label, "status": f"http_{response.status_code}", "rows": 0})
                continue
            frame = parse_french_zip(response.content, label)
            frames[label] = frame
            status_rows.append({"factor_set": label, "status": "downloaded_in_memory", "rows": len(frame)})
        except Exception as exc:
            status_rows.append({"factor_set": label, "status": f"{type(exc).__name__}: {exc}", "rows": 0})
    if "FF3" not in frames:
        return pd.DataFrame(), status_rows
    factors = frames["FF3"].copy()
    if "FF5" in frames:
        for col in ["RMW", "CMA"]:
            if col in frames["FF5"].columns:
                factors[col] = frames["FF5"][col]
    if "MOM" in frames:
        mom_cols = [col for col in frames["MOM"].columns if col.lower().startswith("mom")]
        if mom_cols:
            factors["MOM"] = frames["MOM"][mom_cols[0]]
    return factors.sort_index(), status_rows


def daily_stock_returns(market: dict[str, list[dict[str, Any]]]) -> dict[str, dict[Any, float]]:
    out: dict[str, dict[Any, float]] = {}
    for ticker, rows in market.items():
        returns = {}
        for idx in range(1, len(rows)):
            p0 = rows[idx - 1]["adjusted_close"]
            p1 = rows[idx]["adjusted_close"]
            if p0:
                returns[rows[idx]["date"]] = (p1 / p0) - 1.0
        out[ticker] = returns
    return out


def fit_expected_return(
    event: base.EventRecord,
    horizon: int,
    model_cols: list[str],
    market: dict[str, list[dict[str, Any]]],
    stock_returns: dict[str, dict[Any, float]],
    factors: pd.DataFrame,
) -> float | None:
    rows = market.get(event.data_ticker, [])
    if not rows or event.weekday_adjusted_date is None:
        return None
    idx = base.first_on_or_after(rows, event.weekday_adjusted_date)
    if idx is None or idx + horizon >= len(rows):
        return None
    returns = stock_returns.get(event.data_ticker, {})
    regression_rows = []
    start = max(1, idx - 130)
    for pos in range(start, idx):
        d = rows[pos]["date"]
        if d not in returns or d not in factors.index:
            continue
        factor_row = factors.loc[d]
        needed = model_cols + ["RF"]
        if any(pd.isna(factor_row.get(col)) for col in needed):
            continue
        y = returns[d] - float(factor_row["RF"])
        x = [float(factor_row[col]) for col in model_cols]
        regression_rows.append((y, x))
    if len(regression_rows) < max(40, len(model_cols) * 10):
        return None
    y = np.array([row[0] for row in regression_rows])
    x = np.array([[1.0] + row[1] for row in regression_rows])
    try:
        params = np.linalg.lstsq(x, y, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    window_dates = [rows[pos]["date"] for pos in range(idx + 1, idx + horizon + 1)]
    if any(d not in factors.index for d in window_dates):
        return None
    window = factors.loc[window_dates]
    needed = model_cols + ["RF"]
    if window[needed].isna().any().any():
        return None
    rf_sum = float(window["RF"].sum())
    factor_sums = np.array([float(window[col].sum()) for col in model_cols])
    expected_excess = float(params[0] * horizon + np.dot(params[1:], factor_sums))
    return rf_sum + expected_excess


def event_alpha_rows(events: list[base.EventRecord], factors: pd.DataFrame) -> list[dict[str, Any]]:
    market = base.load_market_data()
    stock_returns = daily_stock_returns(market)
    model_specs = {
        "SPY_adjusted": [],
        "FF3": ["Mkt-RF", "SMB", "HML"],
        "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
        "Carhart": ["Mkt-RF", "SMB", "HML", "MOM"],
    }
    rows = []
    for event in events:
        for horizon, stock_field, spy_field in (
            (1, "stock_return_1d", "ar_1d"),
            (5, "stock_return_5d", "ar_5d"),
        ):
            stock_return = getattr(event, stock_field)
            if stock_return is None:
                continue
            for model, cols in model_specs.items():
                if model == "SPY_adjusted":
                    alpha = getattr(event, spy_field)
                    status = "computed"
                elif not all(col in factors.columns for col in cols + ["RF"]):
                    alpha = None
                    status = "missing_factor_columns"
                else:
                    expected = fit_expected_return(event, horizon, cols, market, stock_returns, factors)
                    alpha = None if expected is None else stock_return - expected
                    status = "computed" if alpha is not None else "insufficient_estimation_window"
                rows.append(
                    {
                        "event_id": event.event_id,
                        "ticker": event.ticker,
                        "creator": event.creator,
                        "recommendation_type": event.recommendation_type,
                        "event_date": event.event_date.isoformat() if event.event_date else "",
                        "horizon": f"{horizon}D",
                        "model": model,
                        "alpha": base.fmt(alpha),
                        "top5_flag": event.ticker in base.TOP5_TICKERS,
                        "low_lookahead_flag": event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS,
                        "duplicate_cluster_id": event.duplicate_cluster_id,
                        "status": status,
                    }
                )
    return rows


def summarize(rows: pd.DataFrame) -> list[dict[str, Any]]:
    if rows.empty:
        return []
    sec_flags_path = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
    sec_clean_ids: set[int] = set()
    if sec_flags_path.exists():
        sec = pd.read_csv(sec_flags_path)
        sec_clean_ids = set(sec.loc[sec["sec_clean_flag"].astype(bool), "event_id"].astype(int))
    out = []
    for sample, predicate in {
        "all": lambda df: df.index == df.index,
        "top5": lambda df: df["top5_flag"].astype(bool),
        "non_top": lambda df: ~df["top5_flag"].astype(bool),
        "low_lookahead": lambda df: df["low_lookahead_flag"].astype(bool),
        "duplicate_collapsed": lambda df: ~df.duplicated("duplicate_cluster_id"),
        "sec_clean": lambda df: df["event_id"].astype(int).isin(sec_clean_ids),
        "buy_only": lambda df: df["recommendation_type"].eq("buy"),
        "sell_only": lambda df: df["recommendation_type"].eq("sell"),
    }.items():
        selected = rows[predicate(rows)]
        for (model, horizon), group in selected.groupby(["model", "horizon"]):
            values = [float(v) for v in group["alpha"] if str(v) not in {"", "nan"}]
            stats = base.t_test(values)
            se = None
            if stats["n"] and stats["n"] > 1:
                se = statistics_stdev(values) / math.sqrt(int(stats["n"]))
            out.append(
                {
                    "sample": sample,
                    "model": model,
                    "horizon": horizon,
                    "n": stats["n"],
                    "mean_alpha": base.fmt(stats["mean"]),
                    "standard_error": base.fmt(se),
                    "t_stat": base.fmt(stats["t"], 3),
                    "p_value": base.fmt(stats["p"], 6),
                    "notes": "factor-adjusted event alpha; free Kenneth French daily factors",
                }
            )
    return out


def statistics_stdev(values: list[float]) -> float:
    return float(pd.Series(values).std(ddof=1))


def main() -> int:
    factors, status_rows = load_factors()
    base.write_csv(FACTOR_DIR / "01_v2_factor_data_status.csv", status_rows, ["factor_set", "status", "rows"])
    base.write_md(
        FACTOR_DIR / "01_v2_factor_data_status.md",
        "# V2 Factor Data Status\n\n" + base.markdown_table(status_rows, ["factor_set", "status", "rows"]),
    )
    events = base.fetch_events(base.load_market_data())
    rows = event_alpha_rows(events, factors) if not factors.empty else []
    columns = [
        "event_id", "ticker", "creator", "recommendation_type", "event_date", "horizon",
        "model", "alpha", "top5_flag", "low_lookahead_flag", "duplicate_cluster_id", "status",
    ]
    base.write_csv(FACTOR_DIR / "02_v2_factor_adjusted_event_returns.csv", rows, columns)
    summary = summarize(pd.DataFrame(rows)) if rows else []
    summary_columns = [
        "sample", "model", "horizon", "n", "mean_alpha", "standard_error",
        "t_stat", "p_value", "notes",
    ]
    base.write_csv(FACTOR_DIR / "03_v2_factor_adjusted_alpha_table.csv", summary, summary_columns)
    base.write_md(
        FACTOR_DIR / "03_v2_factor_adjusted_alpha_table.md",
        "# V2 Factor-Adjusted Alpha Table\n\n" + base.markdown_table(summary, summary_columns),
    )
    top5 = next(
        (r for r in summary if r["sample"] == "top5" and r["model"] == "FF5" and r["horizon"] == "5D"),
        None,
    )
    non_top = next(
        (r for r in summary if r["sample"] == "non_top" and r["model"] == "FF5" and r["horizon"] == "5D"),
        None,
    )
    interpretation = f"""# V2 Factor Interpretation

Factor adjustment uses free Kenneth French daily factors downloaded in memory.
No paid data, WRDS, Bloomberg, or `.env` inputs are used.

- FF5 top-5 5D alpha: `{top5['mean_alpha'] if top5 else 'not available'}` with p=`{top5['p_value'] if top5 else ''}`.
- FF5 non-top 5D alpha: `{non_top['mean_alpha'] if non_top else 'not available'}` with p=`{non_top['p_value'] if non_top else ''}`.

Interpretation should follow the table: if factor adjustment reduces the
top-5 estimate or leaves non-top negative, the paper should frame the finding as
attention concentration rather than broad alpha.
"""
    base.write_md(FACTOR_DIR / "04_v2_factor_interpretation.md", interpretation)
    print(f"V2 factor alpha complete: event_alpha_rows={len(rows)} summary_rows={len(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
