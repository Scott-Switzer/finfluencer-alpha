# Transcript Count Reconciliation

## Summary
| Count | Source/Context | Status |
| --- | --- | --- |
| **9,992** | Current live RunPod DB transcript rows / unique transcript videos | Expanded live DB, not final paper sample |
| **8,994** | Historical locked-package transcript count in committed final artifacts | Sample-lock limitation |
| **1,554** | Committed event IDs in `data/exports/research_grade_analysis/05_event_timeline_dataset.csv` and `locked_sample/01_locked_event_manifest.csv` | Manifest-supported final event sample |
| **2,341** | Current live RunPod DB recommendation-event rows | Expanded live DB, not final paper sample |

## Reconciliation Details
The discrepancy between **9,992** current live DB transcript rows and the
historical **8,994** locked-package transcript count cannot be fully reproduced
from committed files. The current DB also reports 9,977 successful transcript
rows and 9,972 rows with strict `full_text > 50`, while inspected language and
text filters do not produce 8,994.

The committed final paper package does have a reproducible event lock:
`locked_sample/01_locked_event_manifest.csv` contains the 1,554 event IDs used by
the committed final-package SEC, free-news scaffold, and table artifacts. The
current live DB contains 2,341 accepted/extracted recommendation-event rows; that
larger panel has not been reconciled into the final paper package.

## Conclusion
For the final paper, cite **1,554 manifest-supported transcript-backed
recommendation events** as the locked event sample. Cite **8,994 transcripts**
only as a historical locked-package count and disclose the sample-lock
limitation. Do not cite **9,992 transcripts** or **2,341 recommendation events**
as final paper counts unless a new explicit lock is created and the empirical
package is regenerated from that lock.
