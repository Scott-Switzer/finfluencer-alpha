# Event Validation Labeling Guide

Use `event_validation_sample.csv` for human review. Fill the blank label columns, then save a labeled copy as `event_validation_sample_labeled.csv`.

## Label Values

- `is_true_recommendation`: yes, no, unclear
- `recommendation_type`: buy, sell, short, hold, avoid, portfolio_update, price_target, earnings_reaction, news_reaction, macro_commentary, casual_mention, false_positive, unclear
- `direction`: positive, negative, neutral, unclear
- `time_horizon`: short_term, medium_term, long_term, unclear
- `conviction`: low, medium, high, unclear
- `evidence_quality`: strong, medium, weak
- `labeler_notes`: free text

Treat an event as `yes` only when the transcript window or surrounding context contains a concrete stock view or portfolio action attributable to the creator.
Use `no` for casual ticker mentions, news-only discussion, third-party attribution, or false-positive ticker extraction. Use `unclear` when the context is insufficient.
