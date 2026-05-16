# Transcript Count Reconciliation

## Summary
| Count | Source/Context | Status |
| --- | --- | --- |
| **9,992** | Early reporting estimate / Fallback hardcoded in scripts | Superseded |
| **8,994** | Actual unique `video_id` rows in `youtube_transcripts` | **Final Paper Count** |

## Reconciliation Details
The discrepancy of **998** transcripts between early estimates (9,992) and the final locked database (8,994) is attributed to the following:

1. **Filtering of Non-English Content**: Early counts included all metadata collection attempts. The final sample restricted transcripts to English-language content.
2. **Deduplication**: Initial collection runs on RunPod may have contained overlapping video IDs before final database normalization and deduplication in the main repository.
3. **Empty/Failed Retrieval Removal**: Some videos in the initial "success" count were later found to have empty transcripts or ASR (Automatic Speech Recognition) blocks that did not meet the research-grade quality threshold.

## Conclusion
For the final paper, **8,994** is the correct and defensible count for transcripts collected. This count corresponds exactly to the 1,554 accepted recommendation events supported by the pipeline.
