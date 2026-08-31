#!/usr/bin/env python3
"""Build a checked Vercel deploy command from a clean local Git SHA.

This wrapper does not authorize production publication by itself. Preview is
the default. ``--prod`` is an explicit extra flag. Callers still need a
separate owner decision to run the printed command without ``--dry-run``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from firelens.config import DEFAULT_RELEASE_VERSION

# The current product candidate deliberately differs from the legacy runtime
# writer default. Keep that default for historical callers, but make every
# deploy prepared by this wrapper explicit and platform-consistent.
CURRENT_BENCHMARK_ID = "firelens_v1_6_2"

ROOT = Path(__file__).resolve().parents[1]
PINNED_VERCEL_CLI = "vercel@58.1.0"
_FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class DeployIdentityError(RuntimeError):
    """Sanitized failure when the local tree cannot bind a deploy SHA."""


def _git(args: list[str], *, root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DeployIdentityError("git is required to bind a local deploy SHA") from exc
    except subprocess.CalledProcessError as exc:
        raise DeployIdentityError(
            "git could not resolve a clean local deploy identity"
        ) from exc
    return completed.stdout.strip()


def require_clean_tree(root: Path) -> None:
    if _git(["status", "--porcelain"], root=root):
        raise DeployIdentityError("refusing to deploy a dirty Git tree")


def resolve_local_commit(root: Path) -> str:
    stripped = _git(["rev-parse", "HEAD"], root=root)
    if _FULL_COMMIT.fullmatch(stripped) is None:
        raise DeployIdentityError("local HEAD is not a full 40-character lowercase SHA")
    return stripped


def build_vercel_command(*, commit: str, production: bool) -> list[str]:
    commit_env = f"FIRELENS_BUILD_COMMIT={commit}"
    release_env = f"FIRELENS_RELEASE_VERSION={DEFAULT_RELEASE_VERSION}"
    benchmark_env = f"FIRELENS_BENCHMARK_ID={CURRENT_BENCHMARK_ID}"
    command = [
        "npx",
        PINNED_VERCEL_CLI,
        "deploy",
        "--yes",
        "--build-env",
        commit_env,
        "--build-env",
        release_env,
        "--build-env",
        benchmark_env,
        "--env",
        commit_env,
        "--env",
        release_env,
        "--env",
        benchmark_env,
    ]
    if production:
        command.append("--prod")
    return command


def prepare_deploy_command(root: Path, *, production: bool) -> list[str]:
    require_clean_tree(root)
    return build_vercel_command(commit=resolve_local_commit(root), production=production)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prod",
        action="store_true",
        help="target production; omitted deploys a preview",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the pinned command without invoking Vercel",
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        command = prepare_deploy_command(args.root, production=args.prod)
    except DeployIdentityError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rendered = subprocess.list2cmdline(command)
    print(rendered)
    if args.dry_run:
        return 0
    completed = subprocess.run(command, cwd=args.root, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
