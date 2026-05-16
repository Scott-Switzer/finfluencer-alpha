# V2 Factor Interpretation

Factor adjustment uses free Kenneth French daily factors downloaded in memory.
No paid data, WRDS, Bloomberg, or `.env` inputs are used.

- FF5 top-5 5D alpha: `0.000543` with p=`0.734839`.
- FF5 non-top 5D alpha: `-0.001326` with p=`0.446572`.

Interpretation should follow the table: if factor adjustment reduces the
top-5 estimate or leaves non-top negative, the paper should frame the finding as
attention concentration rather than broad alpha.
