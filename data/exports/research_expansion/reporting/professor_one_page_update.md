# Professor One-Page Update

**What I am studying**
Whether YouTube financial influencers ('finfluencers') generate tradeable alpha or merely attention-driven price movements.

**Why it fits FIN 496**
Combines algorithmic data collection, NLP event extraction, event-study methodology, portfolio backtesting, and robust statistical inference.

**What data I collected**
~11,922 videos from 22+ finance YouTube channels. ~6,384 transcripts. 2,147 extracted recommendation events spanning 22 tickers and 2020–2026.

**How the model works**
Deterministic rules scan transcript windows for explicit buy/sell/avoid/price-target language. Events are matched to next-trading-day yfinance prices. Abnormal returns computed vs. SPY, QQQ, IWM, and sector ETFs.

**How I test alpha**
Event-window abnormal returns, bootstrap/permutation inference, Benjamini-Hochberg FDR correction, and investable equal-weight portfolio backtests with transaction costs.

**What I found so far**
Preliminary descriptive statistics show mixed abnormal returns across horizons. Short-term attention effects appear stronger than medium-term alpha. Portfolio hit rates are modest. Results are prototype-grade and require Bloomberg validation.

**What is still provisional**
- yfinance market data (not institutional grade)
- Rule-based pseudo-labels (no human ground truth)
- Overlapping events not fully correlated in SEs

**What I am doing next**
- Attempt Bloomberg data acquisition
- Human validation subsample if time permits
- Final statistical write-up