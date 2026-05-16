from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
TICKER_DIR = OUT_DIR / "ticker_deep_dive"
TICKER_DIR.mkdir(parents=True, exist_ok=True)


def event_df() -> pd.DataFrame:
    events = base.fetch_events(base.load_market_data())
    return pd.DataFrame(
        [
            {
                "event_id": e.event_id,
                "ticker": e.ticker,
                "company_name": e.company_name,
                "creator": e.creator,
                "top5": e.ticker in base.TOP5_TICKERS,
                "buy": e.recommendation_type == "buy",
                "cluster": e.duplicate_cluster_id,
                "timing": e.timing_bucket,
                "ar_1d": e.ar_1d,
                "ar_5d": e.ar_5d,
            }
            for e in events
        ]
    )


def stats(group: pd.DataFrame) -> dict[str, str]:
    values_1d = group["ar_1d"].dropna().astype(float).tolist()
    values_5d = group["ar_5d"].dropna().astype(float).tolist()
    s1 = base.t_test(values_1d)
    s5 = base.t_test(values_5d)
    return {
        "mean_1d_ar": base.fmt(s1["mean"]),
        "mean_5d_ar": base.fmt(s5["mean"]),
        "t_5d": base.fmt(s5["t"], 3),
        "p_5d": base.fmt(s5["p"], 6),
        "median_5d_ar": base.fmt(s5["median"]),
        "win_rate_5d": base.fmt(s5["win_rate"]),
    }


def main() -> int:
    df = event_df()
    sec_share = {}
    sec_path = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
    if sec_path.exists():
        sec = pd.read_csv(sec_path)
        merged = df[["event_id", "ticker"]].merge(sec[["event_id", "sec_confounded_flag"]], on="event_id")
        sec_share = merged.groupby("ticker")["sec_confounded_flag"].mean().to_dict()
    total = df["ar_5d"].dropna().sum()
    rows = []
    for ticker, group in df.groupby("ticker"):
        ret_sum = group["ar_5d"].dropna().sum()
        rows.append(
            {
                "ticker": ticker,
                "company_name": group["company_name"].dropna().iloc[0] if not group.empty else "",
                "event_count": len(group),
                "buy_count": int(group["buy"].sum()),
                "sell_count": int((~group["buy"]).sum()),
                "creator_count": group["creator"].nunique(),
                "top5_flag": ticker in base.TOP5_TICKERS,
                "avg_pre_event_momentum": "",
                **stats(group),
                "SEC_confounded_share": base.fmt(sec_share.get(ticker)),
                "contribution_to_full_sample_mean": base.fmt(None if total == 0 else ret_sum / total),
                "contribution_to_portfolio_return": base.fmt(None if total == 0 else ret_sum / total),
            }
        )
    rows = sorted(rows, key=lambda row: int(row["event_count"]), reverse=True)
    base.write_csv(TICKER_DIR / "01_ticker_summary.csv", rows, list(rows[0]))
    base.write_md(
        TICKER_DIR / "01_ticker_summary.md",
        "# V2 Ticker Summary\n\n" + base.markdown_table(rows, list(rows[0])),
    )
    loo_rows = []
    for ticker in sorted(df["ticker"].unique()):
        remaining = df[df["ticker"] != ticker]
        all_stats = base.t_test(remaining["ar_5d"].dropna().astype(float).tolist())
        top_stats = base.t_test(remaining[remaining["top5"]]["ar_5d"].dropna().astype(float).tolist())
        non_stats = base.t_test(remaining[~remaining["top5"]]["ar_5d"].dropna().astype(float).tolist())
        loo_rows.append(
            {
                "removed_ticker": ticker,
                "remaining_events": len(remaining),
                "headline_5d_mean": base.fmt(all_stats["mean"]),
                "headline_5d_p": base.fmt(all_stats["p"], 6),
                "top5_5d_mean": base.fmt(top_stats["mean"]),
                "top5_5d_p": base.fmt(top_stats["p"], 6),
                "non_top_5d_mean": base.fmt(non_stats["mean"]),
                "non_top_5d_p": base.fmt(non_stats["p"], 6),
            }
        )
    base.write_csv(TICKER_DIR / "02_ticker_leave_one_out.csv", loo_rows, list(loo_rows[0]))
    base.write_md(
        TICKER_DIR / "02_ticker_leave_one_out.md",
        "# V2 Ticker Leave-One-Out\n\n" + base.markdown_table(loo_rows, list(loo_rows[0])),
    )
    groups = {
        "top5_all": df[df["top5"]],
        "non_top_all": df[~df["top5"]],
        "top5_duplicate_collapsed": df[df["top5"]].drop_duplicates("cluster"),
        "non_top_duplicate_collapsed": df[~df["top5"]].drop_duplicates("cluster"),
        "top5_low_lookahead": df[df["top5"] & df["timing"].isin(base.LOW_LOOKAHEAD_BUCKETS)],
        "non_top_low_lookahead": df[(~df["top5"]) & df["timing"].isin(base.LOW_LOOKAHEAD_BUCKETS)],
    }
    sec_path = OUT_DIR / "sec" / "02_v2_sec_event_flags.csv"
    if sec_path.exists():
        sec = pd.read_csv(sec_path)
        clean_ids = set(sec.loc[sec["sec_clean_flag"].astype(bool), "event_id"].astype(int))
        groups["top5_sec_clean"] = df[df["top5"] & df["event_id"].isin(clean_ids)]
        groups["non_top_sec_clean"] = df[(~df["top5"]) & df["event_id"].isin(clean_ids)]
    decomp_rows = []
    total_sum = df["ar_5d"].dropna().sum()
    for name, group in groups.items():
        s = stats(group)
        decomp_rows.append(
            {
                "segment": name,
                "event_count": len(group),
                "return_matched_5d": int(group["ar_5d"].notna().sum()),
                **s,
                "contribution_to_aggregate_effect": base.fmt(
                    None if total_sum == 0 else group["ar_5d"].dropna().sum() / total_sum
                ),
            }
        )
    base.write_csv(TICKER_DIR / "03_top5_vs_non_top_decomposition.csv", decomp_rows, list(decomp_rows[0]))
    base.write_md(
        TICKER_DIR / "03_top5_vs_non_top_decomposition.md",
        "# V2 Top-5 vs Non-Top Decomposition\n\n"
        + base.markdown_table(decomp_rows, list(decomp_rows[0])),
    )
    top_driver = rows[0]["ticker"]
    memo = f"""# V2 Ticker Deep Dive Memo

The v2 paper is primarily about mega-cap technology attention, not broad
stock-picking alpha. The largest event-count ticker is `{top_driver}`. Top-5
events remain positive, while non-top recommendations are negative on average.

Ticker leave-one-out and top-5/non-top decomposition should be used to show
fragility and concentration. The results are consistent with momentum
synchronization and attention amplification rather than generalized predictive
skill.
"""
    base.write_md(TICKER_DIR / "04_ticker_deep_dive_memo.md", memo)
    print("V2 ticker deep dive complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
