# Factor Methodology

Daily Kenneth French FF3, Momentum, and FF5 files are downloaded from the
official Data Library when available. For each event and horizon, ticker-level
factor loadings are estimated on up to 130 pre-event trading days with at least
40 matched observations. Event-window factor-adjusted abnormal return is:

`stock return - RF - estimated expected excess return from pre-event betas`.

This is a free-data robustness layer. It is not a substitute for later
Bloomberg total-return validation, but it directly addresses market/factor
exposure with currently available data.
