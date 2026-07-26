# ADR 0003: Packet-specific quote-ID schema

Status: accepted
Date: 2026-07-26

Every generation request enumerates the evidence packet's valid quote IDs in
the strict JSON Schema. This prevents the model from confusing passage IDs with
quote IDs and leaves the deterministic validator as a second independent check.
The first 30-call canary exposed this defect; the corrected canary passed 30/30.
No regeneration or answer repair is added.
