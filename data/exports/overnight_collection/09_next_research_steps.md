# Next Research Steps

Generated: 2026-05-14T15:57:09Z

## Recommendation
- Stop collecting for now. The X budget cap was reached successfully and the current dataset is sufficient for the next empirical pass.
- Audit X source quality before spending more: source mix, account-level yield, ticker density, language/date coverage, engagement coverage, and market-control composition.
- Inspect classifier label distribution before treating the 1,462 X recommendation events as research events.
- Build and review YouTube + X overlap tables, especially no-attention, pre-attention, same-day attention, post-attention, and persistent-attention categories.
- Run X-only, YouTube-only, and YouTube+X event studies after quality checks pass.
- Keep claims conservative: rule-based pseudo-labels, prototype-grade market data, descriptive evidence only, no causality, no human validation, and no tradable-alpha claim.

## Suggested Order
1. Validate X source quality and remove obvious off-topic/control leakage if needed.
2. Review X classifier examples by label and ticker, with special focus on portfolio disclosures, watchlists, news-only posts, and meme/noise posts.
3. Freeze a clean X event sample and document exclusions.
4. Re-run integrated event inventory and overlap summaries.
5. Run event studies with SPY, QQQ, IWM, and sector adjustments where available.
6. Run robustness checks and only then decide whether more collection is worth the cost.
