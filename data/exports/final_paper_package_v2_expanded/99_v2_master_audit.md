# V2 Master Audit

## Sample

- Transcript rows: `9,992`
- Accepted recommendation events: `2,341`
- Return matched 5D: `2299`

## Headline

- Full-sample 1D: `-2.4e-05`, p=`0.976636`
- Full-sample 5D: `0.000556`, p=`0.666561`
- Top-5 5D: `0.004234`, p=`0.017462`
- Non-top 5D: `-0.004733`, p=`0.008921`
- Low-lookahead 5D: `0.00188`, p=`0.3069`
- Duplicate-collapsed 5D: `0.00162`, p=`0.241189`
- Buy-only 5D: `0.001712`, p=`0.227842`
- Sell-only 5D: `-0.003482`, p=`0.244296`

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
