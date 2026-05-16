# V2 Expanded Locked Sample

V2 is the expanded live RunPod DB primary candidate sample. It uses compact
manifests for current transcript metadata and accepted/extracted recommendation
events without exporting transcript text, raw API payloads, or raw database
files.

V1 is retained under `data/exports/final_paper_package/` as the historical
locked artifact sample and benchmark. V2 should become primary only if the
validator passes or partial-passes with documented caveats.

The v2 empirical claim depends on the v2 results, not the v1 result strength.
The v2 package must not use simulated free-news outputs as evidence. Real
public-news exclusion requires a separate provider implementation and audit.
