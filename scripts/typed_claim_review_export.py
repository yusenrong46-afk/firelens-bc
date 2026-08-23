"""Export a human review queue for pending typed claims. Does not approve."""

from __future__ import annotations

import argparse
import html
import json
from hashlib import sha256
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_inventory(path: Path) -> list[dict[str, object]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = []
    for record in payload.get("records", []):
        if record.get("human_review_state") != "pending_review":
            continue
        rows.append(
            {
                "claim_id": record["claim_id"],
                "review_status": record["human_review_state"],
                "reviewer": None,
                "reviewed_at": None,
                "authority": record.get("authority"),
                "page_or_section": record.get("source_revision"),
                "exact_source_quote": record.get("source_span_text"),
                "surrounding_context": record.get("source_span_text"),
                "candidate_canonical_surface": record.get("canonical_text"),
                "source_revision": record.get("source_revision"),
                "source_document_sha256": record.get("source_document_sha256"),
                "source_span_sha256": record.get("source_span_sha256"),
                "proposed_surface_sha256": record.get("approved_surface_sha256"),
                "source_span_ids": record.get("source_span_ids"),
                "coverage_domain": "existing_inventory",
                "typed_fields": _typed_fields(record),
                "quality_flags": [],
                "preparation_notes": "Existing pending inventory record.",
            }
        )
    return rows


def _load_prepared(path: Path, batch: int | None) -> list[dict[str, object]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    allowed_ids = None
    if batch is not None:
        selected = next(
            (row for row in payload.get("batches", []) if row.get("batch") == batch),
            None,
        )
        if selected is None:
            raise SystemExit(f"unknown prepared review batch {batch}")
        allowed_ids = set(selected["candidate_ids"])
    rows = []
    for candidate in payload.get("prepared_candidates", []):
        if allowed_ids is not None and candidate["candidate_id"] not in allowed_ids:
            continue
        rows.append(
            {
                "claim_id": candidate["candidate_id"],
                "review_status": candidate["review_status"],
                "reviewer": candidate["reviewer"],
                "reviewed_at": candidate["reviewed_at"],
                "authority": candidate["authority"],
                "page_or_section": candidate["source_revision"],
                "exact_source_quote": candidate["exact_source_quote"],
                "surrounding_context": candidate["surrounding_context"],
                "candidate_canonical_surface": candidate["proposed_surface"],
                "source_revision": candidate["source_revision"],
                "source_document_sha256": candidate["source_document_sha256"],
                "source_span_sha256": candidate["source_span_sha256"],
                "proposed_surface_sha256": candidate["proposed_surface_sha256"],
                "source_span_ids": candidate["source_span_ids"],
                "coverage_domain": candidate["coverage_domain"],
                "typed_fields": candidate["typed_fields"],
                "quality_flags": candidate["quality_flags"],
                "preparation_notes": candidate["preparation_notes"],
            }
        )
    return rows


def _typed_fields(record: dict[str, object]) -> dict[str, object]:
    keys = (
        "subject",
        "action",
        "action_polarity",
        "object",
        "modality",
        "urgency",
        "status_stage",
        "quantities",
        "canonical_units",
        "ranges",
        "comparator",
        "conditions",
        "exceptions",
        "applies_to",
    )
    return {key: record.get(key) for key in keys}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--decision-template", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.manifest is not None and args.decision_template is None:
        parser.error("--manifest requires --decision-template")
    rows = _load_prepared(
        ROOT / "data/typed_claims/prepared_candidates_v2.yaml",
        args.batch,
    )
    if args.batch is None:
        rows = _load_inventory(ROOT / "data/typed_claims/high_risk_v1.yaml") + rows
    blocks = []
    for row in rows:
        if row.get("reviewer") or row.get("reviewed_at"):
            raise SystemExit(f"{row.get('claim_id')} illegally has reviewer metadata")
        blocks.append(
            "<article class='card'>"
            f"<h2>{html.escape(str(row['claim_id']))}</h2>"
            f"<p>Status: {html.escape(str(row.get('review_status')))} · "
            f"Domain: {html.escape(str(row.get('coverage_domain')))} · "
            f"Authority: {html.escape(str(row.get('authority')))}</p>"
            f"<p>Source: {html.escape(str(row.get('page_or_section') or row.get('source_revision')))} "
            f"{html.escape(str(row.get('source_span_ids')))}</p>"
            f"<p>Document SHA-256: {html.escape(str(row.get('source_document_sha256')))}<br>"
            f"Quote SHA-256: {html.escape(str(row.get('source_span_sha256')))}<br>"
            f"Surface SHA-256: {html.escape(str(row.get('proposed_surface_sha256')))}</p>"
            "<h3>Exact source quote</h3>"
            f"<blockquote>{html.escape(str(row.get('exact_source_quote') or ''))}</blockquote>"
            "<h3>Surrounding context</h3>"
            f"<p>{html.escape(str(row.get('surrounding_context') or ''))}</p>"
            "<h3>Candidate canonical surface</h3>"
            f"<p>{html.escape(str(row.get('candidate_canonical_surface') or ''))}</p>"
            "<h3>Typed fields</h3>"
            f"<pre>{html.escape(json.dumps(row.get('typed_fields'), indent=2, sort_keys=True))}</pre>"
            f"<p>Quality flags: {html.escape(str(row.get('quality_flags') or []))}</p>"
            f"<p>Preparation note: {html.escape(str(row.get('preparation_notes') or ''))}</p>"
            "<p>Approve / Edit / Reject — reviewer name and time must be filled by a person.</p>"
            "</article>"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>FireLens typed-claim review queue</title>"
        "<style>body{font-family:sans-serif;max-width:52rem;margin:2rem auto;}"
        ".card{border:1px solid #444;padding:1rem;margin:1rem 0;}</style>"
        "</head><body>"
        "<h1>Typed claim review queue</h1>"
        "<p>All records are pending_review. This export does not approve claims.</p>"
        + "".join(blocks)
        + "</body></html>",
        encoding="utf-8",
    )
    if args.decision_template is not None:
        args.decision_template.parent.mkdir(parents=True, exist_ok=True)
        args.decision_template.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "firelens.typed_claim_review_decision_draft.v1",
                    "batch": args.batch,
                    "note": "Blank human decision template. No decision is implied.",
                    "decisions": [
                        {
                            "candidate_id": row["claim_id"],
                            "decision": None,
                            "reviewer": None,
                            "decision_time": None,
                            "approved_surface": None,
                            "notes": None,
                        }
                        for row in rows
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    if args.manifest is not None and args.decision_template is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(
                {
                    "schema_version": "firelens.typed_claim_review_packet_manifest.v1",
                    "batch": args.batch,
                    "record_count": len(rows),
                    "review_state": "pending_review_only",
                    "contains_reviewer_identity": False,
                    "decision_fields_blank": True,
                    "html_filename": args.output.name,
                    "html_sha256": sha256(args.output.read_bytes()).hexdigest(),
                    "decision_template_filename": args.decision_template.name,
                    "decision_template_sha256": sha256(
                        args.decision_template.read_bytes()
                    ).hexdigest(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print(args.output)


if __name__ == "__main__":
    main()
