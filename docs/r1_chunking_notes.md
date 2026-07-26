# R1.2 Structure-Aware Chunking

> Historical executed subsystem note. Current corpus invariants are recorded in
> `docs/TECHNICAL_HANDBOOK.md`.

Date: `2026-07-25`

## Purpose

Convert validated page records into smaller retrieval units without breaking
page-level citations or indexing known-bad extraction.

## Contract

- a chunk belongs to exactly one page;
- a chunk inherits the page's source, document hash, URL, authority and time;
- chunk IDs are deterministic and one-indexed within each page;
- only `text_extracted` pages are eligible;
- known running headers and page-number footers are removed;
- headings, bullet starts and sentence-ending lines are preferred boundaries;
- the default target is 900 characters;
- units shorter than 80 characters are merged with neighboring context;
- no arbitrary overlap is added in v1.

An individual logical unit may exceed the target rather than being cut in the
middle. The limit is therefore a target, not a destructive hard boundary.

## Why not fixed-character slicing?

Fixed slicing can separate an instruction from its condition, split a bullet
item, or cut the phrase used for retrieval. The v1 chunker packs logical units
until adding the next unit would exceed the target.

## Why not overlap yet?

Overlap duplicates evidence and can inflate retrieval scores without adding
new information. FireLens first preserves logical boundaries and evaluates
retrieval. Overlap will be introduced only if the benchmark demonstrates a
specific boundary-recall problem.

## Known limitation

PDF extraction does not reliably reconstruct complex multi-column reading
order. Chunking preserves extracted evidence; it does not repair layout.
Pages with known extraction defects remain excluded for OCR or manual repair.
