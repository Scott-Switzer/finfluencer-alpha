# V2 Causal Identification Memo

The v2 event study estimates abnormal returns by comparing realized stock returns
around YouTube recommendation events with modeled normal returns. It is not a
causal design.

Main identification threats:

- Simultaneity with existing news, price momentum, and retail attention.
- Creator selection into already-trending stocks.
- YouTube upload timestamps may lag recording or private preview timing.
- Repeated recommendation clusters can amplify a common underlying event.
- Retail attention and public information are hard to separate with free data.
- There is no random assignment of recommendations to tickers or dates.

The falsification tests in this folder should be interpreted as stress tests for
the causal story. Passing them would not prove causality; failing or weakening
them should narrow the claim to attention amplification and heterogeneous
association.
