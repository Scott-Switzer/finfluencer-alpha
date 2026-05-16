# Final Methodology Section Draft

Events are accepted only when a transcript evidence window supports a
ticker-level directional recommendation. Event windows are aligned to the first
available trading day on or after the upload date using local yfinance daily
prices. Abnormal returns are computed against SPY for event-study tables, with
additional robustness layers for timing, duplicate clusters, SEC filing
confounds, factor adjustment, intraday coverage where free data exists, and
calendar-time portfolio construction.

Bloomberg is not used in the current build. Manual Bloomberg CSV templates and
validators are prepared so a later school-terminal pull can replace yfinance
prices and populate full news/earnings/analyst controls.
