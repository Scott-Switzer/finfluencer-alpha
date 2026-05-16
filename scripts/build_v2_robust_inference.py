from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_expanded_primary_sample_package as base  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "exports" / "final_paper_package_v2_expanded"
ROBUST_DIR = OUT_DIR / "robust_inference"
ROBUST_DIR.mkdir(parents=True, exist_ok=True)
RNG = random.Random(496)


def event_frame() -> pd.DataFrame:
    events = base.fetch_events(base.load_market_data())
    return pd.DataFrame(
        [
            {
                "event_id": e.event_id,
                "ticker": e.ticker,
                "creator": e.creator,
                "event_date": e.event_date.isoformat() if e.event_date else "",
                "cluster": e.duplicate_cluster_id,
                "top5": e.ticker in base.TOP5_TICKERS,
                "low_lookahead": e.timing_bucket in base.LOW_LOOKAHEAD_BUCKETS,
                "buy": e.recommendation_type == "buy",
                "ar_1d": e.ar_1d,
                "ar_5d": e.ar_5d,
            }
            for e in events
        ]
    )


def normal_p(t_stat: float | None) -> float | None:
    if t_stat is None or math.isnan(t_stat):
        return None
    return 2.0 * (1.0 - base.normal_cdf(abs(t_stat)))


def cluster_se(values: pd.Series, groups: pd.Series) -> float | None:
    df = pd.DataFrame({"value": values, "group": groups}).dropna()
    if len(df) < 2:
        return None
    mean = df["value"].mean()
    residual_sum = df.assign(resid=df["value"] - mean).groupby("group")["resid"].sum()
    g = len(residual_sum)
    n = len(df)
    if g < 2:
        return None
    variance = (g / (g - 1)) * float((residual_sum**2).sum()) / (n**2)
    return math.sqrt(max(variance, 0.0))


def inference_row(df: pd.DataFrame, sample: str, horizon: str, field: str) -> dict[str, Any]:
    data = df.dropna(subset=[field]).copy()
    stats = base.t_test(data[field].astype(float).tolist())
    naive_se = None
    if int(stats["n"]) > 1:
        naive_se = float(data[field].std(ddof=1)) / math.sqrt(int(stats["n"]))
    rows = {
        "sample": sample,
        "horizon": horizon,
        "n": stats["n"],
        "mean_ar": base.fmt(stats["mean"]),
        "naive_se": base.fmt(naive_se),
        "naive_t": base.fmt(stats["t"], 3),
        "naive_p": base.fmt(stats["p"], 6),
    }
    for label, group_col in (
        ("ticker", "ticker"),
        ("creator", "creator"),
        ("event_date", "event_date"),
        ("duplicate_cluster", "cluster"),
    ):
        se = cluster_se(data[field], data[group_col])
        t_stat = None if se in (None, 0) or stats["mean"] is None else float(stats["mean"]) / se
        rows[f"cluster_{label}_se"] = base.fmt(se)
        rows[f"cluster_{label}_p"] = base.fmt(normal_p(t_stat), 6)
    se_ticker = cluster_se(data[field], data["ticker"])
    se_date = cluster_se(data[field], data["event_date"])
    se_pair = cluster_se(data[field], data["ticker"].astype(str) + "__" + data["event_date"].astype(str))
    two_way = None
    if se_ticker is not None and se_date is not None and se_pair is not None:
        two_way = math.sqrt(max(se_ticker**2 + se_date**2 - se_pair**2, 0.0))
    t_two = None if two_way in (None, 0) or stats["mean"] is None else float(stats["mean"]) / two_way
    rows["two_way_ticker_date_se"] = base.fmt(two_way)
    rows["two_way_ticker_date_p"] = base.fmt(normal_p(t_two), 6)
    return rows


def bootstrap_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    samples = {
        "all": df,
        "top5": df[df["top5"]],
        "non_top": df[~df["top5"]],
        "low_lookahead": df[df["low_lookahead"]],
    }
    for sample, data in samples.items():
        tickers = sorted(data["ticker"].dropna().unique())
        for horizon, field in (("1D", "ar_1d"), ("5D", "ar_5d")):
            valid = data.dropna(subset=[field])
            observed = valid[field].mean()
            means = []
            for _ in range(500):
                chosen = [RNG.choice(tickers) for _ in tickers] if tickers else []
                boot = pd.concat([valid[valid["ticker"].eq(ticker)] for ticker in chosen], ignore_index=True)
                if not boot.empty:
                    means.append(float(boot[field].mean()))
            lo, hi = (None, None)
            if means:
                lo, hi = pd.Series(means).quantile([0.025, 0.975]).tolist()
            rows.append(
                {
                    "sample": sample,
                    "horizon": horizon,
                    "n": len(valid),
                    "observed_mean": base.fmt(observed),
                    "block_bootstrap_by_ticker_ci_lower": base.fmt(lo),
                    "block_bootstrap_by_ticker_ci_upper": base.fmt(hi),
                    "bootstrap_iterations": len(means),
                }
            )
    return rows


def multiple_testing(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tests = []
    for row in rows:
        p = row.get("naive_p")
        if p not in ("", None):
            tests.append((row["sample"], row["horizon"], float(p)))
    m = len(tests)
    sorted_tests = sorted(enumerate(tests), key=lambda item: item[1][2])
    q_values = [1.0] * m
    running = 1.0
    for rank, (orig_idx, (_sample, _horizon, p)) in reversed(list(enumerate(sorted_tests, start=1))):
        running = min(running, p * m / rank)
        q_values[orig_idx] = min(running, 1.0)
    out = []
    for idx, (sample, horizon, p) in enumerate(tests):
        out.append(
            {
                "sample": sample,
                "horizon": horizon,
                "raw_p": base.fmt(p, 6),
                "bonferroni_p": base.fmt(min(p * m, 1.0), 6),
                "bh_fdr_q": base.fmt(q_values[idx], 6),
                "test_family_size": m,
            }
        )
    return out


def main() -> int:
    df = event_frame()
    samples = {
        "all": df,
        "top5": df[df["top5"]],
        "non_top": df[~df["top5"]],
        "low_lookahead": df[df["low_lookahead"]],
        "duplicate_collapsed": df.drop_duplicates("cluster"),
        "buy_only": df[df["buy"]],
        "sell_only": df[~df["buy"]],
    }
    rows = []
    for sample, data in samples.items():
        rows.append(inference_row(data, sample, "1D", "ar_1d"))
        rows.append(inference_row(data, sample, "5D", "ar_5d"))
    columns = list(rows[0])
    base.write_csv(ROBUST_DIR / "01_v2_clustered_inference.csv", rows, columns)
    base.write_md(
        ROBUST_DIR / "01_v2_clustered_inference.md",
        "# V2 Clustered Inference\n\n" + base.markdown_table(rows, columns),
    )
    boot = bootstrap_rows(df)
    base.write_csv(ROBUST_DIR / "02_v2_bootstrap_confidence_intervals.csv", boot, list(boot[0]))
    base.write_md(
        ROBUST_DIR / "02_v2_bootstrap_confidence_intervals.md",
        "# V2 Bootstrap Confidence Intervals\n\n" + base.markdown_table(boot, list(boot[0])),
    )
    mt = multiple_testing(rows)
    base.write_csv(ROBUST_DIR / "03_v2_multiple_testing_adjustment.csv", mt, list(mt[0]))
    base.write_md(
        ROBUST_DIR / "03_v2_multiple_testing_adjustment.md",
        "# V2 Multiple-Testing Adjustment\n\n" + base.markdown_table(mt, list(mt[0])),
    )
    text = """# V2 Inference Interpretation

The full-sample headline remains economically small and statistically
insignificant under naive and clustered inference. The key inference question is
whether top-5 positivity and non-top negativity survive conservative standard
errors and multiple-testing adjustments. These tables should be cited instead
of relying only on naive t-tests.
"""
    base.write_md(ROBUST_DIR / "04_v2_inference_interpretation.md", text)
    print("V2 robust inference complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
