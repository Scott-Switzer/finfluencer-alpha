# FNSPID verification (synthesis insert)

Both Hub CSVs were scanned (~15.5M primary + ~13.1M secondary rows). **All_external** did not add incremental event hits: audit found **644** secondary window matches but **0** new article keys vs primary (full dedupe overlap). **~79%** of recommendation events are **2024+**, outside FNSPID’s historical article range; all **340** FNSPID hits are **2020–2023**. Widening windows to ±60d adds only **9** events beyond ±1d — the binding constraint is **calendar era**, not window width.

After targeted unknown-news provider calls (≤100), the master panel reports **668** `unknown_news_coverage`, **461** `media_confounded`, **0** `multi_source_clean`. **Unknown is never clean.** Do not claim public-news-clean non-top robustness.
