# YouTube Transcript Strategy

## Why Transcripts Matter

YouTube titles and descriptions are only screening fields. They can identify likely stock videos, but they often omit the actual recommendation language, risk discussion, valuation logic, and timing. High-confidence recommendation classification needs creator-authored evidence from a transcript, X text, or manual review.

## Official API Limitations

The official YouTube captions API is not a simple public transcript API. `captions.list` costs 50 quota units and returns caption-track metadata, not caption text. `captions.download` costs 200 quota units and requires authorization plus permission to edit the video. Therefore, official caption download is not a scalable method for public third-party videos.

The repo should not claim that public YouTube transcripts are automatically available through a YouTube Data API key.

## Ingestion Design

Transcript ingestion should be designed around local/manual transcript files, an optional future transcript provider, a transcript availability flag, and fallback to manual validation when a transcript is missing.

The fallback hierarchy is:

1. Metadata only for discovery.
2. Transcript if available for classification.
3. Manual validation for high-impact or ambiguous videos.

Missing transcripts should not block metadata collection. They should lower event confidence unless manual review supplies explicit recommendation evidence.

## Evidence Snippets

Transcript snippets should be stored as short auditable evidence around the detected recommendation phrase, with timestamp start and end when available. Exports should carry evidence snippets and metadata, not bulky full transcript text.

Auto-generated captions should be flagged separately from creator-uploaded captions. Non-English transcripts should be flagged with transcript language and excluded from the main English-language classifier unless a reliable translation workflow is documented.

## Comments Are Different

Comments are audience reaction data, not recommendation source data. They can support attention-spillover analysis, but they should not be treated as creator recommendation language.

## Reproducibility

Because transcript availability can change, store the transcript source, availability flag, language, capture date, and evidence snippets used for classification. If a transcript provider is added later, keep it optional and do not make fragile scraping a core dependency of the project.
