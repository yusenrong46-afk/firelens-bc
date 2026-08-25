from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from firelens.ingestion.acquire import MAX_SOURCE_BYTES, acquire_source
from firelens.ingestion.pdf import IngestionError


def _source(**overrides: object) -> dict[str, object]:
    payload = b"%PDF-reviewed"
    source: dict[str, object] = {
        "source_id": "approved-source",
        "source_type": "pdf",
        "corpus_action": "include",
        "canonical_url": "https://www2.gov.bc.ca/approved.pdf",
        "local_file": "data/raw/approved.pdf",
        "expected_sha256": hashlib.sha256(payload).hexdigest(),
    }
    source.update(overrides)
    return source


class _Response:
    def __init__(self, payload: bytes, url: str = "https://www2.gov.bc.ca/approved.pdf"):
        self.payload = payload
        self.url = url

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://www2.gov.bc.ca/approved.pdf",
        "https://example.com/approved.pdf",
        "https://user:password@www2.gov.bc.ca/approved.pdf",
    ],
)
def test_acquisition_rejects_unapproved_source_urls(tmp_path: Path, url: str) -> None:
    with pytest.raises(IngestionError, match="approved HTTPS hosts"):
        acquire_source(_source(canonical_url=url), tmp_path)


def test_acquisition_rejects_destination_traversal(tmp_path: Path) -> None:
    with pytest.raises(IngestionError, match="escapes the project root"):
        acquire_source(_source(local_file="../outside.pdf"), tmp_path)


def test_acquisition_rejects_redirect_to_unapproved_host(tmp_path: Path) -> None:
    with patch(
        "urllib.request.urlopen",
        return_value=_Response(b"%PDF-reviewed", "https://example.com/redirected.pdf"),
    ):
        with pytest.raises(IngestionError, match="approved HTTPS hosts"):
            acquire_source(_source(), tmp_path)


def test_acquisition_rejects_oversized_payload_before_writing(tmp_path: Path) -> None:
    with patch(
        "urllib.request.urlopen",
        return_value=_Response(b"%PDF-" + b"x" * MAX_SOURCE_BYTES),
    ):
        with pytest.raises(IngestionError, match="size limit"):
            acquire_source(_source(), tmp_path)
    assert not (tmp_path / "data/raw/approved.pdf").exists()
