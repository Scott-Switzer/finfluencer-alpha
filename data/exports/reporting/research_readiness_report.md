# Research Readiness Report

- Overall readiness: **yellow**
- Available transcripts: 1000
- Transcript-supported events: 495
- Market-data matched events: 133
- Clean-event reference count: 134
- Market match rate against the selected clean-event source: 99.3%

## Green: Defensible Now

- The local database supports descriptive statements about the caption-available YouTube sample.
- There are 495 transcript-supported recommendation events in the database.
- Market-data matching exists for 133 events in `/Users/scottthomasswitzer/Desktop/FIN496CAPSTONE/data/exports/expanded_robustness/expanded_event_study_results.csv`.

## Yellow: Usable With Limitations

- Associational daily or robustness conclusions are usable only with explicit caveats about interim market data, transcript coverage, and automatic event labeling.
- The largest creator contributes 76 events (15.4%) when transcript-supported events are grouped by creator.
- Transcript coverage is uneven enough to flag: year_coverage_dispersion, creator_coverage_gaps.

## Red: Not Defensible Yet

- Representative claims about all finance-influencer videos are not defensible until transcript missingness is better characterized or reduced.
- Causal claims that recommendations moved prices are not defensible from the current design.
- Cross-platform claims about X leading or lagging YouTube are not defensible while X remains undercovered locally.

## Event Composition

### Events By Creator

- HyperChange: 76
- Ticker Symbol: YOU: 64
- Financial Education: 56
- Sasha Yanshin: 48
- Joseph Carlson: 44
- ZipTrader: 29
- New Money: 28
- Everything Money: 27
- Chicken Genius Singapore: 24
- Tom Nash: 18
- Ale's World of Stocks: 16
- Meet Kevin: 10
- STOCK UP! with LARRY JONES: 10
- The Plain Bagel: 10
- Kenan Grace: 8
- Dumb Money Live: 6
- Graham Stephan: 6
- Best of Us Investors: 4
- Bloomberg Television: 3
- CNBC Television: 3

### Events By Year

- 2020: 17
- 2021: 16
- 2022: 53
- 2023: 106
- 2024: 168
- 2025: 81
- 2026: 54

## Coverage And Validation

- Transcript coverage by the audited 2020-2023 period: 41.4%
- Undercovered years: 2022, 2023
- Low-coverage creators: HyperChange, Joseph Carlson, New Money, Sasha Yanshin, Ticker Symbol: YOU, ZipTrader
- Manual validation status: manual_validated_candidates=0; labeled_validation_rows=0

## Missing-Data Threats

- Transcript availability bias can overweight creators and years with public caption access.
- Creator concentration can make aggregate findings depend on a small number of channels.
- Year and time-period imbalance can confound any temporal comparison.
- Current engagement fields are snapshots, not historical engagement at event time.
- YouTube publication timestamps are not exact investor-attention timestamps.
- Classifier outputs remain partially automated and manual validation is limited or absent when no labeled review file exists.
- X undercoverage blocks a credible cross-platform lead-lag conclusion.
- Ticker false positives and overlapping recommendations can contaminate event identity.
- Survivorship bias remains possible if disappeared or uncollected channels differ from the observed set.
- Market-data matching quality remains incomplete whenever clean events exceed matched event-study rows.

## What Should Happen Before Final Paper Claims

- Keep transcript collection bounded, evidence-driven, and benchmarked against block/error outcomes.
- Prioritize manual validation for high-leverage creators, undercovered years, and ticker-false-positive edge cases.
- Treat expanded robustness as robustness-only until market data and validation are stronger.
- Use Bloomberg-grade joins before final inferential claims.

## Research Framing

- Current claims should be framed as exploratory, descriptive, and robustness-oriented.
- Final causal or representative claims require stronger coverage, validation, and market-data support.
