# Table 7. Calendar-time HAC factor regressions

| strategy                      | holding_trading_days | model   | n_days | alpha_daily | alpha_ann_approx | alpha_t_hac | alpha_p_value |
| ----------------------------- | -------------------- | ------- | ------ | ----------- | ---------------- | ----------- | ------------- |
| long_all_buy                  | 5                    | FF5_MOM | 1534   | 0.017%      | 4.4%             | 0.4322      | 0.665593      |
| long_all_buy                  | 21                   | FF5_MOM | 1534   | 0.049%      | 13.2%            | 1.1872      | 0.235164      |
| short_non_top_buys_diagnostic | 5                    | FF5_MOM | 1272   | -0.030%     | -7.4%            | -0.8314     | 0.405753      |
| short_non_top_buys_diagnostic | 21                   | FF5_MOM | 1272   | -0.040%     | -9.5%            | -1.4136     | 0.157484      |
| long_top5_buys_only           | 5                    | FF5_MOM | 1534   | 0.004%      | 1.1%             | 0.0921      | 0.926633      |
| long_top5_buys_only           | 21                   | FF5_MOM | 1534   | 0.043%      | 11.6%            | 0.9358      | 0.349363      |
