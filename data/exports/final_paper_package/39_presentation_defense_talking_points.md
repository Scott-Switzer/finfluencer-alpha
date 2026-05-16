# 60-Second Defense Memo: FIN 496 Capstone

**Objective**: Summarize the empirical defense package for the professor.

**1. The "What"**:
The committed locked artifact package analyzes 8,994 YouTube transcripts from 35 financial influencers and 1,554 recommendation events, but the current RunPod DB has moved beyond those counts. Cite the locked counts only with the reconciliation caveat in `40_runpod_count_reconciliation_audit.md`.

Stronger wording: the 1,554 event panel is manifest-supported; the 8,994
transcript count is a historical locked-package count and not fully
reproducible from committed transcript IDs.

**2. The "Headline"**:
In the committed primary 16-ticker baseline, the 5-day abnormal return is **0.52% (p=0.001)**. The result holds under upload-timing and SEC-only filters, but the free-news layer is simulated and diagnostic only; the Free-News clean 5D result is economically negligible and statistically meaningless (n=267, mean=0.003%, p=0.995).

**3. The "Fragility"**:
The association is not broad-market alpha. It is highly concentrated in "Top 5" tech tickers (NVDA, TSLA, AAPL, AMD, AMZN). When these are removed, the association reverses (**-0.68%, p=0.002**), suggesting a "pump and fade" dynamic for the broader market.

**4. The "Verdict"**:
The phenomenon is **attention amplification**. Social media creators synchronize with and amplify existing momentum in mega-cap technology stocks. While the committed artifacts show a statistically significant association, high transaction costs (decays at 25 bps) make it unlikely to be a source of tradable idiosyncratic alpha.

**5. Bloomberg Caveat**:
The package has Bloomberg CSV templates, but it is not Bloomberg-validated and should not be described as final until the sample-lock reconciliation is resolved and empirical news data are applied.
