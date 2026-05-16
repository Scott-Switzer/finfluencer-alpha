# Intraday Methodology and Limitations

The intraday layer uses yfinance 60-minute bars with `period=60d` and
`prepost=True` where Yahoo coverage exists. It intentionally does not attempt
full-sample intraday coverage because free yfinance intraday history is limited
to recent observations. Alpha Vantage is scaffolded as an optional future hook
when `AV_API_KEY` is present in the shell environment; this script does not read
.env and does not print keys.

Computed windows are attempted for upload-to-30m, upload-to-60m,
upload-to-2h, upload-to-same-day-close, next-open-to-60m, next-open-to-close,
after-close-to-next-open gap, and before-open-to-open-plus-60m. Missing rows are
left blank rather than fabricated.
