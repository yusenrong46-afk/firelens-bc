from __future__ import annotations

from pathlib import Path

from lxml import html

WEB_ROOT = Path(__file__).resolve().parents[1] / "src/firelens/review_workspace/web"


def test_reviewer_client_has_unique_ids_labels_and_no_inline_executable_content() -> None:
    document = html.fromstring((WEB_ROOT / "review.html").read_text(encoding="utf-8"))
    ids = document.xpath("//*[@id]/@id")
    assert len(ids) == len(set(ids))
    id_roster = set(ids)
    for label_for in document.xpath("//label[@for]/@for"):
        assert label_for in id_roster
    assert document.xpath("//main[@id='review-main']")
    assert document.xpath("//*[@role='status'][@aria-live='polite']")
    assert all(
        button.get("type") in {"button", "submit"} for button in document.xpath("//button")
    )
    assert not document.xpath("//script[not(@src)]")
    assert not document.xpath("//style")
    assert not document.xpath("//*[@style or @onclick or @onchange or @onsubmit or @onload]")


def test_reviewer_script_keeps_capability_in_memory_and_uses_safe_text_rendering() -> None:
    script = (WEB_ROOT / "review.js").read_text(encoding="utf-8")
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert ".innerHTML" not in script
    assert "textContent" in script
    assert 'credentials: "same-origin"' in script
    assert 'cache: "no-store"' in script


def test_reviewer_styles_include_focus_reflow_and_reduced_motion_guards() -> None:
    styles = (WEB_ROOT / "review.css").read_text(encoding="utf-8")
    assert ":focus-visible" in styles
    assert "min-height: 44px" in styles
    assert "@media (max-width: 760px)" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles
