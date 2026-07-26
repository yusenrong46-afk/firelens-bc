# ADR 0002: Versioned single-turn API

Status: accepted
Date: 2026-07-26

The supported HTTP surface is versioned under `/api/v1`. V1 accepts only a
single question. Accepted claims expose local support pairs and evidence
passages so the frontend never needs a second retrieval request or invents
verification state. Debug retrieval is not a production UI dependency.
