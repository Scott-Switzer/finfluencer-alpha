# Exhibit — literature positioning


| paper_or_stream | data_source | event_definition | return_method | controls | main finding | how_this_project_improves_or_differs | remaining_limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Barber & Odean (attention/performance); correlates | retail trading literature | buys after attention spikes | raw/calendar | limited | attention can drive flows | links influencer salience to liquid mega-caps | not YouTube-specific |
| Finfluencer working papers / preprints | social posts / surveys | post-level recommendations | mixed event windows | varies | heterogeneity common | full transcript lock + SEC/news confounds | causal skill still blocked |
| Event-study surveys (MacKinlay; Kothari-Warner) | generic | discrete events | CAR/BHAR | factor models | benchmark | uses SPY-BHAR + matched diagnostics | overlapping windows; public news gaps |
| News-confound / sentiment | news archives | text dates | event time | text + fundamentals | confounds alter inference | multi-provider + FNSPID historical slice | unknown news never “clean” |

This capstone adds conservative **news_confound_master** classification, **FNSPID** historical media coverage, and explicit **claim discipline** (no broad alpha, no uniform creator skill).

