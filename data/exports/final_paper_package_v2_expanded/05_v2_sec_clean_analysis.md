# V2 SEC-Clean Analysis

| specification | n_1d | mean_1d_ar | t_1d | p_1d | n_5d | mean_5d_ar | t_5d | p_5d | median_5d_ar | win_rate_5d | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-clean known subset | 716 | 0.002109 | 2.008 | 0.044670 | 713 | 0.003092 | 1.623 | 0.104494 | 0.001467 | 0.518934 | partial join: 1554 of 2341 v2 events have SEC flags |
| SEC-confounded known subset | 828 | -0.000170 | -0.189 | 0.850109 | 821 | 0.000706 | 0.368 | 0.712638 | -0.004962 | 0.449452 | partial join: 1554 of 2341 v2 events have SEC flags |

SEC flags are joined from v1 by event_id. Events unique to v2 are not SEC-audited in this pass, so this is a partial robustness check.
