# V2 Long-Horizon Return Interpretation

## all
- 5D: mean SPY-adjusted BHAR `0.000635`, p `0.619606`, right-censored `23`
- 21D: mean SPY-adjusted BHAR `0.003173`, p `0.239438`, right-censored `149`
- 63D: mean SPY-adjusted BHAR `0.042903`, p `0.000000`, right-censored `362`
- 126D: mean SPY-adjusted BHAR `0.084560`, p `0.000000`, right-censored `730`
- 252D: mean SPY-adjusted BHAR `0.157459`, p `0.000000`, right-censored `1084`
- 504D: mean SPY-adjusted BHAR `0.253685`, p `0.000000`, right-censored `1601`

## top5
- 5D: mean SPY-adjusted BHAR `0.004406`, p `0.013094`, right-censored `6`
- 21D: mean SPY-adjusted BHAR `0.017313`, p `0.000002`, right-censored `69`
- 63D: mean SPY-adjusted BHAR `0.092714`, p `0.000000`, right-censored `179`
- 126D: mean SPY-adjusted BHAR `0.174241`, p `0.000000`, right-censored `362`
- 252D: mean SPY-adjusted BHAR `0.291735`, p `0.000000`, right-censored `566`
- 504D: mean SPY-adjusted BHAR `0.433119`, p `0.000000`, right-censored `891`

## non_top
- 5D: mean SPY-adjusted BHAR `-0.004715`, p `0.008177`, right-censored `17`
- 21D: mean SPY-adjusted BHAR `-0.016889`, p `0.000018`, right-censored `80`
- 63D: mean SPY-adjusted BHAR `-0.027767`, p `0.000001`, right-censored `183`
- 126D: mean SPY-adjusted BHAR `-0.042674`, p `0.000000`, right-censored `368`
- 252D: mean SPY-adjusted BHAR `-0.033046`, p `0.003600`, right-censored `518`
- 504D: mean SPY-adjusted BHAR `-0.000886`, p `0.959163`, right-censored `710`

## buy
- 5D: mean SPY-adjusted BHAR `0.001785`, p `0.204642`, right-censored `21`
- 21D: mean SPY-adjusted BHAR `0.006180`, p `0.028031`, right-censored `120`
- 63D: mean SPY-adjusted BHAR `0.045528`, p `0.000000`, right-censored `277`
- 126D: mean SPY-adjusted BHAR `0.088600`, p `0.000000`, right-censored `574`
- 252D: mean SPY-adjusted BHAR `0.166941`, p `0.000000`, right-censored `851`
- 504D: mean SPY-adjusted BHAR `0.262210`, p `0.000000`, right-censored `1256`

## sell
- 5D: mean SPY-adjusted BHAR `-0.003409`, p `0.252562`, right-censored `2`
- 21D: mean SPY-adjusted BHAR `-0.007404`, p `0.296817`, right-censored `29`
- 63D: mean SPY-adjusted BHAR `0.033669`, p `0.002627`, right-censored `85`
- 126D: mean SPY-adjusted BHAR `0.070348`, p `0.000007`, right-censored `156`
- 252D: mean SPY-adjusted BHAR `0.124106`, p `0.000000`, right-censored `233`
- 504D: mean SPY-adjusted BHAR `0.223700`, p `0.000000`, right-censored `345`

## SEC_clean
- 5D: mean SPY-adjusted BHAR `0.004055`, p `0.005588`, right-censored `5`
- 21D: mean SPY-adjusted BHAR `0.009176`, p `0.005451`, right-censored `41`
- 63D: mean SPY-adjusted BHAR `0.036275`, p `0.000000`, right-censored `167`
- 126D: mean SPY-adjusted BHAR `0.078248`, p `0.000000`, right-censored `383`
- 252D: mean SPY-adjusted BHAR `0.153658`, p `0.000000`, right-censored `598`
- 504D: mean SPY-adjusted BHAR `0.245064`, p `0.000000`, right-censored `914`

Long-horizon coverage is explicitly censored: `end_of_sample` has `2322` returns and `0` right-censored rows.

Interpret these estimates as event-time associations. They are not causal proof and do not establish tradable alpha without separate portfolio, cost, and public-news controls.
