import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


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
    assert "deterministic high-risk publication" in readme
    assert "Eligible lower-risk packets may use one bounded generation" in readme
    assert "Exact quote only" in readme
    assert "## What FireLens does" in readme
    assert "## Why this is not “just a chatbot”" in readme
    assert "## What V1.6 adds" in readme
    assert "## How an answer becomes publishable" in readme
    assert "## Verification and evidence" in readme
    assert "RC2 hardening and qualification campaign" in readme
    assert "public package and API identity remains `1.6.0-rc.1`" in readme
    assert "not a current wildfire or evacuation report" in readme
    assert "production-ready" not in readme.casefold()
    assert "current architecture authority" in architecture
    assert "reviewed structured claims and extraction-only source wording" in architecture
    assert "named, hash-bound `rc2` profile" in architecture
    assert "active `rc2.1` profile" in architecture
    assert "archival V1.5 code-and-design snapshot" in handbook
    assert "This handbook describes the code that runs now." not in handbook
    assert "exact Git commit and Git tree" in runbook
    assert "matching CI candidate-evidence artifact" in runbook
    assert "Candidate-evidence v2 must bind the unchanged historical hard-probe" in runbook
    assert "--expectation-profile rc2.1" in runbook
    assert "RC2.1 expectation profile/manifest" in runbook
    assert "Do not name `a5cd967`" in runbook
    assert "## Unreleased — V1.6 RC2" in changelog
    assert "independently hash-bound RC2.1 profile" in changelog


def test_readme_relative_links_and_image_exist() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = MARKDOWN_LINK.findall(readme)
    targets.extend(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme))

    missing: list[str] = []
    for raw in targets:
        target = raw.strip().split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        if not (ROOT / target).exists():
            missing.append(raw)
    assert missing == []
