from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return " ".join((ROOT / path).read_text(encoding="utf-8").split())


def test_current_documentation_preserves_v1_6_rc2_authority_boundaries() -> None:
    readme = _read("README.md")
    architecture = _read("docs/ARCHITECTURE_V1_6.md")
    handbook = _read("docs/TECHNICAL_HANDBOOK.md")
    runbook = _read("docs/releases/V1_6_RUNBOOK.md")
    changelog = _read("CHANGELOG.md")

    assert "Python 3.12–3.14" in readme
    assert "26-record, hash-bound typed-claim inventory" in readme
    assert "deterministic and uses zero generation" in readme
    assert "Eligible lower-risk ready packets may use one generation" in readme
    assert "exact-source quote-only, partial, or handoff response" in readme
    assert "current architecture authority" in architecture
    assert "reviewed structured claims and extraction-only source wording" in architecture
    assert "archival V1.5 code-and-design snapshot" in handbook
    assert "This handbook describes the code that runs now." not in handbook
    assert "exact Git commit and Git tree" in runbook
    assert "matching CI candidate-evidence artifact" in runbook
    assert "Do not name `a5cd967`" in runbook
    assert "## Unreleased — V1.6 RC2" in changelog
