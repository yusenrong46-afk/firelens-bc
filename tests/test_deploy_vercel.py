from __future__ import annotations

from pathlib import Path

import pytest

from firelens.config import DEFAULT_RELEASE_VERSION
from scripts.deploy_vercel import (
    CURRENT_BENCHMARK_ID,
    PINNED_VERCEL_CLI,
    DeployIdentityError,
    build_vercel_command,
    main,
    prepare_deploy_command,
)

COMMIT = "b00544c1927ffa12d98689f6a4b0b44b6c7de7e1"


def test_preview_command_binds_exact_sha_and_product_release() -> None:
    command = build_vercel_command(commit=COMMIT, production=False)
    assert command == [
        "npx",
        PINNED_VERCEL_CLI,
        "deploy",
        "--yes",
        "--build-env",
        f"FIRELENS_BUILD_COMMIT={COMMIT}",
        "--build-env",
        f"FIRELENS_RELEASE_VERSION={DEFAULT_RELEASE_VERSION}",
        "--build-env",
        f"FIRELENS_BENCHMARK_ID={CURRENT_BENCHMARK_ID}",
        "--env",
        f"FIRELENS_BUILD_COMMIT={COMMIT}",
        "--env",
        f"FIRELENS_RELEASE_VERSION={DEFAULT_RELEASE_VERSION}",
        "--env",
        f"FIRELENS_BENCHMARK_ID={CURRENT_BENCHMARK_ID}",
    ]
    assert DEFAULT_RELEASE_VERSION == "1.6.2"
    assert "--prod" not in command


def test_production_flag_is_explicit() -> None:
    command = build_vercel_command(commit=COMMIT, production=True)
    assert command[-1] == "--prod"
    assert command.count("--prod") == 1


def test_prepare_deploy_refuses_dirty_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_git(args: list[str], *, root: Path) -> str:
        assert root == tmp_path
        if args == ["status", "--porcelain"]:
            return " M src/firelens/live.py"
        raise AssertionError(args)

    monkeypatch.setattr("scripts.deploy_vercel._git", fake_git)
    with pytest.raises(DeployIdentityError, match="dirty Git tree"):
        prepare_deploy_command(tmp_path, production=False)


def test_prepare_deploy_uses_local_head_when_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_git(args: list[str], *, root: Path) -> str:
        assert root == tmp_path
        if args == ["status", "--porcelain"]:
            return ""
        if args == ["rev-parse", "HEAD"]:
            return COMMIT
        raise AssertionError(args)

    monkeypatch.setattr("scripts.deploy_vercel._git", fake_git)
    assert prepare_deploy_command(tmp_path, production=False) == build_vercel_command(
        commit=COMMIT, production=False
    )


def test_dry_run_prints_command_and_does_not_invoke_vercel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "scripts.deploy_vercel.prepare_deploy_command",
        lambda root, production: build_vercel_command(commit=COMMIT, production=production),
    )
    invoked: list[list[str]] = []

    def fake_run(command, **_kwargs):
        invoked.append(command)
        raise AssertionError("dry-run must not invoke Vercel")

    monkeypatch.setattr("scripts.deploy_vercel.subprocess.run", fake_run)
    assert main(["--dry-run", "--root", str(tmp_path)]) == 0
    assert invoked == []
    rendered = capsys.readouterr().out.strip()
    assert PINNED_VERCEL_CLI in rendered
    assert f"FIRELENS_BUILD_COMMIT={COMMIT}" in rendered
    assert "FIRELENS_RELEASE_VERSION=1.6.2" in rendered
    assert "FIRELENS_BENCHMARK_ID=firelens_v1_6_2" in rendered
    assert "--prod" not in rendered.split()
