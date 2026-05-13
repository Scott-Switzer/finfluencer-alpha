# Final Claims Guardrail

## Claims Supported by Evidence
- 'The dataset contains N transcript recommendation events across K creators and M tickers.'
- 'Mean abnormal return for horizon H was X% with a standard error of Y% using yfinance prototype data.'
- 'The equal-weight portfolio generated a Sharpe ratio of Z over horizon H before transaction costs.'

## Claims Not Supported
- 'Finfluencers beat the market.' (requires causal inference and institutional data)
- 'These recommendations are alpha-generating.' (requires out-of-sample tradable backtest)
- 'Labels are accurate.' (requires human ground truth)

## Claims Requiring Bloomberg
- Precise abnormal returns with split/dividend adjustments
- Intraday execution analysis
- Institutional-grade survivorship-bias-free data

## Claims Requiring Human Validation
- Classifier precision / recall
- False-positive rate of event extraction
- Label agreement between human and algorithm

## Exact Language to Use
- 'using prototype yfinance market data'
- 'rule-generated pseudo-labels'
- 'AI-assisted adjudication, not human ground truth'
- 'descriptive abnormal returns'

## Exact Language to Avoid
- 'alpha' without benchmark and cost adjustments
- 'causal' or 'causality'
- 'human-validated'
- 'Bloomberg-grade' or 'institutional-grade' when using yfinance