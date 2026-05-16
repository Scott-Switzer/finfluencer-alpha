from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402
import build_v2_long_horizon_returns as lh  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
PORT_DIR = OUT_DIR / "portfolio_long_horizon"
FIG_DIR = OUT_DIR / "figures_data"
NARRATIVE_DIR = OUT_DIR / "final_narrative_long_horizon"
PORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)
NARRATIVE_DIR.mkdir(parents=True, exist_ok=True)
HOLDING_PERIODS = ["5D", "10D", "21D", "42D", "63D", "126D", "252D"]
COSTS = [0, 5, 10, 25, 50, 100]


def write_table(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        rows = [{"status": "no_rows"}]
    columns = list(rows[0])
    base.write_csv(path.with_suffix(".csv"), rows, columns)
    base.write_md(
        path.with_suffix(".md"), f"# {title}\n\n" + base.markdown_table(rows[:100], columns)
    )


def load_panel() -> pd.DataFrame:
    df = pd.read_csv(OUT_DIR / "long_horizon" / "01_v2_long_horizon_event_returns.csv")
    panel = df[
        (df["window_type"] == "forward")
        & (df["horizon"].isin(HOLDING_PERIODS))
        & (df["status"] == "computed")
    ].copy()
    panel["raw_return"] = pd.to_numeric(panel["raw_return"], errors="coerce")
    panel["spy_bhar"] = pd.to_numeric(panel["spy_bhar"], errors="coerce")
    panel["event_date_dt"] = pd.to_datetime(panel["event_date"], errors="coerce")
    panel["top5_bool"] = panel["top5_flag"].astype(str).eq("True")
    panel["low_lookahead_bool"] = panel["low_lookahead_flag"].astype(str).eq("True")
    panel["duplicate_collapsed_bool"] = panel["duplicate_collapsed_flag"].astype(str).eq("True")
    panel["high_quality_bool"] = (
        pd.to_numeric(panel["actionability_score"], errors="coerce").fillna(0) >= 3.0
    )
    return panel


def creator_top_quartile(panel: pd.DataFrame) -> set[str]:
    base_h = panel[panel["horizon"].eq("5D")]
    means = base_h.groupby("creator")["spy_bhar"].mean().dropna()
    if means.empty:
        return set()
    cutoff = means.quantile(0.75)
    return set(means[means >= cutoff].index)


def strategy_mask(panel: pd.DataFrame, strategy: str) -> tuple[pd.Series, int]:
    top_creators = creator_top_quartile(panel)
    if strategy == "long_all_buys":
        return panel["recommendation_type"].eq("buy"), 1
    if strategy == "short_all_sells":
        return panel["recommendation_type"].eq("sell"), -1
    if strategy == "long_buy_short_sell":
        return panel["recommendation_type"].isin(["buy", "sell"]), 0
    if strategy == "long_top5_buys":
        return panel["recommendation_type"].eq("buy") & panel["top5_bool"], 1
    if strategy == "long_non_top_buys":
        return panel["recommendation_type"].eq("buy") & ~panel["top5_bool"], 1
    if strategy == "short_non_top_buys_diagnostic":
        return panel["recommendation_type"].eq("buy") & ~panel["top5_bool"], -1
    if strategy == "low_lookahead_top5":
        return panel["recommendation_type"].eq("buy") & panel["top5_bool"] & panel[
            "low_lookahead_bool"
        ], 1
    if strategy == "high_quality_top5":
        return panel["recommendation_type"].eq("buy") & panel["top5_bool"] & panel[
            "high_quality_bool"
        ], 1
    if strategy == "duplicate_collapsed_only":
        return panel["duplicate_collapsed_bool"], 0
    if strategy == "creator_adjusted_top_quartile":
        return panel["creator"].isin(top_creators), 0
    if strategy == "momentum_conditioned_top5":
        return panel["recommendation_type"].eq("buy") & panel["top5_bool"], 1
    return panel.index == panel.index, 0


def directed_returns(group: pd.DataFrame, strategy: str, default_direction: int) -> list[float]:
    values = []
    for row in group.to_dict("records"):
        raw = lh.clean_float(row.get("raw_return"))
        if raw is None:
            continue
        direction = default_direction
        if strategy in {
            "long_buy_short_sell",
            "duplicate_collapsed_only",
            "creator_adjusted_top_quartile",
        }:
            direction = 1 if row.get("recommendation_type") == "buy" else -1
        values.append(direction * raw)
    return values


def max_drawdown(returns: list[float]) -> float | None:
    if not returns:
        return None
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for ret in returns:
        equity *= 1 + ret
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def sortino(values: list[float], scale: float) -> float | None:
    if len(values) < 2:
        return None
    downside = [min(0.0, value) for value in values]
    downside_sd = statistics.stdev(downside) if len(set(downside)) > 1 else None
    if not downside_sd:
        return None
    return statistics.mean(values) / downside_sd * math.sqrt(scale)


def metrics(values: list[float], holding_days: int, cost_bps: int) -> dict[str, Any]:
    cost = 2 * cost_bps / 10000.0
    net = [value - cost for value in values]
    if not net:
        return {
            "trade_count": 0,
            "average_trade_return": "",
            "median_trade_return": "",
            "cumulative_return": "",
            "cagr_proxy": "",
            "annualized_volatility": "",
            "sharpe": "",
            "sortino": "",
            "max_drawdown": "",
            "hit_rate": "",
            "skew": "",
            "breakeven_transaction_cost_bps": "",
        }
    equity = 1.0
    for ret in net:
        equity *= 1 + ret
    scale = 252 / holding_days
    mean = statistics.mean(net)
    sd = statistics.stdev(net) if len(net) > 1 else 0.0
    sharpe = mean / sd * math.sqrt(scale) if sd else None
    series = pd.Series(net)
    gross_mean = statistics.mean(values)
    return {
        "trade_count": len(net),
        "average_trade_return": lh.format_float(mean),
        "median_trade_return": lh.format_float(statistics.median(net)),
        "cumulative_return": lh.format_float(equity - 1),
        "cagr_proxy": lh.format_float((equity ** (scale / len(net)) - 1) if equity > 0 else None),
        "annualized_volatility": lh.format_float(sd * math.sqrt(scale) if sd else None),
        "sharpe": lh.format_float(sharpe, 3),
        "sortino": lh.format_float(sortino(net, scale), 3),
        "max_drawdown": lh.format_float(max_drawdown(net)),
        "hit_rate": lh.format_float(sum(1 for value in net if value > 0) / len(net), 4),
        "skew": lh.format_float(series.skew()),
        "breakeven_transaction_cost_bps": lh.format_float(max(0.0, gross_mean * 10000 / 2), 2),
    }


def strategy_rows(
    panel: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    strategies = [
        "long_all_buys",
        "short_all_sells",
        "long_buy_short_sell",
        "long_top5_buys",
        "long_non_top_buys",
        "short_non_top_buys_diagnostic",
        "low_lookahead_top5",
        "high_quality_top5",
        "duplicate_collapsed_only",
        "creator_adjusted_top_quartile",
        "momentum_conditioned_top5",
    ]
    summary_rows = []
    cost_rows = []
    distribution_rows = []
    for horizon in HOLDING_PERIODS:
        hdf = panel[panel["horizon"].eq(horizon)].sort_values("event_date_dt")
        holding_days = int(horizon.replace("D", ""))
        for strategy in strategies:
            mask, direction = strategy_mask(hdf, strategy)
            selected = hdf[mask]
            values = directed_returns(selected, strategy, direction)
            for cost in COSTS:
                row = {
                    "strategy": strategy,
                    "holding_days": holding_days,
                    "cost_bps": cost,
                    **metrics(values, holding_days, cost),
                    "turnover_trades": len(values) * 2,
                    "top5_event_share": lh.format_float(
                        selected["top5_bool"].mean() if len(selected) else None, 4
                    ),
                    "status": "diagnostic_event_trade_sequence",
                }
                summary_rows.append(row)
                cost_rows.append(row.copy())
            if values:
                series = pd.Series(values)
                distribution_rows.append(
                    {
                        "strategy": strategy,
                        "holding_days": holding_days,
                        "trade_count": len(values),
                        "p05": lh.format_float(series.quantile(0.05)),
                        "p25": lh.format_float(series.quantile(0.25)),
                        "median": lh.format_float(series.quantile(0.50)),
                        "p75": lh.format_float(series.quantile(0.75)),
                        "p95": lh.format_float(series.quantile(0.95)),
                    }
                )
    return summary_rows, cost_rows, distribution_rows


def equity_curve_rows(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for strategy in ["long_all_buys", "long_top5_buys", "short_non_top_buys_diagnostic"]:
        hdf = panel[panel["horizon"].eq("21D")].sort_values("event_date_dt")
        mask, direction = strategy_mask(hdf, strategy)
        values = directed_returns(hdf[mask], strategy, direction)
        dates = hdf[mask]["event_date"].tolist()
        equity = 1.0
        peak = 1.0
        for idx, value in enumerate(values):
            equity *= 1 + value - 0.0025
            peak = max(peak, equity)
            rows.append(
                {
                    "strategy": strategy,
                    "sequence": idx + 1,
                    "event_date": dates[idx],
                    "equity": lh.format_float(equity),
                    "drawdown": lh.format_float(equity / peak - 1 if peak else None),
                }
            )
    return rows


def concentration_rows(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for horizon in HOLDING_PERIODS:
        hdf = panel[panel["horizon"].eq(horizon)]
        total = hdf["raw_return"].abs().sum()
        for ticker, group in hdf.groupby("ticker"):
            rows.append(
                {
                    "horizon": horizon,
                    "ticker": ticker,
                    "event_count": group["event_id"].nunique(),
                    "abs_return_contribution_share": lh.format_float(
                        group["raw_return"].abs().sum() / total if total else None, 4
                    ),
                    "mean_raw_return": lh.format_float(group["raw_return"].mean()),
                    "mean_spy_bhar": lh.format_float(group["spy_bhar"].mean()),
                }
            )
    return rows


def claim_matrix() -> list[dict[str, Any]]:
    rows = [
        {
            "claim": "broad full-sample alpha",
            "supported_status": "rejected",
            "strongest_evidence": "full-sample 1D/5D and long horizons are small or unstable",
            "weakest_evidence": "some SEC-clean/factor subsets are positive",
            "caveat": "sample is observational",
            "paper_wording_allowed": "no broad full-sample alpha",
            "paper_wording_prohibited": "YouTube recommendations generate broad alpha",
        },
        {
            "claim": "short-window top5 attention effect",
            "supported_status": "mixed_supported",
            "strongest_evidence": "top5 1D/5D positive in short-window v2 tables",
            "weakest_evidence": "cluster/factor adjustments weaken 5D",
            "caveat": "likely momentum synchronization",
            "paper_wording_allowed": "top-name concentration",
            "paper_wording_prohibited": "causal mega-cap alpha",
        },
        {
            "claim": "non-top underperformance",
            "supported_status": "mixed_supported",
            "strongest_evidence": "non-top short-window returns are negative",
            "weakest_evidence": "factor and cluster adjustments weaken inference",
            "caveat": "pretrends and news remain threats",
            "paper_wording_allowed": "non-top recommendations underperform in event windows",
            "paper_wording_prohibited": "profitable short strategy",
        },
        {
            "claim": "creator skill",
            "supported_status": "mixed",
            "strongest_evidence": "creator heterogeneity exists",
            "weakest_evidence": "ticker/top5 exposure explains much of it",
            "caveat": "creator naming should be cautious",
            "paper_wording_allowed": "creator differences largely reflect ticker selection",
            "paper_wording_prohibited": "specific creators have proven skill",
        },
        {
            "claim": "real-news-confound robustness",
            "supported_status": "not_tested_full_sample",
            "strongest_evidence": "provider diagnostics/probe attempted",
            "weakest_evidence": "GDELT reliability below full-run threshold if probe fails",
            "caveat": "failed providers mean unknown, not clean",
            "paper_wording_allowed": "news control remains incomplete",
            "paper_wording_prohibited": "news confounds are controlled",
        },
        {
            "claim": "tradable strategy",
            "supported_status": "rejected",
            "strongest_evidence": "portfolio diagnostics are cost/drawdown sensitive",
            "weakest_evidence": "some gross top5 strategies look positive",
            "caveat": "liquidity and timestamp execution are not validated",
            "paper_wording_allowed": "not a validated trading strategy",
            "paper_wording_prohibited": "tradable alpha",
        },
        {
            "claim": "pump-and-fade pattern",
            "supported_status": "mixed",
            "strongest_evidence": "event-time interval and ticker candidate tables",
            "weakest_evidence": "descriptive, not misconduct evidence",
            "caveat": "requires news and causal validation",
            "paper_wording_allowed": "possible post-recommendation fade",
            "paper_wording_prohibited": "pump-and-dump proof",
        },
    ]
    return rows


def write_narrative() -> None:
    abstract = """# Long-Horizon Abstract

Using the expanded v2 RunPod sample of 2,341 transcript-supported YouTube stock
recommendations, the long-horizon package finds no reliable broad alpha. The
evidence is strongest for heterogeneous attention concentration: short-window
positive abnormal returns cluster in a small set of mega-cap momentum names,
while non-top recommendations are weaker or negative and long-horizon results
are sensitive to censoring, factors, controls, and transaction costs.
"""
    files = {
        "01_abstract_long_horizon.md": abstract,
        "02_introduction_long_horizon.md": "# Introduction\n\nThe v2 paper is now framed around attention amplification, momentum synchronization, and heterogeneous performance rather than broad YouTube alpha.",
        "03_data_sample_long_horizon.md": "# Data and Sample\n\nThe primary v2 sample uses 9,992 transcript rows and 2,341 accepted recommendation events. V1 remains a historical benchmark.",
        "04_methods_long_horizon.md": "# Methods\n\nThe package combines BHAR, CAR, calendar-time portfolios, factor adjustment, real-news diagnostics, matched controls, placebo shifts, and portfolio cost tests.",
        "05_short_window_results.md": "# Short-Window Results\n\nThe full sample is near zero over 1D/5D. Top5 names are positive; non-top names are negative. Robust inference weakens the simple alpha story.",
        "06_long_horizon_results.md": "# Long-Horizon Results\n\nLong horizons test whether short-window reactions persist, reverse, or drift. Right-censoring is retained and reported rather than silently dropped.",
        "07_news_confounds.md": "# News Confounds\n\nReal news controls remain the main credibility gap. Failed provider queries are unknown, not clean.",
        "08_factor_and_alpha_results.md": "# Factor and Alpha Results\n\nFactor adjustment is a stress test for market, size, value, profitability, investment, and momentum exposure. It does not establish causality.",
        "09_causal_falsification.md": "# Causal Falsification\n\nMatched controls, placebo shifts, permutations, and pretrends test whether the event-date treatment story survives. The design remains observational.",
        "10_portfolio_economic_significance.md": "# Portfolio and Economic Significance\n\nPortfolio tests are diagnostic. Cost sensitivity, drawdowns, and concentration prevent tradable-alpha claims.",
        "11_creator_ticker_deep_dive.md": "# Creator and Ticker Deep Dive\n\nCreator heterogeneity is interpreted through ticker exposure and top-name concentration. Ticker effects dominate long-horizon inference.",
        "12_limitations_long_horizon.md": "# Limitations\n\nThe study lacks random assignment and complete public-news controls. Long horizons are right-censored for recent events.",
        "13_conclusion_long_horizon.md": "# Conclusion\n\nThe strongest defensible claim is attention amplification and ticker concentration, not broad causal or tradable alpha.",
        "14_professor_one_page_long_horizon.md": "# Professor One-Page\n\nV2 is primary because it is larger and reproducible. It rejects broad alpha and supports a narrower heterogeneous attention-concentration claim.",
        "15_60_second_defense_long_horizon.md": "# 60-Second Defense\n\nThe expanded long-horizon analysis does not show broad YouTube alpha. It shows that short-window effects concentrate in salient mega-cap names, non-top recommendations are weaker or negative, and long-run/portfolio/news/factor diagnostics prevent causal or tradable-alpha claims.",
        "16_slide_talking_points_long_horizon.md": "# Slide Talking Points\n\n- V2 is the primary sample.\n- Full sample: no broad alpha.\n- Top names: concentrated attention effect.\n- Non-top: weak or negative.\n- News control incomplete.\n- No causal or trading claim.",
        "17_table_and_figure_plan_long_horizon.md": "# Table and Figure Plan\n\nUse the long-horizon coverage funnel, top5/non-top horizon curve, event-time path, factor alpha table, news provider table, and portfolio cost grid.",
    }
    for name, text in files.items():
        base.write_md(NARRATIVE_DIR / name, text)


def update_readme_and_audits() -> None:
    text = """# V2 Expanded Final Paper Package

This directory now contains the expanded v2 primary sample, maximum-defense
short-window package, and long-horizon alpha/news/portfolio defense.

Core conclusion: the expanded sample does not support broad causal or tradable
YouTube alpha. The defensible finding is heterogeneous attention amplification:
short-window effects concentrate in top mega-cap momentum names, while non-top
recommendations are weaker or negative and long-horizon evidence is sensitive to
censoring, factors, news controls, and costs.

News status: real provider diagnostics are included, but failed providers imply
unknown news status rather than clean events. Do not claim completed news
confound control unless the full real-news layer succeeds.
"""
    base.write_md(OUT_DIR / "README.md", text)
    audit = """# V2 Long-Horizon Final Audit

- Sample: 2,341 accepted events from the expanded RunPod live DB.
- Short-window finding: no broad full-sample alpha; top5 positive and non-top negative.
- Long-horizon purpose: test persistence, reversal, censoring, and tradability.
- Alpha status: BHAR, CAR, calendar-time, and factor diagnostics generated.
- News status: real provider diagnostics/probe generated; no simulated news evidence.
- Causal status: falsification diagnostics only; no causal claim.
- Portfolio status: diagnostic only; no tradable-alpha claim.
- Strongest final claim: attention amplification and ticker concentration.
- Rejected claims: broad alpha, causal alpha, news-controlled alpha, validated trading strategy.
"""
    base.write_md(OUT_DIR / "99_v2_master_audit.md", audit)
    base.write_md(OUT_DIR / "100_v2_long_horizon_final_audit.md", audit)


def main() -> int:
    panel = load_panel()
    summary, costs, distribution = strategy_rows(panel)
    write_table(PORT_DIR / "01_strategy_summary", summary, "Long-Horizon Strategy Summary")
    write_table(PORT_DIR / "02_transaction_cost_grid", costs, "Long-Horizon Transaction Cost Grid")
    risk_rows = [row for row in summary if row["cost_bps"] == 25]
    write_table(
        PORT_DIR / "03_portfolio_risk_metrics", risk_rows, "Long-Horizon Portfolio Risk Metrics"
    )
    concentration = concentration_rows(panel)
    write_table(
        PORT_DIR / "04_portfolio_concentration",
        concentration,
        "Long-Horizon Portfolio Concentration",
    )
    write_table(PORT_DIR / "05_trade_distribution", distribution, "Long-Horizon Trade Distribution")
    base.write_md(
        PORT_DIR / "06_long_horizon_portfolio_interpretation.md",
        "# Long-Horizon Portfolio Interpretation\n\nPortfolio results are diagnostic, not trading advice. If a strategy dies after costs or has extreme drawdowns, that is evidence against tradable alpha. Avoid/short non-top variants should also be treated cautiously because borrow costs, timing, and risk controls are not validated.",
    )
    equity = equity_curve_rows(panel)
    base.write_csv(
        FIG_DIR / "v2_long_horizon_portfolio_equity_curves.csv",
        equity,
        list(equity[0]) if equity else ["status"],
    )
    base.write_csv(
        FIG_DIR / "v2_long_horizon_transaction_cost_heatmap.csv",
        costs,
        list(costs[0]) if costs else ["status"],
    )
    base.write_csv(
        FIG_DIR / "v2_trade_return_distribution.csv",
        distribution,
        list(distribution[0]) if distribution else ["status"],
    )
    claims = claim_matrix()
    base.write_csv(OUT_DIR / "21_v2_long_horizon_claim_matrix.csv", claims, list(claims[0]))
    base.write_md(
        OUT_DIR / "21_v2_long_horizon_claim_matrix.md",
        "# V2 Long-Horizon Claim Matrix\n\n" + base.markdown_table(claims, list(claims[0])),
    )
    write_narrative()
    update_readme_and_audits()
    print(f"V2 long-horizon portfolio complete: rows={len(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
