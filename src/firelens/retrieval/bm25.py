"""A small, deterministic BM25 retrieval baseline for FireLens chunks."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from firelens.ingestion.chunking import ChunkRecord
from firelens.ingestion.pdf import IngestionError

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
DEFAULT_K1 = 1.5
DEFAULT_B = 0.75


@dataclass(frozen=True)
class RetrievalResult:
    """One ranked chunk plus the provenance required for a citation."""

    rank: int
    score: float
    chunk_id: str
    parent_record_id: str
    source_id: str
    title: str
    publisher: str
    canonical_url: str
    page_number: int | None
    section_title: str | None
    text: str
    source_type: str = "pdf"
    section_id: str | None = None
    locator: str | None = None


def tokenize(text: str) -> list[str]:
    """Normalize text into deterministic lowercase lexical tokens."""

    normalized = text.lower().replace("’", "'")
    return TOKEN_PATTERN.findall(normalized)


def load_chunk_records(path: Path) -> list[ChunkRecord]:
    """Load and validate retrieval chunks from JSON Lines."""

    records: list[ChunkRecord] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                records.append(ChunkRecord(**payload))
            except (TypeError, json.JSONDecodeError) as exc:
                raise IngestionError(
                    f"Invalid chunk record on JSONL line {line_number}: {path}"
                ) from exc

    if not records:
        raise IngestionError(f"No chunk records found: {path}")
    return records


class BM25Index:
    """Rank chunks by lexical relevance using Okapi BM25."""

    def __init__(
        self,
        records: Sequence[ChunkRecord],
        *,
        k1: float = DEFAULT_K1,
        b: float = DEFAULT_B,
        retrieval_texts: Sequence[str] | None = None,
    ) -> None:
        if not records:
            raise ValueError("BM25 requires at least one chunk.")
        if k1 <= 0:
            raise ValueError("k1 must be greater than zero.")
        if not 0 <= b <= 1:
            raise ValueError("b must be between zero and one.")

        chunk_ids = [record.chunk_id for record in records]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("BM25 chunk IDs must be unique.")

        if retrieval_texts is not None and len(retrieval_texts) != len(records):
            raise ValueError("retrieval_texts must align with BM25 records")
        self.records = tuple(records)
        self.k1 = k1
        self.b = b
        indexed_texts = retrieval_texts or [record.text for record in self.records]
        self._term_frequencies = [Counter(tokenize(text)) for text in indexed_texts]
        self._document_lengths = [
            sum(frequencies.values()) for frequencies in self._term_frequencies
        ]
        self._average_document_length = sum(self._document_lengths) / len(
            self._document_lengths
        )
        self._document_frequencies = self._calculate_document_frequencies()
        self._inverse_document_frequencies = {
            term: self._calculate_inverse_document_frequency(frequency)
            for term, frequency in self._document_frequencies.items()
        }

    def _calculate_document_frequencies(self) -> Counter[str]:
        frequencies: Counter[str] = Counter()
        for term_frequencies in self._term_frequencies:
            frequencies.update(term_frequencies.keys())
        return frequencies

    def _calculate_inverse_document_frequency(self, document_frequency: int) -> float:
        document_count = len(self.records)
        return math.log(
            1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
        )

    def _inverse_document_frequency(self, term: str) -> float:
        return self._inverse_document_frequencies.get(
            term, self._calculate_inverse_document_frequency(0)
        )

    def _score_document(self, query_terms: set[str], document_index: int) -> float:
        frequencies = self._term_frequencies[document_index]
        document_length = self._document_lengths[document_index]
        length_ratio = document_length / self._average_document_length
        score = 0.0

        for term in query_terms:
            term_frequency = frequencies.get(term, 0)
            if term_frequency == 0:
                continue

            denominator = term_frequency + self.k1 * (1 - self.b + self.b * length_ratio)
            score += self._inverse_document_frequency(term) * (
                term_frequency * (self.k1 + 1) / denominator
            )
        return score

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        """Return the highest-scoring chunks; a score is not answerability."""

        if top_k < 1:
            raise ValueError("top_k must be at least one.")

        query_terms = set(tokenize(query))
        if not query_terms:
            return []

        scored = [
            (self._score_document(query_terms, index), record)
            for index, record in enumerate(self.records)
        ]
        ranked = sorted(
            (item for item in scored if item[0] > 0),
            key=lambda item: (-item[0], item[1].chunk_id),
        )[:top_k]

        return [
            RetrievalResult(
                rank=rank,
                score=round(score, 6),
                chunk_id=record.chunk_id,
                parent_record_id=record.parent_record_id,
                source_id=record.source_id,
                title=record.title,
                publisher=record.publisher,
                canonical_url=record.canonical_url,
                page_number=record.page_number,
                section_title=record.section_title,
                text=record.text,
                source_type=record.source_type,
                section_id=record.section_id,
                locator=record.locator,
            )
            for rank, (score, record) in enumerate(ranked, start=1)
        ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search FireLens chunks with deterministic BM25 ranking."
    )
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    index = BM25Index(load_chunk_records(args.chunks))
    results = index.search(args.query, top_k=args.top_k)
    print(
        json.dumps(
            [asdict(result) for result in results],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
