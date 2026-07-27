# ADR 0008: Retain the narrow custom pipeline over a RAG framework

Status: accepted
Date: 2026-07-26

## Context

LangChain, Haystack, and LlamaIndex can reduce boilerplate for generic model and
retriever composition. FireLens, however, depends on local provenance,
OpenRouter-only provider calls, generalized RRF diagnostics, packet-specific
quote schemas, typed abstention, exact-quote validation, and benchmark stage
observations.

## Decision

V1.1 retains the existing custom Python component boundaries. Refactoring is
limited to small typed records, explicit stage functions, shared provider
transport, and direct internal observations. No orchestration framework,
vector database, or agent runtime is added.

A future framework adapter is acceptable only behind the existing provider or
retrieval protocol. It must pass the same offline suite and governed benchmark,
preserve OpenRouter model identity and provider controls, expose the same stage
diagnostics, introduce no fallback, and demonstrate a material maintenance
benefit.

## Consequences

The code remains more application-specific, but the evidence and failure
semantics stay visible and dependency surface remains small. Framework features
can still be studied independently without coupling release qualification to a
large migration.
