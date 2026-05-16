# Real News Layer Interpretation

The news layer ran provider diagnostics and a stratified real GDELT probe. It
does not simulate news. It stores compact metadata only: counts, domains,
truncated titles, dates, query status, and reason codes.

- Probe events: `40`
- Successful GDELT queries: `1`
- Probe success rate: `0.025`
- Full 2,341-event run status: `not run because probe success was below 50%`

Do not cite the news-clean event study as full-sample evidence unless the full
provider layer succeeds. Failed providers imply `unknown`, not `clean`.
