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
    assert "## What V1.6 and the local V1.6.2 candidate add" in readme
    assert "## How an answer becomes publishable" in readme
    assert "## Adaptive views" in readme
    assert "## Quick start" in readme
    assert "## Verification and evidence" in readme
    assert "local V1.6.2 engineering candidate" in readme
    assert "not been exact-Git qualified, deployed, or release-qualified" in readme
    assert "general conversational assistant with specialized, evidence-bound B.C." in readme
    assert "Broad interpretation, narrow authority" in readme
    assert "Safety-sensitive is not out of scope" in readme
    assert "Product Constitution" in readme
    assert "V1.6.2 evaluation framework" in readme
    assert "not a current wildfire or evacuation report" in readme
    assert "The request plan owns retrieval scope" in readme
    assert "Preview and production configuration reject" in readme
    assert "production-ready" not in readme.casefold()
    assert "current architecture authority" in architecture
    assert "V1.6.2 branch candidate is committed" in architecture
    assert "required in the external current candidate-evidence record" in architecture
    assert "does not affirm that matching CI evidence already exists" in architecture
    assert "345aaab2bef2fb3f580401dd79303a6b840fc88a" not in architecture
    assert (
        "RC1/RC2 standards and their recorded reports remain historical, frozen" in architecture
    )
    assert "Deterministic request-plan boundary" in architecture
    assert "sole authority for a request's tools, live layers, geography" in architecture
    assert "preview and production reject it" in architecture
    assert "reviewed structured claims and extraction-only source wording" in architecture
    assert "named, hash-bound `rc2` profile" in architecture
    assert "active `rc2.2` profile" in architecture
    assert "archival V1.5 code-and-design snapshot" in handbook
    assert "ADR 0017" in handbook
    assert "This handbook describes the code that runs now." not in handbook
    assert "exact Git commit and Git tree" in runbook
    assert (
        "tracked Python package, web package, runtime default, Docker configuration" in runbook
    )
    assert "are `1.6.2`" in runbook
    assert "separate from the historical `1.6.0-rc.1` and RC2 records" in runbook
    assert "clean V1.6.2 commit before freezing" in runbook
    assert "matching CI candidate-evidence artifact" in runbook
    assert "Candidate-evidence v2 must bind the unchanged historical hard-probe" in runbook
    assert "--expectation-profile rc2.2" in runbook
    assert "RC2.1 expectation profile/manifest" in runbook
    assert "Do not name a historical RC1/RC2 commit as the V1.6.2 candidate" in runbook
    assert "## Unreleased — V1.6.2" in changelog
    assert "PB15-style source-extraction defects remain source-repair work" in changelog
    assert "committed local engineering candidate" in changelog
    assert "must be bound by external current candidate evidence" in changelog
    assert "does not affirm that such evidence exists" in changelog
    assert "345aaab2bef2fb3f580401dd79303a6b840fc88a" not in changelog
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


def test_portfolio_and_offline_examination_documents_preserve_limits() -> None:
    case_study = _read("docs/portfolio/CLIMATE_DECISION_INTELLIGENCE_CASE_STUDY.md")
    demo = _read("docs/portfolio/DEMO_SCRIPT.md")
    offline_prompt = _read("docs/audit/V1_6_GPT_5_6_PRO_OFFLINE_BUNDLE_EXAMINATION_PROMPT.md")

    assert "Why naive RAG fails" in case_study
    assert "Remaining limits" in case_study
    assert "not an emergency authority" in case_study
    assert "fixture lane" in demo
    assert "current incident, evacuation, or safety information" in demo
    assert "GitHub, network, and a local checkout are unavailable" in offline_prompt
    assert "state UNKNOWN" in offline_prompt
    assert "must not edit files, make network calls" in offline_prompt


def test_v1_6_2_quality_documents_preserve_constitution_and_evidence_boundaries() -> None:
    constitution = _read("docs/quality/FIRELENS_PRODUCT_CONSTITUTION.md")
    framework = _read("docs/quality/V1_6_2_EVALUATION_FRAMEWORK.md")

    for contract in (
        "Scope understanding",
        "Capability decomposition",
        "Evidence authority",
        "Deterministic ownership",
        "Publication authority",
        "Useful failure",
        "User-first presentation",
        "Runtime and release truth",
    ):
        assert contract in constitution
    assert "broad interpretation, narrow authority" in constitution.casefold()
    assert "Safety-sensitive is not out of scope" in constitution
    assert "Observe → Reproduce → Falsify" in constitution
    assert "three active issue clusters" in constitution
    assert "PB15-style malformed source extraction" in constitution
    assert "not a certification, deployment result, or release decision" in constitution
    assert "Benchmark pyramid" in framework
    assert "ProductBench v2" in framework
    assert "31-case offline tier" in framework
    assert "19 provider-backed cases" in framework
    assert "Inspected" in framework and "Release" in framework
    assert "not a release certificate" in framework


def test_quality_document_relative_links_exist() -> None:
    for path in (
        "docs/quality/FIRELENS_PRODUCT_CONSTITUTION.md",
        "docs/quality/V1_6_2_EVALUATION_FRAMEWORK.md",
    ):
        text = (ROOT / path).read_text(encoding="utf-8")
        missing: list[str] = []
        for raw in MARKDOWN_LINK.findall(text):
            target = raw.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not ((ROOT / path).parent / target).resolve().exists():
                missing.append(raw)
        assert missing == []


def test_readme_documented_verification_commands_exist() -> None:
    readme = _read("README.md")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for script in (
        "scripts/v1_6_structured_publication_eval.py",
        "scripts/run_hard_probe.py",
        "scripts/run_productbench.py",
    ):
        assert script in readme
        assert (ROOT / script).is_file()
    assert "make verify" in readme
    assert "productbench-provider:" in makefile
