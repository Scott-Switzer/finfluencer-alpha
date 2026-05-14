# Professor Update

My FIN 496 capstone asks whether YouTube finfluencer stock recommendations are associated with benchmark-adjusted abnormal returns or whether they mostly reflect attention around stocks already being discussed.

The reconciled RunPod dataset has 11,922 YouTube videos, 9,747 successful transcripts, and 9,742 transcripts with more than 50 characters of text. The conservative rule-labeling pipeline produces 562 row-level clean pseudo-labeled events, which I deduplicate to 473 video/ticker/date events for return testing.

The method combines NLP-style deterministic event extraction, next-trading-day event windows, SPY/QQQ/IWM benchmark adjustment, portfolio backtests, and robustness checks. The classifier caveat is important: these are rule-generated pseudo-labels, not human ground truth. The available AI audit is AI-assisted and cannot be described as human validation.

What changed from the prior results is that the large OpenCode clean-event count was not defensible as a clean-label count; it bypassed earlier validation safeguards and overweighted repeated ticker mentions. The verified audit uses the conservative deduped event set.

Before final presentation, the main next step is to decide whether to keep yfinance as explicitly prototype-grade or replace the market data with Bloomberg-adjusted prices if access is available.
