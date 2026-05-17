"""Shared helpers for information-environment / analyst-relay / sentiment layers."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402, I001
import v2_critical_defense_utils as utils  # noqa: E402, I001
CONFIG_DIR = Path(os.environ.get("FIN496_CONFIG_DIR", "/root/.config/fin496"))
INFO_ENV = utils.OUT_DIR / "information_environment"
DB_PATH = REPO_ROOT / "data" / "finfluencer_alpha.db"
COMPACT_CACHE = INFO_ENV / "analyst_relay" / "_analyst_compact_cache.csv"
USER_AGENT = "fin496-information-environment/1.0"


def info_dir(name: str) -> Path:
    path = INFO_ENV / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_api_key(env_name: str) -> tuple[str | None, str]:
    """Load API key from environment or FIN496 config file. Never log the value."""
    value = os.environ.get(env_name, "").strip()
    if value:
        return value, "environment"
    cfg = CONFIG_DIR / f"{env_name.lower()}.env"
    if not cfg.exists():
        return None, "missing"
    for line in cfg.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{env_name}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                os.environ[env_name] = value
                return value, "config_file"
    return None, "missing"


def http_json(url: str, timeout: int = 25) -> tuple[Any | None, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), "ok"
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except urllib.error.URLError:
        return None, "network_error"
    except (json.JSONDecodeError, TimeoutError):
        return None, "parse_error"


def parse_iso_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return pd.to_datetime(value, errors="coerce").date()
    except (TypeError, ValueError):
        return None


def narrative_relay_scores(text: str) -> dict[str, int]:
    """Keyword counts on evidence snippets only (no full transcript export)."""
    t = (text or "").lower()
    base_scores = {
        "analyst_relay_score": sum(
            1
            for k in [
                "analyst",
                "wall street",
                "upgrade",
                "downgrade",
                "price target",
                "consensus",
                "outperform",
                "underperform",
                "initiated coverage",
            ]
            if k in t
        ),
        "earnings_relay_score": sum(
            1
            for k in ["earnings", "eps", "guidance", "quarter", "call", "revenue beat", "revenue miss"]
            if k in t
        ),
        "news_relay_score": sum(
            1
            for k in [
                "report",
                "announcement",
                "lawsuit",
                "partnership",
                "fda",
                "merger",
                "acquisition",
                "headline",
            ]
            if k in t
        ),
        "market_move_relay_score": sum(
            1
            for k in [
                "stock is up",
                "stock is down",
                "rallied",
                "sold off",
                "dropped",
                "breakout",
                "all-time high",
                "52-week",
            ]
            if k in t
        ),
        "retail_hype_score": sum(
            1
            for k in ["moon", "explode", "10x", "millionaire", "next tesla", "squeeze", "to the moon", "100x"]
            if k in t
        ),
        "urgency_score": sum(
            1
            for k in ["buy now", "before it is too late", "don't miss", "dont miss", "act fast", "last chance"]
            if k in t
        ),
        "valuation_score": sum(
            1
            for k in ["dcf", "cash flow", "multiple", "margin", "fair value", "valuation", "pe ratio", "free cash flow"]
            if k in t
        ),
        "technical_score": sum(
            1
            for k in ["chart", "breakout", "support", "resistance", "rsi", "moving average", "macd"]
            if k in t
        ),
        "risk_score": sum(
            1 for k in ["risk", "downside", "overvalued", "uncertainty", "volatile", "could lose"] if k in t
        ),
        "disclosure_score": sum(
            1 for k in ["i own", "my position", "sponsor", "affiliate", "paid", "disclosure"] if k in t
        ),
    }
    return base_scores


def load_evidence_text() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame(columns=["event_id", "evidence_window"])
    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute(
            """
            SELECT transcript_event_id AS event_id, evidence_window
            FROM transcript_recommendation_events
            WHERE evidence_window IS NOT NULL AND TRIM(evidence_window) <> ''
            """
        ).fetchall()
    except sqlite3.Error:
        rows = []
    con.close()
    return pd.DataFrame(rows, columns=["event_id", "evidence_window"])


def spy_benchmark_series() -> pd.DataFrame:
    """Daily SPY proxy from any ticker row with benchmark prices."""
    rows: list[dict[str, Any]] = []
    for _ticker, series in base.load_market_data().items():
        for row in series:
            d = base.parse_date(row.get("date"))
            bench = base.safe_float(row.get("benchmark_adjusted_close"))
            if d and bench is not None:
                rows.append({"date": d, "spy_close": bench})
    if not rows:
        return pd.DataFrame(columns=["date", "spy_close"])
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    df["spy_return_1d"] = df["spy_close"].pct_change()
    return df


def vix_proxy_series() -> pd.DataFrame:
    """VIX level from public CSV if reachable; else SPY-realized-vol proxy."""
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    # CBOE publishes CSV (not JSON)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        from io import StringIO

        vix = pd.read_csv(StringIO(raw))
        date_col = next((c for c in vix.columns if "date" in c.lower()), vix.columns[0])
        close_col = next((c for c in vix.columns if "close" in c.lower() or "SETTLE" in c.upper()), None)
        if close_col is None and len(vix.columns) > 1:
            close_col = vix.columns[-1]
        vix["date"] = pd.to_datetime(vix[date_col], errors="coerce").dt.date
        vix["vix_level"] = pd.to_numeric(vix[close_col], errors="coerce")
        out = vix.dropna(subset=["date", "vix_level"])[["date", "vix_level"]].drop_duplicates("date")
        out["vix_source"] = "cboe_csv"
        return out
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        spy = spy_benchmark_series()
        if spy.empty:
            return pd.DataFrame(columns=["date", "vix_level", "vix_source"])
        spy = spy.copy()
        spy["vix_level"] = spy["spy_return_1d"].rolling(21, min_periods=10).std() * np.sqrt(252) * 100
        spy["vix_source"] = "spy_realized_vol_proxy"
        return spy[["date", "vix_level", "vix_source"]].dropna(subset=["vix_level"])


def features_on_date(
    as_of: date,
    spy: pd.DataFrame,
    vix: pd.DataFrame,
    qqq: pd.DataFrame | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"as_of": as_of.isoformat()}
    spy_hist = spy[spy["date"] <= as_of].tail(126)
    if len(spy_hist) < 22:
        return row
    spy_close = spy_hist["spy_close"].astype(float)
    row["spy_prior_21d_return"] = float(spy_close.iloc[-1] / spy_close.iloc[-22] - 1) if len(spy_close) >= 22 else None
    row["spy_prior_63d_return"] = float(spy_close.iloc[-1] / spy_close.iloc[-64] - 1) if len(spy_close) >= 64 else None
    hi63 = spy_close.tail(63).max() if len(spy_close) >= 63 else spy_close.max()
    row["spy_drawdown_from_63d_high"] = float(spy_close.iloc[-1] / hi63 - 1) if hi63 else None
    if qqq is not None and not qqq.empty:
        qqq_hist = qqq[qqq["date"] <= as_of].tail(126)
        if len(qqq_hist) >= 22:
            qc = qqq_hist["qqq_close"].astype(float)
            row["qqq_prior_21d_return"] = float(qc.iloc[-1] / qc.iloc[-22] - 1)
            row["qqq_prior_63d_return"] = float(qc.iloc[-1] / qc.iloc[-64] - 1) if len(qc) >= 64 else None
            hiq = qc.tail(63).max() if len(qc) >= 63 else qc.max()
            row["qqq_drawdown_from_63d_high"] = float(qc.iloc[-1] / hiq - 1) if hiq else None
    vix_hist = vix[vix["date"] <= as_of].tail(252)
    if not vix_hist.empty:
        vl = vix_hist["vix_level"].astype(float)
        row["vix_level"] = float(vl.iloc[-1])
        row["vix_percentile_1y"] = float((vl <= vl.iloc[-1]).mean()) if len(vl) > 20 else None
        if len(vl) >= 6:
            row["vix_change_5d"] = float(vl.iloc[-1] - vl.iloc[-6])
        if len(vl) >= 22:
            row["vix_change_21d"] = float(vl.iloc[-1] - vl.iloc[-22])
    # Regime labels (conditioning only)
    spy21 = row.get("spy_prior_21d_return")
    vix_lvl = row.get("vix_level")
    if spy21 is not None and vix_lvl is not None:
        if spy21 > 0.02 and vix_lvl < 20:
            row["sentiment_regime"] = "risk_on"
        elif spy21 < -0.03 or (vix_lvl and vix_lvl > 25):
            row["sentiment_regime"] = "risk_off"
        else:
            row["sentiment_regime"] = "neutral"
    return row


def qqq_series() -> pd.DataFrame:
    """QQQ proxy: use NVDA benchmark rows won't work — try ticker QQQ in market data."""
    data = base.load_market_data().get("QQQ") or base.load_market_data().get("qqq")
    if not data:
        return pd.DataFrame(columns=["date", "qqq_close"])
    rows = []
    for row in data:
        d = base.parse_date(row.get("date"))
        c = base.safe_float(row.get("adjusted_close"))
        if d and c is not None:
            rows.append({"date": d, "qqq_close": c})
    return pd.DataFrame(rows).drop_duplicates("date").sort_values("date")


def summarize_returns_by_bucket(
    panel: pd.DataFrame,
    bucket_col: str,
    out_csv: Path,
    out_md: Path,
    title: str,
    horizon: str = "21D",
) -> list[dict[str, Any]]:
    sub = panel[panel["horizon"] == horizon].copy() if "horizon" in panel.columns else panel.copy()
    rows: list[dict[str, Any]] = []
    for bucket, grp in sub.groupby(bucket_col, dropna=False):
        stats = utils.t_stats([float(x) for x in grp["spy_bhar"].dropna()])
        rows.append(
            {
                "bucket": str(bucket),
                "horizon": horizon,
                "n": stats["n"],
                "mean_spy_bhar": stats["mean"],
                "t_stat": stats["t_stat"],
                "p_value": stats["p_value"],
                "win_rate": stats["win_rate"],
            }
        )
    utils.write_csv(out_csv, rows, list(rows[0]) if rows else ["bucket"])
    utils.write_md(out_md, title, utils.md_table(rows))
    return rows
