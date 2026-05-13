# Transcript Collection Methodology and Limitations

## Overview
The project successfully aggregated metadata for over 6,400 financial influencer videos. However, expanding the transcript sample from the initial baseline of 1,000 videos encountered significant infrastructure and platform constraints.

## Automated Collection Channels
Two primary automated collection routes were implemented and tested:

1. **API Provider Route (YouTubeTranscript.dev)**:
   - This route was highly functional but constrained by credit limits.
   - It successfully imported 7 transcripts earlier in the collection phase before reaching a `402 Payment Required` status.
   
2. **Rotating Proxy Route (Webshare)**:
   - A robust infrastructure for proxy rotation and aggregation was implemented to support direct YouTube fetching.
   - **Performance**: In final testing, a pool of 22 proxies (Direct and Backbone) was evaluated.
   - **Results**: 0 out of 22 proxies were usable for transcript collection due to persistent `ProxyError` and tunnel connection failures.
   - **Diagnostic Run**: A controlled batch of 3 videos resulted in 3 transient failures and 0 imports.

## Methodological Limitations
These results highlight a critical methodological constraint: **platform-level transcript availability and automated retrieval blocking.** 

As a result:
- The findings of this project should be framed as **transcript-supported and reproducible**, but representative of the available sample rather than a full-universe causal analysis.
- The evidence is **exploratory and descriptive**, grounded in the high-fidelity data obtained for the 1,000-video sample.
- Sample expansion for specific high-priority creators (e.g., Joseph Carlson, Ticker Symbol: YOU) requires targeted manual enrichment or fresh residential proxy pools.

## Manual Enrichment
To mitigate these gaps, a manual collection workflow has been established, allowing for targeted enrichment of the most critical 2022-2023 video windows.
