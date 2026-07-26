# R1.1 PDF Ingestion Result

Date: `2026-07-25`  
Source: `preparedbc_wildfire_guide`  
Input: PreparedBC Wildfire Preparedness Guide

## Learning objective

Understand and verify the exact page records that later chunking and retrieval
will consume.

## Implemented

- source metadata loaded from the approved registry;
- PDF header, existence, encryption and page-count validation;
- SHA-256 document identity;
- one record per human-visible, one-indexed PDF page;
- title, publisher, canonical URL, temporal class and authority on every record;
- UTC retrieval timestamp;
- explicit `text_extracted`, `empty`, or `suspect_text` status;
- quality flags for unmapped PDF font glyphs and suspiciously short text;
- deterministic JSON Lines output;
- focused unit and real-document integration tests.

## Extractor experiment

The first implementation used `pypdf` text extraction. On visible PDF page 6,
it produced:

```text
B
ottled water
```

instead of:

```text
Bottled water
```

`pdfplumber` preserved the phrase correctly, so extraction was changed to
`pdfplumber`. `pypdf` remains useful for structural validation and test-PDF
creation.

## Verified result

```text
Pages: 20
Clean text pages: 17
Review-required pages: 3
Empty pages: 0
```

Flagged pages:

- Page 1: unmapped custom-font glyphs on the cover.
- Page 5: infographic text includes unmapped custom-font glyphs.
- Page 19: intentionally sparse notes page.

Visible checks:

- Page 6 contains `Bottled water` and `personal medications`.
- Page 11 contains `leave IMMEDIATELY`.

## Decision

Do not send `suspect_text` pages directly into the embedding pipeline. They
must be repaired with OCR, represented through a verified alternative, or
explicitly excluded with an audit record.

## Next R1 learning slice

Design chunks from the 17 clean page records and compare:

- naive fixed-character chunks;
- paragraph-aware chunks;
- parent-page provenance.

No embedding model should be selected until the chunk objects are inspectable
and citations can reconstruct the source page.
