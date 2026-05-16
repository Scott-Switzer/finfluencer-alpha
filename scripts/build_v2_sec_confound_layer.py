from __future__ import annotations

import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
SEC_DIR = OUT_DIR / "sec"
SEC_DIR.mkdir(parents=True, exist_ok=True)

SEC_USER_AGENT = "Scott Switzer scott@example.com FIN496 academic research"
SEC_FORMS_MATERIAL = {
    "8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A", "S-1", "S-1/A",
    "424B", "424B1", "424B2", "424B3", "424B4", "424B5", "DEF 14A",
}
FALLBACK_CIK = {
    "AAPL": "0000320193",
    "AMC": "0001411579",
    "AMD": "0000002488",
    "AMZN": "0001018724",
    "COIN": "0001679788",
    "CRM": "0001108524",
    "DIS": "0001744489",
    "GME": "0001326380",
    "GOOGL": "0001652044",
    "HOOD": "0001783879",
    "META": "0001326801",
    "MSFT": "0000789019",
    "NFLX": "0001065280",
    "NVDA": "0001045810",
    "PLTR": "0001321655",
    "PYPL": "0001633917",
    "ROKU": "0001428439",
    "SHOP": "0001594801",
    "SMCI": "0001375365",
    "SOFI": "0001818874",
    "SQ": "0001512673",
    "TGT": "0000027419",
    "TSLA": "0001318605",
    "UBER": "0001543151",
    "XYZ": "0001512673",
}


def sec_get_json(url: str) -> tuple[dict[str, Any] | None, str]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=30,
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if response.status_code != 200:
        return None, f"http_{response.status_code}"
    try:
        return response.json(), "ok"
    except ValueError as exc:
        return None, f"json_error: {exc}"


def build_ticker_cik_map(tickers: set[str]) -> tuple[dict[str, str], str]:
    payload, status = sec_get_json("https://www.sec.gov/files/company_tickers.json")
    mapping = FALLBACK_CIK.copy()
    if payload:
        for item in payload.values():
            ticker = str(item.get("ticker") or "").upper()
            cik = str(item.get("cik_str") or "").zfill(10)
            if ticker:
                mapping[ticker] = cik
    return {ticker: mapping[ticker] for ticker in tickers if ticker in mapping}, status


def submissions_for_cik(cik: str) -> tuple[list[dict[str, Any]], str]:
    payload, status = sec_get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    time.sleep(0.15)
    if not payload:
        return [], status
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accession = recent.get("accessionNumber", [])
    rows = []
    for idx, form in enumerate(forms):
        filing_date = base.parse_date(dates[idx] if idx < len(dates) else "")
        if filing_date is None:
            continue
        rows.append(
            {
                "filing_date": filing_date,
                "form_type": str(form or ""),
                "accession_number": accession[idx] if idx < len(accession) else "",
            }
        )
    return rows, status


def event_window_counts(
    event_date: date | None,
    filings: list[dict[str, Any]],
) -> dict[str, Any]:
    if event_date is None:
        return {
            "filing_count_pm1": 0,
            "filing_count_pm3": 0,
            "filing_count_pm5": 0,
            "material_filing_flag_pm1": False,
            "material_filing_flag_pm3": False,
            "material_filing_flag_pm5": False,
            "material_form_types": "",
            "nearest_filing_date": "",
            "nearest_form_type": "",
        }
    out: dict[str, Any] = {}
    material_forms: set[str] = set()
    nearest = None
    for filing in filings:
        delta = abs((filing["filing_date"] - event_date).days)
        if nearest is None or delta < nearest[0]:
            nearest = (delta, filing)
        if delta <= 5 and filing["form_type"] in SEC_FORMS_MATERIAL:
            material_forms.add(filing["form_type"])
    for window in (1, 3, 5):
        window_filings = [
            filing for filing in filings if abs((filing["filing_date"] - event_date).days) <= window
        ]
        out[f"filing_count_pm{window}"] = len(window_filings)
        out[f"material_filing_flag_pm{window}"] = any(
            filing["form_type"] in SEC_FORMS_MATERIAL for filing in window_filings
        )
    out["material_form_types"] = ";".join(sorted(material_forms))
    out["nearest_filing_date"] = nearest[1]["filing_date"].isoformat() if nearest else ""
    out["nearest_form_type"] = nearest[1]["form_type"] if nearest else ""
    return out


def stats_row(name: str, events: list[base.EventRecord], notes: str = "") -> dict[str, Any]:
    return base.spec_row(name, events, notes)


def build_event_study(events: list[base.EventRecord], flags: pd.DataFrame) -> None:
    flag_map = flags.set_index("event_id")

    def select(predicate) -> list[base.EventRecord]:
        out = []
        for event in events:
            row = flag_map.loc[event.event_id]
            if predicate(event, row):
                out.append(event)
        return out

    all_events = events
    sec_clean = select(lambda _event, row: bool(row["sec_clean_flag"]))
    sec_confounded = select(lambda _event, row: bool(row["sec_confounded_flag"]))
    clean_top5 = select(lambda event, row: bool(row["sec_clean_flag"]) and event.ticker in base.TOP5_TICKERS)
    clean_non_top = select(
        lambda event, row: bool(row["sec_clean_flag"]) and event.ticker not in base.TOP5_TICKERS
    )
    clean_low = select(
        lambda event, row: bool(row["sec_clean_flag"]) and event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS
    )
    clean_collapsed_ids = {event.event_id for event in base.first_per_cluster(sec_clean)}
    clean_collapsed = [event for event in sec_clean if event.event_id in clean_collapsed_ids]
    rows = [
        stats_row("v2 all", all_events, "all accepted/extracted events"),
        stats_row("v2 SEC-clean", sec_clean, "full v2 SEC submissions metadata refresh"),
        stats_row("v2 SEC-confounded", sec_confounded, "material SEC filing within +/-5 calendar days"),
        stats_row("v2 SEC-clean top-5", clean_top5, ""),
        stats_row("v2 SEC-clean non-top", clean_non_top, ""),
        stats_row("v2 low-lookahead + SEC-clean", clean_low, ""),
        stats_row("v2 duplicate-collapsed + SEC-clean", clean_collapsed, ""),
    ]
    columns = list(rows[0])
    base.write_csv(SEC_DIR / "04_v2_sec_clean_event_study.csv", rows, columns)
    base.write_md(
        SEC_DIR / "04_v2_sec_clean_event_study.md",
        "# V2 SEC-Clean Event Study\n\n"
        + base.markdown_table(rows, columns)
        + "\n\nSEC flags use compact company submissions metadata only; no filing bodies are downloaded.",
    )


def write_workplan() -> None:
    text = """# V2 Maximum Empirical Defense Workplan

## Current V2 State

V2 is the expanded live RunPod sample: 9,992 transcript rows, 2,341 accepted
recommendation events, 35 creators, 24 tickers, and 2,299 5-day return-matched
events. The full-sample 5-day abnormal return is near zero and insignificant,
while top-5 mega-cap momentum tickers remain positive and non-top tickers are
negative.

## Already Computed

- V2 compact transcript and event manifests.
- V1 vs V2 event bridge.
- SPY-adjusted headline event-study tables.
- Timing, duplicate, top-5/non-top, buy/sell, creator, and ticker summaries.

## Missing Before This Pass

- Full v2 SEC refresh.
- Factor-adjusted alpha.
- Falsification, placebo, matched-control, and pretrend diagnostics.
- Clustered/robust inference.
- Portfolio and transaction-cost diagnostics.
- Creator/ticker deep dives.
- Quality sensitivity.
- Real free-news probe.
- Revised narrative centered on v2.

## Why V2 Becomes Primary

V2 should become primary because it is the most complete manifest-backed sample
available in the RunPod database, not because it gives a stronger result. It
weakens the earlier v1 broad-alpha interpretation, which is a valid and
important empirical update.

## Thesis Shift

The paper should shift from broad YouTube alpha to attention amplification
concentrated in top mega-cap momentum tickers, with non-top recommendations
underperforming or reversing. Causality and tradable alpha remain unproven.

## Task List

1. Full v2 SEC refresh.
2. Factor-adjusted alpha.
3. Placebo, permutation, and falsification tests.
4. Pre-trend and post-event decay.
5. Matched controls.
6. Clustered inference.
7. Creator/ticker heterogeneity.
8. Portfolio construction and transaction costs.
9. Quality/confidence sensitivity.
10. Revised narrative and professor defense.
"""
    base.write_md(OUT_DIR / "19_v2_maximum_defense_workplan.md", text)


def main() -> int:
    write_workplan()
    market = base.load_market_data()
    events = base.fetch_events(market)
    tickers = {event.ticker for event in events}
    mapping, mapping_status = build_ticker_cik_map(tickers | {"XYZ"})
    filings_by_ticker: dict[str, list[dict[str, Any]]] = {}
    provider_rows = []
    for ticker in sorted(tickers):
        cik = mapping.get("XYZ" if ticker == "SQ" else ticker) or mapping.get(ticker)
        if not cik:
            provider_rows.append(
                {
                    "ticker": ticker,
                    "cik": "",
                    "query_status": "missing_cik",
                    "filing_rows": 0,
                    "notes": "ticker not found in SEC mapping",
                }
            )
            filings_by_ticker[ticker] = []
            continue
        filings, status = submissions_for_cik(cik)
        filings_by_ticker[ticker] = filings
        provider_rows.append(
            {
                "ticker": ticker,
                "cik": cik,
                "query_status": status,
                "filing_rows": len(filings),
                "notes": f"ticker map status={mapping_status}",
            }
        )
    base.write_csv(SEC_DIR / "01_v2_sec_provider_status.csv", provider_rows, list(provider_rows[0]))
    base.write_md(
        SEC_DIR / "01_v2_sec_provider_status.md",
        "# V2 SEC Provider Status\n\n" + base.markdown_table(provider_rows, list(provider_rows[0])),
    )

    flag_rows = []
    for event in events:
        event_date = event.event_date
        window_counts = event_window_counts(event_date, filings_by_ticker.get(event.ticker, []))
        sec_confounded = bool(window_counts["material_filing_flag_pm5"])
        reason_codes = []
        if not provider_rows:
            reason_codes.append("provider_status_missing")
        if sec_confounded:
            reason_codes.append("material_filing_pm5")
        if not filings_by_ticker.get(event.ticker):
            reason_codes.append("no_filings_or_missing_cik")
        flag_rows.append(
            {
                "event_id": event.event_id,
                "ticker": event.ticker,
                "company_name": event.company_name,
                "event_date": event_date.isoformat() if event_date else "",
                "window_pm1": "[-1,+1] calendar days",
                "window_pm3": "[-3,+3] calendar days",
                "window_pm5": "[-5,+5] calendar days",
                **window_counts,
                "sec_confounded_flag": sec_confounded,
                "sec_clean_flag": not sec_confounded,
                "query_status": "ok" if filings_by_ticker.get(event.ticker) else "missing_or_empty",
                "reason_codes": ";".join(reason_codes),
            }
        )
    columns = [
        "event_id",
        "ticker",
        "company_name",
        "event_date",
        "window_pm1",
        "window_pm3",
        "window_pm5",
        "filing_count_pm1",
        "filing_count_pm3",
        "filing_count_pm5",
        "material_filing_flag_pm1",
        "material_filing_flag_pm3",
        "material_filing_flag_pm5",
        "material_form_types",
        "nearest_filing_date",
        "nearest_form_type",
        "sec_confounded_flag",
        "sec_clean_flag",
        "query_status",
        "reason_codes",
    ]
    base.write_csv(SEC_DIR / "02_v2_sec_event_flags.csv", flag_rows, columns)
    flags = pd.DataFrame(flag_rows)
    base.write_md(
        SEC_DIR / "02_v2_sec_event_flags.md",
        "# V2 SEC Event Flags\n\n"
        + base.markdown_table(flag_rows[:25], columns)
        + "\n\nPreview only; full compact metadata is in the CSV.",
    )
    clean = int(flags["sec_clean_flag"].sum())
    confounded = int(flags["sec_confounded_flag"].sum())
    form_counter = Counter(
        form
        for value in flags["material_form_types"].dropna().astype(str)
        for form in value.split(";")
        if form
    )
    summary = f"""# V2 SEC Summary

- Events audited: `{len(flags)}`
- SEC-clean events: `{clean}`
- SEC-confounded events: `{confounded}`
- Provider rows: `{len(provider_rows)}`
- Material form types: `{dict(form_counter.most_common())}`

This pass uses official SEC submissions metadata and stores only compact filing
counts/forms/dates. It does not download filing bodies.
"""
    base.write_md(SEC_DIR / "03_v2_sec_summary.md", summary)
    build_event_study(events, flags)
    print(f"V2 SEC refresh complete: events={len(flags)} clean={clean} confounded={confounded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
