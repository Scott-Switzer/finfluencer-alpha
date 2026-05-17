from __future__ import annotations

import csv
import hashlib
import math
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
LONG_DIR = OUT_DIR / "long_horizon"
LONG_PANEL = LONG_DIR / "01_v2_long_horizon_event_returns.csv"
EVENT_MANIFEST = OUT_DIR / "locked_sample_v2" / "02_v2_event_manifest.csv"
SEC_FLAGS = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
HORIZONS = ["5D", "21D", "63D", "126D", "252D"]
TOP5 = {"NVDA", "TSLA", "AAPL", "AMD", "AMZN"}


def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def clean_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def t_stats(values: list[float]) -> dict[str, Any]:
    clean = [float(v) for v in values if clean_float(v) is not None]
    n = len(clean)
    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "standard_error": None,
            "median": None,
            "t_stat": None,
            "p_value": None,
            "win_rate": None,
        }
    mean = statistics.mean(clean)
    median = statistics.median(clean)
    win_rate = sum(v > 0 for v in clean) / n
    if n < 2:
        return {
            "n": n,
            "mean": mean,
            "standard_error": None,
            "median": median,
            "t_stat": None,
            "p_value": None,
            "win_rate": win_rate,
        }
    sd = statistics.stdev(clean)
    se = sd / math.sqrt(n) if sd else 0.0
    t_stat = mean / se if se else None
    p_value = None if t_stat is None else 2.0 * (1.0 - normal_cdf(abs(t_stat)))
    return {
        "n": n,
        "mean": mean,
        "standard_error": se,
        "median": median,
        "t_stat": t_stat,
        "p_value": p_value,
        "win_rate": win_rate,
    }


def fmt(value: Any, digits: int = 6) -> str:
    out = clean_float(value)
    if out is None:
        return ""
    return f"{out:.{digits}f}"


def fmt_pct(value: Any, digits: int = 3) -> str:
    out = clean_float(value)
    if out is None:
        return ""
    return f"{100.0 * out:.{digits}f}%"


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    ensure_dir(path)
    if columns is None:
        columns = list(rows[0]) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def md_table(rows: list[dict[str, Any]], columns: list[str] | None = None, limit: int = 80) -> str:
    if not rows:
        rows = [{"status": "no_rows"}]
    if columns is None:
        columns = list(rows[0])
    out = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows[:limit]:
        out.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(out)


def write_md(path: Path, title: str, body: str) -> None:
    ensure_dir(path)
    path.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")


def table_pair(base_path: Path, rows: list[dict[str, Any]], title: str, columns: list[str] | None = None) -> None:
    write_csv(base_path.with_suffix(".csv"), rows, columns)
    write_md(base_path.with_suffix(".md"), title, md_table(rows, columns))


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def long_panel() -> pd.DataFrame:
    frame = pd.read_csv(LONG_PANEL)
    for col in ["event_id", "requested_horizon_days", "spy_bhar", "spy_car", "raw_return"]:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def forward_panel(horizons: list[str] | None = None) -> pd.DataFrame:
    horizons = horizons or HORIZONS
    frame = long_panel()
    return frame[(frame["window_type"] == "forward") & frame["horizon"].isin(horizons)].copy()


def event_manifest() -> pd.DataFrame:
    return pd.read_csv(EVENT_MANIFEST)


def sec_flags() -> pd.DataFrame:
    if SEC_FLAGS.exists():
        return pd.read_csv(SEC_FLAGS)
    return pd.DataFrame()


def event_records() -> list[base.EventRecord]:
    return base.fetch_events(base.load_market_data())


def sample_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    all_mask = pd.Series(True, index=frame.index)
    top5 = frame["top5_flag"].astype(str).str.lower().eq("true")
    out = {
        "all": all_mask,
        "top5": top5,
        "non_top": ~top5,
        "buy": frame["recommendation_type"].astype(str).eq("buy"),
        "sell": frame["recommendation_type"].astype(str).eq("sell"),
        "low_lookahead": frame["low_lookahead_flag"].astype(str).str.lower().eq("true"),
        "duplicate_collapsed": frame["duplicate_collapsed_flag"].astype(str).str.lower().eq("true"),
    }
    if "sec_clean_flag" in frame.columns:
        out["sec_clean"] = frame["sec_clean_flag"].astype(str).str.lower().eq("true")
        out["sec_confounded"] = frame["sec_confounded_flag"].astype(str).str.lower().eq("true")
    return out


def summarize_return_panel(
    frame: pd.DataFrame,
    value_col: str = "spy_bhar",
    masks: dict[str, pd.Series] | None = None,
    horizons: list[str] | None = None,
) -> list[dict[str, Any]]:
    horizons = horizons or HORIZONS
    masks = masks or sample_masks(frame)
    rows: list[dict[str, Any]] = []
    for sample, mask in masks.items():
        selected = frame[mask]
        for horizon in horizons:
            group = selected[(selected["horizon"] == horizon) & (selected["status"] == "computed")]
            stats = t_stats(group[value_col].dropna().astype(float).tolist())
            right_censored = 0
            if "right_censored" in group.columns:
                right_censored = int(group["right_censored"].astype(str).str.lower().eq("true").sum())
            rows.append(
                {
                    "sample": sample,
                    "horizon": horizon,
                    "return_type": value_col,
                    "n": stats["n"],
                    "mean": fmt(stats["mean"]),
                    "mean_pct": fmt_pct(stats["mean"]),
                    "standard_error": fmt(stats["standard_error"]),
                    "median": fmt(stats["median"]),
                    "t_stat": fmt(stats["t_stat"], 3),
                    "p_value": fmt(stats["p_value"], 6),
                    "win_rate": fmt(stats["win_rate"]),
                    "right_censored": right_censored,
                }
            )
    return rows


def safe_hash(*parts: Any) -> str:
    joined = "|".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def winsorize(values: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    clean = values.dropna()
    if clean.empty:
        return values
    lo = clean.quantile(lower)
    hi = clean.quantile(upper)
    return values.clip(lo, hi)


def ols(y: np.ndarray, x: np.ndarray) -> dict[str, Any]:
    mask = np.isfinite(y) & np.isfinite(x).all(axis=1)
    y = y[mask]
    x = x[mask]
    n = len(y)
    if n <= x.shape[1]:
        return {"status": "insufficient_observations"}
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    resid = y - x @ beta
    dof = max(n - x.shape[1], 1)
    sigma2 = float((resid @ resid) / dof)
    try:
        cov = sigma2 * np.linalg.inv(x.T @ x)
    except np.linalg.LinAlgError:
        return {"status": "singular_design"}
    se = np.sqrt(np.diag(cov))
    tvals = beta / se
    pvals = [2.0 * (1.0 - normal_cdf(abs(float(t)))) for t in tvals]
    ss_tot = float((y - y.mean()) @ (y - y.mean()))
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot else None
    return {"status": "computed", "beta": beta, "se": se, "t": tvals, "p": pvals, "r2": r2, "n": n}


def bh_q_values(p_values: list[float | None]) -> list[float | None]:
    indexed = [(idx, float(p)) for idx, p in enumerate(p_values) if p is not None and not math.isnan(float(p))]
    if not indexed:
        return [None for _ in p_values]
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    q: list[float | None] = [None for _ in p_values]
    running = 1.0
    for rank, (idx, p) in reversed(list(enumerate(indexed, start=1))):
        running = min(running, p * m / rank)
        q[idx] = running
    return q


def simple_markdown_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
