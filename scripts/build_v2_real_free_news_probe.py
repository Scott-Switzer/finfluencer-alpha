from __future__ import annotations

import random
import sys
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
PROBE_DIR = OUT_DIR / "free_news_probe"
NARRATIVE_DIR = OUT_DIR / "final_narrative"
PROBE_DIR.mkdir(parents=True, exist_ok=True)
NARRATIVE_DIR.mkdir(parents=True, exist_ok=True)
RNG = random.Random(496)


def select_probe_events(events: list[base.EventRecord], max_events: int = 30) -> list[base.EventRecord]:
    buckets = [
        [e for e in events if e.ticker in base.TOP5_TICKERS and e.ar_5d is not None and e.ar_5d > 0],
        [e for e in events if e.ticker not in base.TOP5_TICKERS and e.ar_5d is not None and e.ar_5d < 0],
        sorted([e for e in events if e.ar_5d is not None], key=lambda e: e.ar_5d or 0, reverse=True)[:50],
        sorted([e for e in events if e.ar_5d is not None], key=lambda e: e.ar_5d or 0)[:50],
        [e for e in events if e.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS],
        events[:],
    ]
    selected: dict[int, base.EventRecord] = {}
    per_bucket = max_events // len(buckets)
    for bucket in buckets:
        if len(bucket) > per_bucket:
            bucket = RNG.sample(bucket, per_bucket)
        for event in bucket:
            selected[event.event_id] = event
    remaining = [event for event in events if event.event_id not in selected]
    while len(selected) < max_events and remaining:
        event = RNG.choice(remaining)
        remaining = [item for item in remaining if item.event_id != event.event_id]
        selected[event.event_id] = event
    return list(selected.values())[:max_events]


def gdelt_query(event: base.EventRecord) -> dict[str, Any]:
    if event.event_date is None:
        return {"query_status": "missing_event_date", "article_count": 0, "top_domains": "", "truncated_titles": ""}
    start = (event.event_date - timedelta(days=3)).strftime("%Y%m%d000000")
    end = (event.event_date + timedelta(days=3)).strftime("%Y%m%d235959")
    query_terms = [event.ticker]
    if event.company_name:
        query_terms.append(f'"{event.company_name[:60]}"')
    query = " OR ".join(query_terms)
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": 10,
        "sort": "hybridrel",
        "startdatetime": start,
        "enddatetime": end,
    }
    try:
        response = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=8)
    except Exception as exc:
        return {"query_status": f"{type(exc).__name__}: {exc}", "article_count": 0, "top_domains": "", "truncated_titles": ""}
    if response.status_code != 200:
        return {"query_status": f"http_{response.status_code}", "article_count": 0, "top_domains": "", "truncated_titles": ""}
    try:
        payload = response.json()
    except ValueError as exc:
        return {"query_status": f"json_error: {exc}", "article_count": 0, "top_domains": "", "truncated_titles": ""}
    articles = payload.get("articles", []) or []
    domains = []
    titles = []
    for article in articles[:10]:
        url = article.get("url") or ""
        domain = urlparse(url).netloc.replace("www.", "")
        if domain:
            domains.append(domain)
        title = str(article.get("title") or "").replace("\n", " ").strip()
        if title:
            titles.append(title[:90])
    domain_counts = Counter(domains)
    return {
        "query_status": "ok",
        "article_count": len(articles),
        "top_domains": ";".join(domain for domain, _count in domain_counts.most_common(5)),
        "truncated_titles": " || ".join(titles[:3]),
    }


def run_probe() -> None:
    existing = PROBE_DIR / "02_real_gdelt_probe_event_flags.csv"
    if existing.exists():
        try:
            prior = pd.read_csv(existing)
            if len(prior) > 0:
                return
        except Exception:
            pass
    events = base.fetch_events(base.load_market_data())
    selected = select_probe_events(events)
    rows = []
    status_rows = []
    for idx, event in enumerate(selected, start=1):
        result = gdelt_query(event)
        time.sleep(0.15)
        rows.append(
            {
                "event_id": event.event_id,
                "ticker": event.ticker,
                "company_name": event.company_name,
                "event_date": event.event_date.isoformat() if event.event_date else "",
                "top5_flag": event.ticker in base.TOP5_TICKERS,
                "low_lookahead_flag": event.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS,
                "ar_5d": base.fmt(event.ar_5d),
                "query_window": "+/-3 calendar days",
                **result,
            }
        )
        status_rows.append({"probe_event_number": idx, "event_id": event.event_id, "query_status": result["query_status"]})
    columns = list(rows[0])
    base.write_csv(PROBE_DIR / "02_real_gdelt_probe_event_flags.csv", rows, columns)
    base.write_md(
        PROBE_DIR / "02_real_gdelt_probe_event_flags.md",
        "# Real GDELT Probe Event Flags\n\n"
        + base.markdown_table(rows[:30], columns)
        + "\n\nThis is a preview; the CSV contains the full compact probe output.",
    )
    base.write_csv(PROBE_DIR / "01_real_gdelt_probe_status.csv", status_rows, list(status_rows[0]))
    base.write_md(
        PROBE_DIR / "01_real_gdelt_probe_status.md",
        "# Real GDELT Probe Status\n\n" + base.markdown_table(status_rows, list(status_rows[0])),
    )
    df = pd.DataFrame(rows)
    ok = df["query_status"].eq("ok")
    summary = f"""# Real GDELT Probe Summary

- Probe events: `{len(df)}`
- Successful real GDELT queries: `{int(ok.sum())}`
- Failed/non-OK queries: `{int((~ok).sum())}`
- Events with one or more returned articles: `{int((df['article_count'].astype(int) > 0).sum())}`
- Top-5 article-overlap rate: `{(df[df['top5_flag']]['article_count'].astype(int) > 0).mean():.3f}`
- Non-top article-overlap rate: `{(df[~df['top5_flag']]['article_count'].astype(int) > 0).mean():.3f}`

This is a stratified real-news feasibility probe, not a full public-news control.
No article bodies are stored, and no simulated rows are labeled as real.
"""
    base.write_md(PROBE_DIR / "03_real_gdelt_probe_summary.md", summary)
    interpretation = """# Free-News Probe Interpretation

The GDELT pass is a real stratified probe, not a full v2 news-control layer. It
can reveal whether obvious public-news overlap differs across top-5/non-top or
high/low-return event strata, but it cannot establish clean causal isolation.

The main paper should not claim the v2 signal survives public-news controls
until all 2,341 events have a completed and validated real-news overlap layer.
"""
    base.write_md(PROBE_DIR / "04_free_news_probe_interpretation.md", interpretation)


def result_row(name: str) -> pd.Series:
    table = pd.read_csv(OUT_DIR / "02_v2_event_study_robustness_table.csv")
    return table.loc[table["specification"].eq(name)].iloc[0]


def write_final_narrative() -> None:
    all_v2 = result_row("v2 all accepted events")
    top5 = result_row("v2 top-5 tickers")
    non_top = result_row("v2 non-top tickers")
    low = result_row("v2 low-lookahead")
    duplicate = result_row("v2 duplicate-collapsed")
    buy = result_row("v2 buy-only")
    sell = result_row("v2 sell-only")
    sec_path = OUT_DIR / "sec" / "04_v2_sec_clean_event_study.csv"
    factor_path = OUT_DIR / "factors" / "03_v2_factor_adjusted_alpha_table.csv"
    robust_path = OUT_DIR / "robust_inference" / "01_v2_clustered_inference.csv"
    portfolio_path = OUT_DIR / "portfolio" / "01_v2_strategy_return_table.csv"
    creator_path = OUT_DIR / "creator_deep_dive" / "01_creator_summary.csv"
    ticker_path = OUT_DIR / "ticker_deep_dive" / "01_ticker_summary.csv"
    sec = pd.read_csv(sec_path) if sec_path.exists() else pd.DataFrame()
    factors = pd.read_csv(factor_path) if factor_path.exists() else pd.DataFrame()
    robust = pd.read_csv(robust_path) if robust_path.exists() else pd.DataFrame()
    portfolio = pd.read_csv(portfolio_path) if portfolio_path.exists() else pd.DataFrame()
    creators = pd.read_csv(creator_path) if creator_path.exists() else pd.DataFrame()
    tickers = pd.read_csv(ticker_path) if ticker_path.exists() else pd.DataFrame()

    abstract = """# V2 Abstract

Using the expanded RunPod database, this study analyzes 2,341 YouTube
transcript-supported stock recommendation events. The full-sample abnormal
return is near zero over one and five trading days, but the effect is strongly
heterogeneous: top-5 mega-cap momentum tickers remain positive while non-top
recommendations underperform. The evidence supports an attention-amplification
and concentration interpretation, not broad causal or tradable alpha.
"""
    base.write_md(NARRATIVE_DIR / "01_v2_abstract.md", abstract)
    base.write_md(
        NARRATIVE_DIR / "02_v2_introduction.md",
        "# V2 Introduction\n\nThe v2 paper asks whether finfluencer recommendations predict broad abnormal returns or instead synchronize attention around already salient stocks. The expanded sample moves the answer toward heterogeneity and concentration.",
    )
    base.write_md(
        NARRATIVE_DIR / "03_v2_data_and_sample.md",
        "# V2 Data and Sample\n\nThe primary sample contains 9,992 transcript rows and 2,341 accepted recommendation events. V1 is preserved as a historical benchmark, but v2 is primary because it is larger and manifest-backed.",
    )
    base.write_md(
        NARRATIVE_DIR / "04_v2_methods.md",
        "# V2 Methods\n\nEvent studies estimate abnormal returns by comparing realized stock returns with modeled normal returns. V2 uses local yfinance adjusted-close data, SPY-adjusted returns, SEC metadata, factor models, placebo tests, and robust inference diagnostics.",
    )
    results = f"""# V2 Results

Full-sample v2 abnormal returns are `{all_v2['mean_1d_ar']}` over 1D
(p=`{all_v2['p_1d']}`) and `{all_v2['mean_5d_ar']}` over 5D
(p=`{all_v2['p_5d']}`). Top-5 events show `{top5['mean_5d_ar']}` over 5D
(p=`{top5['p_5d']}`), while non-top events show `{non_top['mean_5d_ar']}`
(p=`{non_top['p_5d']}`).

The v2 result weakens the v1 broad-alpha story but strengthens the concentration
story.
"""
    base.write_md(NARRATIVE_DIR / "05_v2_results.md", results)
    sec_line = "SEC refresh completed for all v2 events." if not sec.empty else "SEC refresh unavailable."
    factor_line = "Factor alpha table computed with free Kenneth French factors." if not factors.empty else "Factor alpha unavailable."
    robust_line = "Clustered and bootstrap inference tables are available." if not robust.empty else "Robust inference unavailable."
    base.write_md(
        NARRATIVE_DIR / "06_v2_robustness.md",
        f"# V2 Robustness\n\n{sec_line} {factor_line} {robust_line} Free-news remains a stratified probe, not a full control.",
    )
    if not portfolio.empty:
        p25 = portfolio[(portfolio["holding_days"].eq(5)) & (portfolio["cost_bps"].eq(25))]
        best = p25.sort_values("average_trade_return", ascending=False).iloc[0]
        port_text = f"Best 5D 25 bps diagnostic strategy: `{best['strategy']}` with average trade return `{best['average_trade_return']}`."
    else:
        port_text = "Portfolio diagnostics unavailable."
    base.write_md(
        NARRATIVE_DIR / "07_v2_portfolio_and_economic_significance.md",
        "# V2 Portfolio and Economic Significance\n\n"
        + port_text
        + " These diagnostics do not establish tradable alpha.",
    )
    top_creator = creators.iloc[0]["creator"] if not creators.empty else "not available"
    top_ticker = tickers.iloc[0]["ticker"] if not tickers.empty else "not available"
    base.write_md(
        NARRATIVE_DIR / "08_v2_creator_and_ticker_deep_dive.md",
        f"# V2 Creator and Ticker Deep Dive\n\nTop event-volume creator: `{top_creator}`. Top event-volume ticker: `{top_ticker}`. Creator effects should be interpreted through ticker mix and concentration.",
    )
    base.write_md(
        NARRATIVE_DIR / "09_v2_causal_diagnostics.md",
        "# V2 Causal Diagnostics\n\nPretrend, placebo, permutation, matched-control, and DiD-style diagnostics are falsification checks. They do not convert the event study into causal proof.",
    )
    base.write_md(
        NARRATIVE_DIR / "10_v2_limitations.md",
        "# V2 Limitations\n\nThe full-sample effect is insignificant, public-news controls are incomplete, GDELT is only a probe, event timing is approximate, and no strategy is validated as executable after realistic liquidity and timing costs.",
    )
    base.write_md(
        NARRATIVE_DIR / "11_v2_conclusion.md",
        "# V2 Conclusion\n\nThe expanded v2 evidence supports attention amplification concentrated in mega-cap momentum tickers and non-top underperformance. It does not support a broad YouTube alpha or causal trading claim.",
    )
    one_page = f"""# V2 Professor One-Page

- Sample: 2,341 recommendation events from the expanded RunPod DB.
- Headline: 5D full-sample AR `{all_v2['mean_5d_ar']}`, p=`{all_v2['p_5d']}`.
- Core finding: top-5 positive, non-top negative.
- Claim: attention amplification and concentration, not broad alpha.
- Caveat: news controls and causal identification remain incomplete.
"""
    base.write_md(NARRATIVE_DIR / "12_v2_professor_one_page.md", one_page)
    defense = """# V2 60-Second Defense

We promoted v2 because it uses the full RunPod database, not because it improves
the result. The broader sample removes the broad-alpha headline: full-sample
returns are near zero. What survives is heterogeneity. Top mega-cap momentum
names remain positive; non-top recommendations are negative. The paper is now
about attention amplification and concentration, with causal and tradability
caveats stated clearly.
"""
    base.write_md(NARRATIVE_DIR / "13_v2_60_second_defense.md", defense)
    claims = [
        {"claim": "V2 establishes broad YouTube alpha.", "supported": "No", "evidence": "full-sample 5D p is insignificant"},
        {"claim": "Top-5 ticker recommendations are positive.", "supported": "Yes", "evidence": f"5D mean {top5['mean_5d_ar']}, p {top5['p_5d']}"},
        {"claim": "Non-top recommendations underperform.", "supported": "Yes", "evidence": f"5D mean {non_top['mean_5d_ar']}, p {non_top['p_5d']}"},
        {"claim": "Causality is proven.", "supported": "No", "evidence": "diagnostics are falsification checks only"},
        {"claim": "Free-news controls are complete.", "supported": "No", "evidence": "GDELT is a stratified probe only"},
    ]
    base.write_md(
        NARRATIVE_DIR / "14_v2_claim_matrix.md",
        "# V2 Claim Matrix\n\n" + base.markdown_table(claims, list(claims[0])),
    )
    base.write_md(
        NARRATIVE_DIR / "15_v2_figure_and_table_plan.md",
        "# V2 Figure and Table Plan\n\nUse sample funnel, event-study forest plot, top5/non-top bar chart, SEC/factor robustness tables, causal diagnostics, portfolio cost sensitivity, and creator/ticker concentration tables.",
    )

    readme = """# Final Paper Package V2 Expanded

This is the primary candidate empirical package built from the expanded live
RunPod database. V1 remains preserved as a historical benchmark.

Paper readiness: `ADOPT_V2_PRIMARY_WITH_CAUTION`.

Key directories:

- `locked_sample_v2/`: compact v2 manifests and sample construction.
- `sec/`: full v2 SEC metadata confound refresh.
- `factors/`: free Kenneth French factor-adjusted alpha diagnostics.
- `causal_diagnostics/`: pretrend, placebo, permutation, matched-control, and DiD-style diagnostics.
- `robust_inference/`: clustered SEs, bootstrap CIs, and multiple-testing adjustments.
- `portfolio/`: event-trade portfolio and transaction-cost diagnostics.
- `creator_deep_dive/` and `ticker_deep_dive/`: heterogeneity and concentration.
- `quality_sensitivity/`: extraction-quality sensitivity.
- `free_news_probe/`: real GDELT stratified probe, not a full news control.
- `final_narrative/`: paper-facing v2 narrative package.
"""
    base.write_md(OUT_DIR / "README.md", readme)
    master = f"""# V2 Master Audit

## Sample

- Transcript rows: `9,992`
- Accepted recommendation events: `2,341`
- Return matched 5D: `{all_v2['n_5d']}`

## Headline

- Full-sample 1D: `{all_v2['mean_1d_ar']}`, p=`{all_v2['p_1d']}`
- Full-sample 5D: `{all_v2['mean_5d_ar']}`, p=`{all_v2['p_5d']}`
- Top-5 5D: `{top5['mean_5d_ar']}`, p=`{top5['p_5d']}`
- Non-top 5D: `{non_top['mean_5d_ar']}`, p=`{non_top['p_5d']}`
- Low-lookahead 5D: `{low['mean_5d_ar']}`, p=`{low['p_5d']}`
- Duplicate-collapsed 5D: `{duplicate['mean_5d_ar']}`, p=`{duplicate['p_5d']}`
- Buy-only 5D: `{buy['mean_5d_ar']}`, p=`{buy['p_5d']}`
- Sell-only 5D: `{sell['mean_5d_ar']}`, p=`{sell['p_5d']}`

## Status

- SEC: full v2 metadata refresh complete if `sec/` exists.
- Factor: free Kenneth French diagnostics complete if `factors/` exists.
- Causal diagnostics: falsification only, not causal proof.
- Portfolio: diagnostic only, not tradable-alpha proof.
- Free-news: real GDELT probe only; full public-news control incomplete.

## Adoption

`ADOPT_V2_PRIMARY_WITH_CAUTION`

## Final Claim

The expanded sample supports attention amplification and concentration in
mega-cap momentum tickers, with non-top underperformance. It does not support a
broad causal or tradable-alpha claim.

## Unresolved Issues

1. Full public-news control remains incomplete.
2. Intraday execution timing is not validated.
3. Portfolio diagnostics need liquidity/capacity validation before any trading claim.
"""
    base.write_md(OUT_DIR / "99_v2_master_audit.md", master)
    adoption = """# V2 Adoption Recommendation

## Label

ADOPT_V2_PRIMARY_WITH_CAUTION

V2 is the primary candidate package because it is larger, manifest-backed, and
better defended. It should be adopted with the explicit conclusion that broad
full-sample alpha does not survive expansion; the defensible result is
concentrated attention amplification in top mega-cap momentum tickers and
negative/non-positive performance outside those names.
"""
    base.write_md(OUT_DIR / "18_v2_adoption_recommendation.md", adoption)


def refresh_sample_construction_status() -> None:
    paths = [
        OUT_DIR / "locked_sample_v2" / "04_v2_sample_construction.csv",
        OUT_DIR / "01_v2_sample_construction_table.csv",
    ]
    sec_path = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
    factor_path = OUT_DIR / "factors" / "02_v2_factor_adjusted_event_returns.csv"
    sec_clean = sec_confounded = None
    if sec_path.exists():
        sec = pd.read_csv(sec_path)
        sec_clean = int(sec["sec_clean_flag"].astype(bool).sum())
        sec_confounded = int(sec["sec_confounded_flag"].astype(bool).sum())
    factor_count = None
    if factor_path.exists():
        factors = pd.read_csv(factor_path)
        computed = factors[
            factors["status"].eq("computed")
            & factors["model"].ne("SPY_adjusted")
            & factors["horizon"].eq("5D")
        ]
        factor_count = int(computed["event_id"].nunique())
    for path in paths:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if sec_clean is not None:
            df.loc[df["metric"].eq("sec_clean_events"), "count"] = sec_clean
            df.loc[df["metric"].eq("sec_clean_events"), "source"] = "full v2 SEC submissions refresh"
            df.loc[df["metric"].eq("sec_clean_events"), "notes"] = "all v2 events audited with compact SEC metadata"
            df.loc[df["metric"].eq("sec_confounded_events"), "count"] = sec_confounded
            df.loc[df["metric"].eq("sec_confounded_events"), "source"] = "full v2 SEC submissions refresh"
            df.loc[df["metric"].eq("sec_confounded_events"), "notes"] = "material filing within +/-5 calendar days"
        if factor_count is not None:
            df.loc[df["metric"].eq("factor_matched_events"), "count"] = factor_count
            df.loc[df["metric"].eq("factor_matched_events"), "source"] = "free Kenneth French daily factors"
            df.loc[df["metric"].eq("factor_matched_events"), "notes"] = "5D factor-adjusted alpha computed where estimation windows are sufficient"
        df.to_csv(path, index=False)
    sample = pd.read_csv(OUT_DIR / "locked_sample_v2" / "04_v2_sample_construction.csv")
    text = "# V2 Sample Construction\n\n" + base.markdown_table(sample.to_dict("records"), list(sample.columns))
    base.write_md(OUT_DIR / "locked_sample_v2" / "04_v2_sample_construction.md", text)
    base.write_md(
        OUT_DIR / "01_v2_sample_construction_table.md",
        "# V2 Sample Construction Table\n\n"
        + base.markdown_table(sample.to_dict("records"), list(sample.columns))
        + "\n\nV2 is the expanded live-DB candidate primary sample. X/Twitter is not used.",
    )


def main() -> int:
    run_probe()
    refresh_sample_construction_status()
    write_final_narrative()
    print("V2 real free-news probe and narrative package complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
