# Event Funnel Reconciliation

- Candidate transcript windows: **12,083**.
- DB transcript recommendation rows: **2,341**.
- Auto-label counts: yes=785, no=1,301, unclear=255.
- Conservative prior clean row-level events: **562**.
- Corrected unique video/ticker/date events for return testing: **473**.
- Duplicate video/ticker/date groups in conservative clean rows: **63** with **89** extra repeated rows.

## Audit Finding
- The OpenCode 2,078 clean-event figure is not a defensible clean-label count for the current RunPod state.
- The research-expansion branch bypassed the earlier auto-label safeguards (`is_true_recommendation`, `needs_review`, evidence quality, and exclusion reasons) and treated most DB recommendation rows as clean.
- For the paper, cite **562** conservative row-level pseudo-labeled clean events and **473** unique video/ticker/date events for event-study returns.
- The corrected return pipeline below uses the 473 deduped events to avoid overweighting repeated mentions of the same ticker in the same transcript.
