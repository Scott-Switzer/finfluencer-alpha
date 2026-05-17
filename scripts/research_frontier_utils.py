"""Shared helpers for research-frontier mechanism and robustness scripts."""

from __future__ import annotations

import random
import sqlite3
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
import build_v2_long_horizon_returns as lh  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR
FRONTIER = OUT_DIR / "research_frontier"
DB_PATH = REPO_ROOT / "data" / "finfluencer_alpha.db"
MARKET_DATA = REPO_ROOT / "data" / "imports" / "market_data" / "yfinance_market_data.csv"
RNG = random.Random(496)
PRE_HORIZONS = [1, 5, 21, 63, 126]
POST_HORIZONS = [1, 5, 21, 63]


def frontier_dir(name: str) -> Path:
    path = FRONTIER / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_market_with_volume() -> dict[str, pd.DataFrame]:
    frames = lh.market_frames()
    if not MARKET_DATA.exists():
        return frames
    vol_map: dict[tuple[str, date], float] = {}
    cap_map: dict[tuple[str, date], float] = {}
    import csv

    with MARKET_DATA.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").upper().strip()
            d = base.parse_date(row.get("date"))
            if not ticker or d is None:
                continue
            vol = base.safe_float(row.get("volume"))
            cap = base.safe_float(row.get("market_cap"))
            if vol is not None:
                vol_map[(ticker, d)] = vol
            if cap is not None:
                cap_map[(ticker, d)] = cap
    out: dict[str, pd.DataFrame] = {}
    for ticker, frame in frames.items():
        f = frame.copy()
        f["volume"] = [vol_map.get((ticker, d), np.nan) for d in f["date"]]
        f["market_cap"] = [cap_map.get((ticker, d), np.nan) for d in f["date"]]
        f["dollar_volume"] = f["volume"] * f["adjusted_close"]
        f["volume_ma21"] = f["volume"].rolling(21, min_periods=5).mean()
        f["abnormal_volume"] = f["volume"] / f["volume_ma21"] - 1.0
        out[ticker] = f
    return out


def bhar_at(frame: pd.DataFrame, idx: int, start_off: int, end_off: int) -> float | None:
    m = lh.window_metrics(frame, idx, idx + start_off, idx + end_off, allow_right_censor=False)
    return lh.clean_float(m.get("spy_bhar")) if m.get("status") == "computed" else None


def pre_features(frame: pd.DataFrame, idx: int) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for h in PRE_HORIZONS:
        row[f"prior_return_{h}d"] = bhar_at(frame, idx, -h, 0)
    pre = frame.iloc[max(0, idx - 21) : idx + 1]
    rets = [lh.clean_float(x) for x in pre["daily_stock_return"].tolist() if lh.clean_float(x) is not None]
    row["prior_volatility_21d"] = float(np.std(rets)) if len(rets) > 1 else None
    row["prior_max_drawdown_21d"] = lh.max_drawdown([float(x) for x in pre["adjusted_close"].tolist()])
    if idx > 0 and "abnormal_volume" in frame.columns:
        av = lh.clean_float(frame.iloc[idx - 1].get("abnormal_volume"))
        row["prior_abnormal_volume"] = av
        row["prior_market_cap"] = lh.clean_float(frame.iloc[idx - 1].get("market_cap"))
    else:
        row["prior_abnormal_volume"] = None
        row["prior_market_cap"] = None
    return row


def post_features(frame: pd.DataFrame, idx: int) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for h in POST_HORIZONS:
        m = lh.window_metrics(frame, idx, idx, idx + h, allow_right_censor=False)
        row[f"post_bhar_{h}d"] = lh.clean_float(m.get("spy_bhar"))
        row[f"post_vol_{h}d"] = lh.clean_float(m.get("realized_volatility"))
        row[f"post_raw_ret_{h}d"] = lh.clean_float(m.get("raw_return"))
    if idx + 1 < len(frame):
        hi = frame.iloc[idx + 1]["adjusted_close"]
        lo = frame.iloc[idx + 1]["adjusted_close"]
        if "high" in frame.columns:
            hi = frame.iloc[idx + 1].get("high", hi)
            lo = frame.iloc[idx + 1].get("low", lo)
        row["post_1d_range_pct"] = (float(hi) / float(lo) - 1.0) if lo else None
    return row


def build_event_feature_table() -> pd.DataFrame:
    events = utils.event_records()
    frames = load_market_with_volume()
    manifest = utils.event_manifest()
    if not manifest.empty and "event_id" in manifest.columns:
        manifest = manifest.copy()
        manifest["_event_id_key"] = manifest["event_id"].astype(str)
    panel = utils.forward_panel(["5D", "21D", "63D"]).drop_duplicates(subset=["event_id", "horizon"])
    panel = panel.copy()
    panel["_event_id_key"] = panel["event_id"].astype(str)
    pivot = panel.pivot_table(index="_event_id_key", columns="horizon", values="spy_bhar", aggfunc="first")
    rows: list[dict[str, Any]] = []
    event_positions: dict[str, set[int]] = {}
    for event in events:
        if event.return_exclusion_reason or event.effective_trading_event_date is None:
            continue
        frame = frames.get(event.data_ticker)
        idx = lh.first_idx(frame, event.effective_trading_event_date) if frame is not None else None
        if idx is None or frame is None:
            continue
        event_positions.setdefault(event.data_ticker, set()).add(idx)
        event_key = str(event.event_id)
        quality = None
        if "_event_id_key" in manifest.columns:
            quality_rows = manifest.loc[manifest["_event_id_key"] == event_key, "quality_score"]
            quality = quality_rows.iloc[0] if not quality_rows.empty else None
        feat = {
            "event_id": event.event_id,
            "ticker": event.ticker,
            "data_ticker": event.data_ticker,
            "creator": event.creator,
            "event_date": event.effective_trading_event_date.isoformat(),
            "event_year": event.effective_trading_event_date.year,
            "recommendation_type": event.recommendation_type,
            "top5_flag": event.ticker in utils.TOP5,
            "confidence_score": event.confidence_score,
            "confidence_label": event.confidence_label,
            "quality_score": quality,
            "high_confidence": (event.confidence_score or 0) >= 0.7
            or str(event.confidence_label).lower() in {"high", "very_high"},
            "event_idx": idx,
        }
        feat.update(pre_features(frame, idx))
        feat.update(post_features(frame, idx))
        for h in ["5D", "21D", "63D"]:
            if h in pivot.columns and event_key in pivot.index:
                feat[f"forward_spy_bhar_{h.lower()}"] = lh.clean_float(pivot.loc[event_key, h])
        rows.append(feat)
    df = pd.DataFrame(rows)
    if not manifest.empty and "_event_id_key" in manifest.columns:
        included = manifest[manifest["included_in_v2_event_study"].astype(str).str.lower().eq("true")].copy()
        existing = set(df["event_id"].astype(str)) if not df.empty and "event_id" in df.columns else set()
        supplemental: list[dict[str, Any]] = []
        for _, item in included.iterrows():
            event_key = str(item.get("event_id"))
            if event_key in existing:
                continue
            event_date = item.get("effective_trading_event_date") or item.get("event_date")
            parsed_event_date = utils.parse_date(event_date)
            feat = {
                "event_id": item.get("event_id"),
                "ticker": item.get("ticker"),
                "data_ticker": item.get("ticker"),
                "creator": item.get("creator"),
                "event_date": parsed_event_date.isoformat() if parsed_event_date else event_date,
                "event_year": parsed_event_date.year if parsed_event_date else None,
                "recommendation_type": item.get("recommendation_type"),
                "top5_flag": str(item.get("ticker")).upper() in utils.TOP5,
                "confidence_score": None,
                "confidence_label": "",
                "quality_score": item.get("quality_score"),
                "high_confidence": False,
                "event_idx": None,
                "manifest_supplement_only": True,
            }
            for h in ["5D", "21D", "63D"]:
                if h in pivot.columns and event_key in pivot.index:
                    feat[f"forward_spy_bhar_{h.lower()}"] = lh.clean_float(pivot.loc[event_key, h])
            supplemental.append(feat)
        if supplemental:
            df = pd.concat([df, pd.DataFrame(supplemental)], ignore_index=True)
        included_keys = set(included["_event_id_key"].astype(str))
        if included_keys and "event_id" in df.columns:
            df = df[df["event_id"].astype(str).isin(included_keys)].copy()
    if df.empty:
        return df
    conf = utils.read_csv(OUT_DIR / "confounds_expanded" / "01_v2_master_confound_panel_expanded.csv")
    if not conf.empty and "event_id" in conf.columns:
        keep = [c for c in conf.columns if c.startswith("master_") or c.startswith("public_") or c.startswith("av_")]
        df = df.merge(conf[["event_id"] + keep], on="event_id", how="left")
    return df


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


def language_scores(text: str) -> dict[str, int]:
    t = (text or "").lower()
    hype_kw = ["millionaire", "moon", "explode", "10x", "100x", "undervalued", "next tesla", "to the moon", "rocket"]
    risk_kw = ["risk", "downside", "valuation", "uncertainty", "not financial advice", "could lose", "volatile"]
    disc_kw = ["i own", "my position", "sponsor", "affiliate", "disclosure", "paid promotion"]
    fund_kw = ["dcf", "cash flow", "margin", "earnings", "revenue", "multiple", "pe ratio", "free cash flow"]
    tech_kw = ["support", "resistance", "breakout", "chart", "moving average", "rsi", "macd"]
    urg_kw = ["buy now", "before it's too late", "dont miss", "don't miss", "act fast", "last chance"]
    amb_kw = ["watchlist", "keeping an eye", "might consider", "thinking about", "on my radar"]
    return {
        "hype_score": sum(1 for k in hype_kw if k in t),
        "risk_warning_score": sum(1 for k in risk_kw if k in t),
        "disclosure_score": sum(1 for k in disc_kw if k in t),
        "valuation_score": sum(1 for k in fund_kw if k in t),
        "technical_score": sum(1 for k in tech_kw if k in t),
        "urgency_score": sum(1 for k in urg_kw if k in t),
        "ambiguity_score": sum(1 for k in amb_kw if k in t),
        "text_len": len(t),
    }


def run_ols(y: pd.Series, x: pd.DataFrame, label: str) -> dict[str, Any]:
    data = pd.concat([y.rename("y"), x], axis=1).dropna()
    if len(data) < max(30, x.shape[1] + 5):
        return {"spec": label, "status": "insufficient_n", "n": len(data)}
    yv = data["y"].astype(float).values
    xv = np.column_stack([np.ones(len(data)), data[x.columns].astype(float).values])
    res = utils.ols(yv, xv)
    if res.get("status") != "computed":
        return {"spec": label, "status": res.get("status", "failed"), "n": len(data)}
    names = ["intercept"] + list(x.columns)
    out: dict[str, Any] = {"spec": label, "status": "computed", "n": res["n"], "r2": res.get("r2")}
    for i, name in enumerate(names):
        out[f"coef_{name}"] = float(res["beta"][i])
        out[f"t_{name}"] = float(res["t"][i])
        out[f"p_{name}"] = float(res["p"][i])
    return out


def placebo_indices(
    frame: pd.DataFrame,
    event_idx: int,
    event_positions: set[int],
    shifts: list[int] | None = None,
    n_random: int = 3,
) -> list[tuple[str, int]]:
    shifts = shifts or [-90, -60, -30, 30, 60, 90]
    out: list[tuple[str, int]] = []
    for s in shifts:
        pos = event_idx + s
        if 22 <= pos < len(frame) - 63 and pos not in event_positions:
            out.append((f"shift_{s:+d}", pos))
    valid = [p for p in range(22, len(frame) - 63) if p not in event_positions]
    if valid:
        for i, pos in enumerate(RNG.sample(valid, min(n_random, len(valid)))):
            out.append((f"random_placebo_{i}", pos))
    return out
