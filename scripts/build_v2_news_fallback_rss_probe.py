from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
FALLBACK_DIR = OUT_DIR / "news_fallback"
FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
RNG = random.Random(496)


def write_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    base.write_md(
        path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(rows[:80], columns)
    )


def trunc(text: Any, limit: int = 120) -> str:
    return str(text or "").replace("\n", " ").replace("\r", " ")[:limit]


def yfinance_news(ticker: str) -> dict[str, Any]:
    try:
        import yfinance as yf
    except Exception as exc:
        return {
            "status": "package_unavailable",
            "error_class": type(exc).__name__,
            "article_count": 0,
        }
    try:
        news = yf.Ticker(ticker).news or []
    except Exception as exc:
        return {"status": "query_failed", "error_class": type(exc).__name__, "article_count": 0}
    titles = []
    domains = []
    for item in news[:10]:
        content = item.get("content") if isinstance(item, dict) else {}
        title = item.get("title") or content.get("title") if isinstance(item, dict) else ""
        url = (
            item.get("link") or content.get("canonicalUrl", {}).get("url", "")
            if isinstance(item, dict)
            else ""
        )
        if title:
            titles.append(trunc(title, 90))
        domain = urlparse(url).netloc.replace("www.", "")
        if domain:
            domains.append(domain)
    return {
        "status": "ok",
        "error_class": "",
        "article_count": len(news),
        "top_domains": ";".join(sorted(set(domains))[:5]),
        "top_titles_truncated": " || ".join(titles[:3]),
    }


def main() -> int:
    events = base.fetch_events(base.load_market_data())
    candidates = sorted(events, key=lambda e: abs(e.ar_5d or 0), reverse=True)[:80]
    selected = RNG.sample(candidates, min(30, len(candidates))) if candidates else []
    provider_rows = [
        {
            "provider": "yfinance_ticker_news_metadata",
            "status": "attempted",
            "article_body_storage": "none",
        }
    ]
    flag_rows = []
    cache: dict[str, dict[str, Any]] = {}
    for event in selected:
        cache.setdefault(event.ticker, yfinance_news(event.ticker))
        result = cache[event.ticker]
        flag_rows.append(
            {
                "event_id": event.event_id,
                "ticker": event.ticker,
                "company_name": event.company_name,
                "event_date": event.event_date.isoformat() if event.event_date else "",
                "provider": "yfinance_ticker_news_metadata",
                "query_status": result.get("status", ""),
                "article_count": result.get("article_count", 0),
                "top_domains": result.get("top_domains", ""),
                "top_titles_truncated": result.get("top_titles_truncated", ""),
                "error_class": result.get("error_class", ""),
                "coverage_status": "weak_metadata_only_not_event_date_specific",
            }
        )
    write_table(
        FALLBACK_DIR / "01_fallback_news_provider_status",
        provider_rows,
        "Fallback News Provider Status",
    )
    write_table(
        FALLBACK_DIR / "02_fallback_news_probe_flags", flag_rows, "Fallback News Probe Flags"
    )
    df = pd.DataFrame(flag_rows)
    ok = int(df["query_status"].eq("ok").sum()) if not df.empty else 0
    text = f"""# Fallback News Interpretation

The fallback pass uses only compact yfinance ticker-news metadata when available.
It is not event-date-specific and does not replace a real GDELT or professional
news-control layer.

- Probe events: `{len(df)}`
- Successful metadata queries: `{ok}`
- Article bodies stored: `0`

Use this only as a weak provider-feasibility diagnostic. It is not empirical
public-news exclusion evidence.
"""
    base.write_md(FALLBACK_DIR / "03_fallback_news_interpretation.md", text)
    print(f"V2 fallback news probe complete: events={len(df)} ok={ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
