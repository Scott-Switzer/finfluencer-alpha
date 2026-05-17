from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v2_critical_defense_utils as utils  # noqa: E402

OUT_DIR = utils.OUT_DIR / "sec_earnings_confounds"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sec = utils.sec_flags()
    if sec.empty:
        rows = []
    else:
        rows = []
        for _, row in sec.iterrows():
            form = str(row.get("material_form_types", ""))
            nearest = str(row.get("nearest_form_type", ""))
            is_8k = "8-K" in form or nearest == "8-K"
            is_10qk = "10-Q" in form or "10-K" in form or nearest in {"10-Q", "10-K"}
            offering = any(x in form for x in ["S-1", "424B", "F-1"])
            ownership = any(x in form for x in ["13D", "13G", "4"])
            material = bool(row.get("material_filing_flag_pm5")) if not pd.isna(row.get("material_filing_flag_pm5")) else False
            confounded = bool(row.get("sec_confounded_flag")) or is_8k or offering
            unknown = str(row.get("query_status", "")).lower() not in {"ok", "cached"}
            reason = []
            if is_8k:
                reason.append("8k_window")
            if is_10qk:
                reason.append("10q_10k_window")
            if offering:
                reason.append("offering_registration_window")
            if ownership:
                reason.append("ownership_insider_window")
            if material:
                reason.append("material_filing_flag")
            if unknown:
                reason.append("sec_unknown")
            rows.append(
                {
                    "event_id": int(row.event_id),
                    "ticker": row.ticker,
                    "company_name": row.company_name,
                    "event_date": row.event_date,
                    "filing_count_pm1": row.get("filing_count_pm1", 0),
                    "filing_count_pm3": row.get("filing_count_pm3", 0),
                    "filing_count_pm5": row.get("filing_count_pm5", 0),
                    "eight_k_pm5_flag": is_8k,
                    "ten_q_or_k_pm5_flag": is_10qk,
                    "offering_registration_pm5_flag": offering,
                    "ownership_or_insider_pm5_flag": ownership,
                    "earnings_proxy_flag": is_10qk,
                    "sec_material_event_confounded_flag": confounded,
                    "sec_routine_filing_flag": is_10qk and not confounded,
                    "sec_unknown_flag": unknown,
                    "sec_clean_expanded_flag": not confounded and not unknown,
                    "reason_codes": ";".join(reason) if reason else "no_material_sec_overlap_detected",
                }
            )
    utils.write_csv(OUT_DIR / "01_sec_event_flags_expanded.csv", rows)
    clean = sum(bool(r["sec_clean_expanded_flag"]) for r in rows)
    conf = sum(bool(r["sec_material_event_confounded_flag"]) for r in rows)
    unknown = sum(bool(r["sec_unknown_flag"]) for r in rows)
    summary = [
        {
            "events": len(rows),
            "sec_clean_events": clean,
            "sec_confounded_events": conf,
            "sec_unknown_events": unknown,
            "source": "existing compact SEC metadata; no filing bodies stored",
        }
    ]
    utils.table_pair(OUT_DIR / "02_sec_earnings_confound_summary", summary, "SEC Earnings Confound Summary")
    panel = utils.forward_panel()
    flags = pd.DataFrame(rows)
    merged = panel.merge(flags[["event_id", "sec_clean_expanded_flag", "sec_material_event_confounded_flag"]], on="event_id", how="left")
    masks = {
        "sec_clean_expanded": merged["sec_clean_expanded_flag"].astype(str).str.lower().eq("true"),
        "sec_confounded_expanded": merged["sec_material_event_confounded_flag"].astype(str).str.lower().eq("true"),
    }
    returns = []
    for name, mask in masks.items():
        returns.extend(utils.summarize_return_panel(merged[mask], "spy_bhar", {name: pd.Series(True, index=merged[mask].index)}))
    utils.table_pair(OUT_DIR / "03_sec_clean_vs_confounded_returns", returns, "SEC Clean Vs Confounded Returns")
    utils.write_md(
        OUT_DIR / "04_sec_earnings_interpretation.md",
        "SEC Earnings Interpretation",
        f"Expanded SEC flags classify {clean} events as SEC-clean, {conf} as SEC/earnings confounded, and {unknown} as unknown. This layer uses compact filing metadata only and does not store filing text.",
    )
    print(f"SEC earnings confounds complete: clean={clean} confounded={conf} unknown={unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
