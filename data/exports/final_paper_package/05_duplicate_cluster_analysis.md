# Duplicate Cluster Analysis

| row_type | specification | horizon | n | mean | median | t_stat | p_value | bh_q_value | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overview | events |  | 1554 |  |  |  |  |  | event-level observations |
| overview | clusters |  | 1117 |  |  |  |  |  | creator+ticker+date clusters |
| overview | duplicate_clusters |  | 253 |  |  |  |  |  | cluster size greater than 1 |
| overview | max_cluster_size |  | 13 |  |  |  |  |  |  |
| overview | observations_removed_first_event_collapse |  | 437 |  |  |  |  |  |  |
| result | event_level | AR_0_1 | 1549 | 0.000016 | 0.000513 | 0.015 | 0.988189 |  | all events |
| result | event_level | AR_0_5 | 1536 | 0.003269 | -0.000162 | 1.868 | 0.061830 |  | all events |
| result | first_event_collapse | AR_0_1 | 1112 | 0.001345 | 0.000561 | 1.387 | 0.165527 |  | first event per cluster |
| result | first_event_collapse | AR_0_5 | 1104 | 0.004058 | -0.000057 | 2.183 | 0.029023 |  | first event per cluster |
| result | max_quality_per_cluster | AR_0_1 | 1112 | 0.001345 | 0.000561 | 1.387 | 0.165527 |  | highest quality event per cluster |
| result | max_quality_per_cluster | AR_0_5 | 1104 | 0.004058 | -0.000057 | 2.183 | 0.029023 |  | highest quality event per cluster |
| result | cluster_mean_return | AR_0_1 | 1112 | 0.001345 | 0.000561 | 1.387 | 0.165527 |  | mean return within each cluster |
| result | cluster_mean_return | AR_0_5 | 1104 | 0.004058 | -0.000057 | 2.183 | 0.029023 |  | mean return within each cluster |
