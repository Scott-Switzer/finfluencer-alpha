# Information environment workplan

## Purpose

This pass separates **original YouTube information** from **analyst relay**, **public narrative relay**, **market sentiment**, and **noise/attention** effects. It improves mechanism and falsification without claiming new alpha.

## The unresolved public-news problem

- Alpha Vantage / GDELT / SEC layers leave **most events unknown** for public-news cleanliness.
- **Unknown is never clean** — cannot treat missing news metadata as absence of confounds.
- **Non-top master-clean n = 0** — public-news-clean robustness for the main heterogeneity result remains **unresolved**.

## Why analyst consensus / price targets matter

- Finfluencers often **repackage** Wall Street ratings, upgrades, and price targets visible before upload.
- Dated analyst history (FMP / Finnhub when keys exist) supports **event-time alignment** tests.
- **Latest-only** consensus without event dates is **diagnostic_current_only** — not historical proof.

## Why market sentiment regimes matter

- Retail-facing finance content intensifies in **risk-on / high-VIX / drawdown** environments.
- VIX, SPY/QQQ trend, and drawdown features are **conditioning variables**, not causal instruments.
- They complement but do not replace the **market-implied confound screen** (pre-event return/volume quiet).

## Market-implied confounds ≠ news-clean evidence

- `market_quiet` flags low pre-event return/volume — a **sensitivity** layer only.
- Example: non-top + market_quiet 21D SPY BHAR ≈ **-0.56%** — **not** public-news-clean.
- Do not equate quiet markets with absence of Bloomberg/analyst/earnings information.

## What this pass tests

| Question | Module |
| --- | --- |
| Are calls aligned with dated analyst consensus? | `analyst_relay/` |
| Do returns vary by VIX / SPY regime? | `market_sentiment/` |
| Does snippet language look like relay or hype? | `transcript_narrative_relay/` |
| What share looks relay vs original-like? | `originality_taxonomy/` |
| Do YouTube features add predictive value over market baselines? | `incremental_predictive_value/` |

## Reproduction (RunPod / full data)

```bash
.venv/bin/python3 scripts/build_v2_analyst_relay_layer.py
.venv/bin/python3 scripts/build_v2_market_sentiment_regime_layer.py
.venv/bin/python3 scripts/build_v2_transcript_narrative_relay_layer.py
.venv/bin/python3 scripts/build_v2_information_originality_taxonomy.py
.venv/bin/python3 scripts/build_v2_incremental_predictive_value.py
```

Optional keys (never commit): `FMP_API_KEY`, `FINNHUB_API_KEY` in env or `/root/.config/fin496/*.env`.

## Claim discipline

- Strengthen: narrative-relay mechanism, sentiment conditioning, repackaging hypothesis.
- Do not claim: causal skill, tradability, full news-clean robustness, analyst snapshot as event-time proof.
