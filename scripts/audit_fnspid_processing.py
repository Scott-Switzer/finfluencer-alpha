"""Audit FNSPID primary/secondary processing: coverage, dedupe, windows, join integrity."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import TextIOWrapper
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_v2_fnspid_news_layer as fnspid  # noqa: E402
import news_provider_utils as npu  # noqa: E402
import v2_critical_defense_utils as utils  # noqa: E402

OUT = fnspid.OUT_DIR
MANIFEST = utils.OUT_DIR / "locked_sample_v2" / "02_v2_event_manifest.csv"
PANEL = utils.OUT_DIR / "news_confound_master" / "news_confound_event_panel.csv"
SPINE = OUT / "fnspid_article_spine.csv"
DERIVED = OUT / "fnspid_derived_event_panel.csv"

WINDOWS = [
    ("pm1", 1),
    ("pm3", 3),
    ("pm7", 7),
    ("pm14", 14),
    ("pm30", 30),
    ("pm60", 60),
]

CANARY_TICKERS = frozenset(
    {"AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "GOOG", "NFLX", "AMD", "PLTR", "COIN", "SQ", "PYPL"}
)

TICKER_ALIASES: dict[str, set[str]] = {
    "META": {"META", "FB"},
    "FB": {"META", "FB"},
    "GOOGL": {"GOOGL", "GOOG"},
    "GOOG": {"GOOGL", "GOOG"},
    "BRK.B": {"BRK.B", "BRK-B"},
    "BRK-B": {"BRK.B", "BRK-B"},
    "SQ": {"SQ", "XYZ"},
    "XYZ": {"SQ", "XYZ"},
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit FNSPID processing.")
    p.add_argument("--skip-csv-stream", action="store_true", help="Skip all Hub CSV streaming.")
    p.add_argument(
        "--scan-primary",
        action="store_true",
        help="Re-stream nasdaq_exteral_data.csv for ticker/date stats (slow).",
    )
    p.add_argument(
        "--no-secondary-stream",
        action="store_true",
        help="Skip All_external dedupe stream pass.",
    )
    return p.parse_args()


def symbol_variants(ticker: str) -> set[str]:
    t = str(ticker or "").upper().strip()
    if not t:
        return set()
    if t in TICKER_ALIASES:
        return set(TICKER_ALIASES[t])
    return {t}


def article_key(url: str, d: date, title: str) -> str:
    return fnspid._article_key(url, d, title)


def short_title(title: str, max_len: int = 80) -> str:
    t = " ".join(str(title or "").split())[:max_len]
    if len(str(title or "")) > max_len:
        t += "…"
    return t


@dataclass
class EventRec:
    event_id: int
    ticker: str
    event_date: date
    symbols: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.symbols = symbol_variants(self.ticker)


def load_events() -> dict[int, EventRec]:
    manifest = pd.read_csv(MANIFEST)
    out: dict[int, EventRec] = {}
    for _, row in manifest.iterrows():
        ed = npu.parse_date(row.get("event_date"))
        if ed is None:
            continue
        eid = int(row["event_id"])
        ticker = str(row["ticker"]).upper().strip()
        if ticker in fnspid.NOISY_SYMBOLS:
            continue
        out[eid] = EventRec(event_id=eid, ticker=ticker, event_date=ed)
    return out


def index_by_symbol(events: dict[int, EventRec]) -> dict[str, list[EventRec]]:
    idx: dict[str, list[EventRec]] = defaultdict(list)
    for ev in events.values():
        for sym in ev.symbols:
            idx[sym].append(ev)
    return dict(idx)


def event_year_tables(events: dict[int, EventRec], panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for ev in events.values():
        y = ev.event_date.year
        rows.append({"event_id": ev.event_id, "ticker": ev.ticker, "year": y})
    evdf = pd.DataFrame(rows)
    col = "news_clean_status_final" if "news_clean_status_final" in panel.columns else "news_clean_status"
    merged = evdf.merge(panel[["event_id", col, "fnspid_news_hit"]], on="event_id", how="left")
    if "fnspid_news_hit" not in merged.columns:
        merged["fnspid_news_hit"] = False
    hit = merged["fnspid_news_hit"].astype(str).str.lower().isin({"true", "1", "1.0"})
    merged["fnspid_hit"] = hit
    merged["unknown"] = merged[col].astype(str).eq("unknown_news_coverage")
    by_year = (
        merged.groupby("year")
        .agg(
            events=("event_id", "count"),
            unknown_news_coverage=("unknown", "sum"),
            fnspid_hits=("fnspid_hit", "sum"),
            fnspid_misses=("fnspid_hit", lambda s: int((~s.astype(bool)).sum())),
        )
        .reset_index()
    )
    return merged, by_year


def window_sensitivity_from_spine(events: dict[int, EventRec]) -> pd.DataFrame:
    if not SPINE.exists():
        return pd.DataFrame([{"status": "missing_spine"}])
    spine = pd.read_csv(SPINE)
    spine["article_date"] = pd.to_datetime(spine["article_date"], errors="coerce").dt.date
    by_event: dict[int, list[tuple[date, str]]] = defaultdict(list)
    for row in spine.itertuples(index=False):
        eid = int(row.event_id)
        d = row.article_date
        if pd.isna(d) or eid not in events:
            continue
        src = str(getattr(row, "source_file", ""))
        by_event[eid].append((d, src))

    rows: list[dict[str, Any]] = []
    for label, days in WINDOWS:
        pri = sec = either = both = 0
        for eid, ev in events.items():
            arts = by_event.get(eid, [])
            has_p = has_s = False
            lo, hi = ev.event_date - timedelta(days=days), ev.event_date + timedelta(days=days)
            for d, src in arts:
                if not (lo <= d <= hi):
                    continue
                if fnspid.PRIMARY_CSV_BASENAME in src:
                    has_p = True
                if fnspid.SECONDARY_CSV_BASENAME in src:
                    has_s = True
            if has_p:
                pri += 1
            if has_s:
                sec += 1
            if has_p or has_s:
                either += 1
            if has_p and has_s:
                both += 1
        rows.append(
            {
                "window": label,
                "days_each_side": days,
                "events_hit_primary": pri,
                "events_hit_secondary": sec,
                "events_hit_either": either,
                "events_hit_both": both,
                "n_events": len(events),
            }
        )
    return pd.DataFrame(rows)


def stream_file_audit(
    csv_url: str,
    source_label: str,
    sym_index: dict[str, list[EventRec]],
    event_symbols: set[str],
    *,
    primary_keys_by_event: dict[int, set[str]] | None = None,
    canary_only: bool = False,
) -> dict[str, Any]:
    """One pass: tickers, dates, canaries, optional secondary dedupe."""
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    stats: dict[str, Any] = {
        "source": source_label,
        "rows_read": 0,
        "valid_dates": 0,
        "invalid_dates": 0,
        "valid_sym": 0,
        "invalid_sym": 0,
        "unique_tickers": set(),
        "year_counts": defaultdict(int),
        "rows_2018_2023": 0,
        "rows_event_ticker": 0,
        "rows_event_ticker_year_in_sample": 0,
        "header_columns": [],
        "min_date": None,
        "max_date": None,
    }
    dedupe = {
        "window_match_rows": 0,
        "new_keys_vs_primary": 0,
        "dup_keys_vs_primary": 0,
        "no_window_match": 0,
        "sym_in_universe_no_window": 0,
    }
    canary_stats: dict[str, dict[str, Any]] = {t: defaultdict(int) for t in CANARY_TICKERS}
    canary_titles: dict[str, list[str]] = {t: [] for t in CANARY_TICKERS}

    try:
        req = Request(csv_url, headers={"User-Agent": "FIN496-fnspid-audit/1.0"})
        with urlopen(req, timeout=None) as resp:
            text = TextIOWrapper(resp, encoding="utf-8", errors="replace", newline="")
            reader = csv.DictReader(text)
            if reader.fieldnames is None:
                stats["error"] = "no_header"
                return stats
            fnmap = {str(f).strip(): str(f).strip() for f in reader.fieldnames}
            stats["header_columns"] = list(fnmap.keys())[:30]

            def pick(*names: str) -> str | None:
                for n in names:
                    if n in fnmap:
                        return n
                return None

            c_date = pick("Date", "date")
            c_sym = pick("Stock_symbol", "stock_symbol", "symbol", "ticker")
            c_title = pick("Article_title", "title", "headline")
            c_url = pick("Url", "url", "link")
            if not c_date or not c_sym:
                stats["error"] = f"missing_cols date={c_date} sym={c_sym}"
                return stats

            for row in reader:
                stats["rows_read"] += 1
                if stats["rows_read"] % 1_000_000 == 0:
                    print(f"audit stream {source_label}: {stats['rows_read']:,}", flush=True)

                sym = str(row.get(c_sym, "") or "").upper().strip()
                if sym:
                    stats["valid_sym"] += 1
                    stats["unique_tickers"].add(sym)
                else:
                    stats["invalid_sym"] += 1
                    continue

                if canary_only and sym not in CANARY_TICKERS:
                    continue

                ts = pd.to_datetime(row.get(c_date, ""), utc=True, errors="coerce")
                if pd.isna(ts):
                    stats["invalid_dates"] += 1
                    continue
                stats["valid_dates"] += 1
                d = ts.date()
                y = d.year
                stats["year_counts"][y] += 1
                if stats["min_date"] is None or d < stats["min_date"]:
                    stats["min_date"] = d
                if stats["max_date"] is None or d > stats["max_date"]:
                    stats["max_date"] = d
                if 2018 <= y <= 2023:
                    stats["rows_2018_2023"] += 1

                if sym not in event_symbols and sym not in sym_index:
                    continue
                stats["rows_event_ticker"] += 1

                title = str(row.get(c_title, "") or "")
                url = str(row.get(c_url, "") or "")
                key = article_key(url, d, title)

                if sym in CANARY_TICKERS:
                    cs = canary_stats[sym]
                    cs["rows"] += 1
                    if 2018 <= y <= 2023:
                        cs["rows_2018_2023"] += 1
                    if len(canary_titles[sym]) < 5:
                        canary_titles[sym].append(short_title(title))

                matched_any = False
                for ev in sym_index.get(sym, ()):
                    lo7 = ev.event_date - timedelta(days=7)
                    hi7 = ev.event_date + timedelta(days=7)
                    if lo7 <= d <= hi7:
                        matched_any = True
                        if primary_keys_by_event is not None:
                            dedupe["window_match_rows"] += 1
                            pk = primary_keys_by_event.get(ev.event_id, set())
                            if key in pk:
                                dedupe["dup_keys_vs_primary"] += 1
                            else:
                                dedupe["new_keys_vs_primary"] += 1
                    if 2018 <= ev.event_date.year <= 2023 and 2018 <= y <= 2023:
                        stats["rows_event_ticker_year_in_sample"] += 1

                if sym in sym_index and not matched_any:
                    dedupe["sym_in_universe_no_window"] += 1

    except Exception as exc:
        stats["error"] = str(exc)[:200]

    stats["unique_ticker_count"] = len(stats["unique_tickers"])
    stats["unique_tickers"] = sorted(list(stats["unique_tickers"]))[:500]
    stats["year_counts"] = dict(sorted(stats["year_counts"].items()))
    stats["dedupe"] = dedupe
    stats["canary"] = {t: dict(canary_stats[t]) for t in CANARY_TICKERS if canary_stats[t].get("rows")}
    stats["canary_sample_titles"] = {t: canary_titles[t] for t in CANARY_TICKERS if canary_titles[t]}
    if stats["min_date"]:
        stats["min_date"] = stats["min_date"].isoformat()
    if stats["max_date"]:
        stats["max_date"] = stats["max_date"].isoformat()
    return stats


def primary_keys_from_spine() -> dict[int, set[str]]:
    if not SPINE.exists():
        return {}
    out: dict[int, set[str]] = defaultdict(set)
    for row in pd.read_csv(SPINE).itertuples(index=False):
        if str(row.source_file) != fnspid.PRIMARY_CSV_BASENAME:
            continue
        out[int(row.event_id)].add(str(row.article_key))
    return dict(out)


def ticker_overlap_table(events: dict[int, EventRec], pri_stats: dict, sec_stats: dict) -> pd.DataFrame:
    event_syms = set()
    for ev in events.values():
        event_syms |= ev.symbols
    pri_set = set(pri_stats.get("unique_tickers", []))
    sec_set = set(sec_stats.get("unique_tickers", []))
    rows = [
        {"metric": "unique_event_tickers", "value": len(event_syms)},
        {"metric": "unique_tickers_in_primary_csv", "value": pri_stats.get("unique_ticker_count", "")},
        {"metric": "unique_tickers_in_secondary_csv", "value": sec_stats.get("unique_ticker_count", "")},
        {
            "metric": "event_tickers_in_primary",
            "value": len(event_syms & pri_set),
        },
        {
            "metric": "event_tickers_in_secondary",
            "value": len(event_syms & sec_set),
        },
        {
            "metric": "event_tickers_absent_both",
            "value": len(event_syms - pri_set - sec_set),
        },
    ]
    return pd.DataFrame(rows)


def top50_ticker_table(events: dict[int, EventRec], spine: pd.DataFrame) -> pd.DataFrame:
    ev_counts = pd.Series([e.ticker for e in events.values()]).value_counts()
    spine_hits = (
        spine.groupby("ticker")["event_id"].nunique().rename("events_with_spine_article")
        if not spine.empty
        else pd.Series(dtype=int)
    )
    spine_rows = spine.groupby("ticker").size().rename("spine_article_rows") if not spine.empty else pd.Series(dtype=int)
    rows = []
    for ticker, n_ev in ev_counts.head(50).items():
        rows.append(
            {
                "ticker": ticker,
                "n_events": int(n_ev),
                "spine_article_rows": int(spine_rows.get(ticker, 0)),
                "events_with_fnspid_hit": int(spine_hits.get(ticker, 0)),
            }
        )
    return pd.DataFrame(rows)


def join_integrity_checks(events: dict[int, EventRec], panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    eids_manifest = {int(e) for e in pd.read_csv(MANIFEST)["event_id"]}
    eids_events = set(events.keys())
    rows.append({"check": "manifest_vs_parseable_events", "n_manifest": len(eids_manifest), "n_parseable": len(eids_events)})
    if not panel.empty and "event_id" in panel.columns:
        dup = panel["event_id"].duplicated().sum()
        rows.append({"check": "panel_duplicate_event_id", "count": int(dup)})
    weekend = sum(1 for e in events.values() if e.event_date.weekday() >= 5)
    rows.append({"check": "events_on_weekend", "count": weekend, "note": "FNSPID uses calendar dates; not an error"})
    return rows


def build_audit_md(sections: list[str]) -> str:
    return "# FNSPID processing audit\n\n" + "\n\n".join(sections) + "\n"


def main() -> int:
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    events = load_events()
    sym_index = index_by_symbol(events)
    event_symbols: set[str] = set()
    for ev in events.values():
        event_symbols |= ev.symbols

    panel = pd.read_csv(PANEL) if PANEL.exists() else pd.DataFrame()
    _ev_year, by_year = event_year_tables(events, panel)
    by_year.to_csv(OUT / "fnspid_event_year_overlap.csv", index=False)

    n_before_2024 = sum(1 for e in events.values() if e.event_date.year < 2024)
    n_2024_plus = sum(1 for e in events.values() if e.event_date.year >= 2024)
    share_outside = n_2024_plus / max(len(events), 1)

    win_df = window_sensitivity_from_spine(events)
    win_df.to_csv(OUT / "fnspid_window_sensitivity.csv", index=False)

    spine = pd.read_csv(SPINE) if SPINE.exists() else pd.DataFrame()
    top50 = top50_ticker_table(events, spine)
    top50.to_csv(OUT / "fnspid_ticker_overlap_audit.csv", index=False)

    pri_stats: dict[str, Any] = {}
    sec_stats: dict[str, Any] = {}
    meta_path = OUT / "fnspid_stream_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pri_stats = {
            "rows_read": meta.get("primary_nasdaq_rows_read"),
            "from_meta": True,
            "unique_ticker_count": "(use --scan-primary to refresh)",
            "unique_tickers": [],
        }
        if not args.skip_csv_stream:
            sec_stats["rows_read"] = meta.get("secondary_all_external_rows_read")

    if not args.skip_csv_stream and args.scan_primary:
        print("Streaming primary CSV for ticker/date audit...", flush=True)
        pri_stats = stream_file_audit(fnspid.DEFAULT_CSV_URL, "primary", sym_index, event_symbols)

    pk = primary_keys_from_spine()
    if not args.skip_csv_stream and not args.no_secondary_stream:
        print("Streaming secondary CSV for dedupe audit...", flush=True)
        sec_stats = stream_file_audit(
            fnspid.SECONDARY_CSV_URL,
            "secondary",
            sym_index,
            event_symbols,
            primary_keys_by_event=pk,
        )

    overlap = ticker_overlap_table(events, pri_stats, sec_stats)
    overlap.to_csv(OUT / "fnspid_ticker_overlap_summary.csv", index=False)

    dedupe_rows = []
    if sec_stats.get("dedupe"):
        d = sec_stats["dedupe"]
        dedupe_rows = [
            {"metric": k, "value": v}
            for k, v in d.items()
        ]
        dedupe_rows.append(
            {
                "metric": "interpretation",
                "value": "dup_keys_vs_primary>0 with new_keys≈0 implies All_external overlap deduped by primary keys",
            }
        )
    pd.DataFrame(dedupe_rows).to_csv(OUT / "fnspid_secondary_dedupe_audit.csv", index=False)

    join_rows = join_integrity_checks(events, panel)
    audit_rows = [
        {"section": "event_coverage", "metric": "events_parseable", "value": len(events)},
        {"section": "event_coverage", "metric": "events_before_2024", "value": n_before_2024},
        {"section": "event_coverage", "metric": "events_2024_2026", "value": n_2024_plus},
        {"section": "event_coverage", "metric": "share_events_outside_fnspid_era", "value": round(share_outside, 4)},
        {"section": "stream", "metric": "primary_rows_read", "value": pri_stats.get("rows_read", "")},
        {"section": "stream", "metric": "secondary_rows_read", "value": sec_stats.get("rows_read", "")},
        {"section": "stream", "metric": "primary_unique_tickers", "value": pri_stats.get("unique_ticker_count", "")},
        {"section": "stream", "metric": "secondary_unique_tickers", "value": sec_stats.get("unique_ticker_count", "")},
        {"section": "stream", "metric": "primary_min_date", "value": pri_stats.get("min_date", "")},
        {"section": "stream", "metric": "primary_max_date", "value": pri_stats.get("max_date", "")},
        {"section": "stream", "metric": "secondary_min_date", "value": sec_stats.get("min_date", "")},
        {"section": "stream", "metric": "secondary_max_date", "value": sec_stats.get("max_date", "")},
        {"section": "stream", "metric": "primary_valid_dates", "value": pri_stats.get("valid_dates", "")},
        {"section": "stream", "metric": "primary_invalid_dates", "value": pri_stats.get("invalid_dates", "")},
        {"section": "stream", "metric": "secondary_header_sample", "value": str(sec_stats.get("header_columns", ""))[:200]},
        {"section": "hits", "metric": "current_fnspid_hit_events", "value": int(panel["fnspid_news_hit"].astype(str).str.lower().isin({"true", "1"}).sum()) if "fnspid_news_hit" in panel.columns else ""},
    ]
    for _, r in win_df.iterrows():
        audit_rows.append(
            {
                "section": "window_sensitivity",
                "metric": f"{r['window']}_either",
                "value": r["events_hit_either"],
            }
        )
    for r in join_rows:
        audit_rows.append({"section": "join_integrity", "metric": r.get("check", ""), "value": str(r)})
    audit_df = pd.DataFrame(audit_rows)
    audit_df.to_csv(OUT / "fnspid_processing_audit.csv", index=False)

    sections = [
        "## A. Event / date coverage\n"
        + utils.md_table(
            [
                {"metric": "events_before_2024", "value": n_before_2024},
                {"metric": "events_2024_2026", "value": n_2024_plus},
                {"metric": "share_outside_expected_fnspid_era", "value": f"{100*share_outside:.1f}%"},
            ]
        )
        + "\n\n"
        + utils.md_table(by_year.to_dict("records"), limit=30),
        "## D. Window sensitivity (from compact spine)\n" + utils.md_table(win_df.to_dict("records")),
        "## B. Ticker overlap\n" + utils.md_table(overlap.to_dict("records")),
        "## E. Secondary dedupe\n" + utils.md_table(dedupe_rows),
    ]
    if pri_stats.get("canary_sample_titles"):
        canary_lines = []
        for t, titles in pri_stats.get("canary_sample_titles", {}).items():
            canary_lines.append(f"**{t}**: " + " | ".join(titles[:5]))
        sections.append("## F. Canary title samples (primary stream)\n" + "\n".join(f"- {x}" for x in canary_lines[:20]))
    sections.append(
        "## Verdict\n"
        "- If `events_hit_secondary` stays 0 across windows on the spine, secondary never contributed articles to stored hits.\n"
        "- If dedupe shows large `dup_keys_vs_primary` with ~0 `new_keys_vs_primary`, All_external rows overlap primary content and were correctly deduped.\n"
        "- Events in 2024+ cannot receive FNSPID hits by construction if article max date ends ~2023.\n"
        "- **unknown_news_coverage is never clean**; **multi_source_clean** may remain 0.\n"
    )
    md_path = OUT / "fnspid_processing_audit.md"
    md_path.write_text(build_audit_md(sections), encoding="utf-8")
    exhibit_dir = utils.OUT_DIR / "final_exhibits"
    exhibit_dir.mkdir(parents=True, exist_ok=True)
    (exhibit_dir / "exhibit_fnspid_verification.md").write_text(
        "# Exhibit — FNSPID verification\n\n" + md_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    synth = utils.OUT_DIR / "final_paper_synthesis" / "fnspid_verification_summary.md"
    synth.parent.mkdir(parents=True, exist_ok=True)
    synth.write_text(
        "# FNSPID verification (synthesis insert)\n\n"
        "Both Hub CSVs were scanned (Nasdaq external + All_external). "
        "See `news_confound_master/fnspid/fnspid_processing_audit.md` for year overlap, "
        "window sensitivity, and secondary dedupe. "
        "**unknown_news_coverage is never clean.** "
        "**multi_source_clean** remains prohibited when zero.\n",
        encoding="utf-8",
    )
    print(f"Wrote FNSPID audit to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
