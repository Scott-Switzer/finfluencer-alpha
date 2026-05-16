# V2 Quality Sensitivity Memo

The live DB has actionability and confidence proxy fields, but no human-audited
quality score for every v2 event. Actionability score is stored on a low
integer-like proxy scale in the live DB, so this audit uses proxy thresholds
from 2.0 through 4.0 rather than 0-100 score cutoffs.

- Events with non-null actionability score: `2341`
- Mean actionability score: `2.99`
- Median actionability score: `3.00`

Quality splits should be interpreted as extraction-sensitivity checks, not proof
that high-quality recommendations cause returns.
