# Final Results Section Draft

This study asks whether transcript-supported YouTube finance recommendations
are associated with short-window abnormal stock returns. The locked sample
contains 9,992 transcripts and 1,554 accepted recommendation events across 35
creators and 23 tickers. X/Twitter data is excluded.

The canonical yfinance baseline shows a positive 1D abnormal return
(`mean=0.002728`,
`p=0.001149`) and a positive 5D
abnormal return (`mean=0.005236`,
`p=0.001396`). The result is more
fragile in robustness tests: expanded all-event coverage weakens, high-quality
A/B events are not significant, and the non-top-ticker cut flips negative.

The low-lookahead sample remains positive over 5D, which supports the claim
that the association is not solely an artifact of same-day upload timing. SEC
EDGAR filing flags identify 833 events with nearby material
filings, but SEC-only flags are not full news controls. Factor adjustment is
computed. Intraday testing is limited to recent yfinance coverage
(`covered events=153`), so it is diagnostic rather than
full-sample evidence. Calendar-time portfolio status: computed.

The final interpretation is conservative: YouTube recommendations are
associated with short-window abnormal returns in the locked transcript sample,
but the evidence points toward attention/momentum amplification concentrated in
major names rather than broad, tradable, causal alpha.
