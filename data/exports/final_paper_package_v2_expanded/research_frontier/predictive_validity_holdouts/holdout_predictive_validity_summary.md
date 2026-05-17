# Holdout Predictive Validity

# Holdout predictive validity

| split | target | model | status | n_train | n_test | accuracy | auc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| random_70_30 | non_top_underperform | logistic | computed | 1625 | 697 | 0.830703012912482 | 0.8991778663909812 |
| time_ordered | non_top_underperform | logistic | computed | 1625 | 697 | 0.7862266857962698 | 0.8720388607931859 |
| creator_out_top3 | non_top_underperform | logistic | computed | 1268 | 1054 | 0.7969639468690702 | 0.88582113110415 |
| ticker_out_top5 | non_top_underperform | logistic | computed | 907 | 1415 | 0.8968197879858657 | 0.9351474543785333 |
| year_out_latest | non_top_underperform | logistic | computed | 1768 | 554 | 0.7851985559566786 | 0.8760027903732124 |

## Interpretation
- If **non_top_underperform** AUC collapses under **ticker_out**, the pattern is **ticker/salience-driven**, not a portable cross-sectional rule.
- High AUC under random/time split but failure under ticker-out → do **not** claim tradable non-top shorts.
