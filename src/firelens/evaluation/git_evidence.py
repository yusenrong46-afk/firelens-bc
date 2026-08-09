"""Fail-closed Git identity and benchmark ancestry validation."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from firelens.evaluation.common import file_sha256
from firelens.evaluation.spec_models import BenchmarkSpec

GitCommand = Callable[..., subprocess.CompletedProcess[str]]


def git(repository_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def tracked_dirty(repository_root: Path) -> bool:
    working = subprocess.run(["git", "diff", "--quiet"], cwd=repository_root, check=False)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=repository_root, check=False
    )
    return working.returncode != 0 or staged.returncode != 0


def relevant_untracked_paths(
    *,
    git_reader: Callable[..., str],
) -> list[str]:
    ignored_prefixes = (".agents/", "output/")
    return sorted(
        path
        for path in git_reader("ls-files", "--others", "--exclude-standard").splitlines()
        if path and not path.startswith(ignored_prefixes)
    )


def repo_relative_path(
    path: Path,
    *,
    repository_root: Path,
    context: str,
) -> tuple[Path, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repository_root).as_posix()
    except ValueError as error:
        raise ValueError(f"{context} must be inside the repository") from error
    return resolved, relative


def spec_seal_path(spec: BenchmarkSpec, *, repository_root: Path) -> tuple[Path, str]:
    configured = Path(spec.before_snapshot_seal)
    if configured.is_absolute():
        raise ValueError("before snapshot seal path must be repository-relative")
    if ".." in configured.parts:
        raise ValueError("before snapshot seal path must not traverse parent directories")
    configured_relative = configured.as_posix()
    unresolved = repository_root / configured
    if unresolved.is_symlink():
        raise ValueError("before snapshot seal path cannot be a symbolic link")
    path, relative = repo_relative_path(
        unresolved,
        repository_root=repository_root,
        context="before snapshot seal",
    )
    if relative != configured_relative:
        raise ValueError(
            "before snapshot seal must use the exact canonical repository path "
            "without symbolic-link components"
        )
    if relative.startswith("output/"):
        raise ValueError("before snapshot seal cannot be stored under ignored output")
    return path, relative


def git_evidence_command(
    args: list[str],
    *,
    repository_root: Path,
    context: str,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    """Run a Git evidence command while preserving fail-closed diagnostics."""

    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ValueError(
            f"{context}: Git could not run; verify the repository and Git installation"
        ) from error
    if completed.returncode not in allowed_returncodes:
        detail = (completed.stderr or completed.stdout).strip() or "no diagnostic output"
        command = "git " + " ".join(args)
        raise ValueError(
            f"{context}: `{command}` failed with exit {completed.returncode}: {detail}"
        )
    return completed


def path_is_tracked_and_unmodified(
    path: Path,
    *,
    repository_root: Path,
    command: GitCommand,
) -> bool:
    _, relative = repo_relative_path(
        path,
        repository_root=repository_root,
        context="tracked benchmark artifact",
    )
    tracked = command(
        ["ls-files", "--error-unmatch", "--", relative],
        context=f"cannot verify tracked benchmark artifact {relative}",
        allowed_returncodes=(0, 1),
    )
    if tracked.returncode != 0:
        return False
    unstaged = command(
        ["diff", "--quiet", "--", relative],
        context=f"cannot verify unstaged benchmark artifact state for {relative}",
        allowed_returncodes=(0, 1),
    )
    staged = command(
        ["diff", "--cached", "--quiet", "--", relative],
        context=f"cannot verify staged benchmark artifact state for {relative}",
        allowed_returncodes=(0, 1),
    )
    return unstaged.returncode == 0 and staged.returncode == 0


def exact_git_commit(
    commitish: str,
    *,
    context: str,
    command: GitCommand,
) -> str:
    if not isinstance(commitish, str) or not commitish.strip():
        raise ValueError(f"{context} has no Git commit")
    observed = commitish.strip()
    completed = command(
        ["rev-parse", "--verify", f"{observed}^{{commit}}"],
        context=f"cannot resolve {context}",
    )
    resolved = completed.stdout.strip()
    if not resolved or resolved != observed:
        raise ValueError(
            f"{context} must use the exact full Git commit ID; "
            f"recorded={observed!r}, resolved={resolved!r}"
        )
    return resolved


def current_git_commit(*, context: str, command: GitCommand) -> str:
    resolved = command(
        ["rev-parse", "--verify", "HEAD^{commit}"],
        context=f"cannot resolve {context}",
    ).stdout.strip()
    return exact_git_commit(resolved, context=context, command=command)


def resolve_before_snapshot_ancestry(
    *,
    spec: BenchmarkSpec,
    before: dict[str, Any],
    after_commit: str,
    seal_path_resolver: Callable[[BenchmarkSpec], tuple[Path, str]],
    command: GitCommand,
    report_reader: Callable[[Path | None], dict[str, Any] | None],
) -> dict[str, Any]:
    """Prove before -> seal introduction -> after using complete Git history."""

    seal_path, relative_seal = seal_path_resolver(spec)
    if not seal_path.is_file():
        raise ValueError(
            f"before snapshot seal is missing at {relative_seal}; create and commit it first"
        )
    if seal_path.is_symlink():
        raise ValueError("before snapshot seal must be a regular file, not a symbolic link")
    _validate_seal_worktree(relative_seal, command)
    before_commit = _sealed_before_commit(seal_path, before, report_reader, command)
    resolved_after_commit = exact_git_commit(
        after_commit, context="after candidate", command=command
    )
    seal_commit = _seal_introduction_commit(relative_seal, resolved_after_commit, command)
    _validate_seal_blobs(relative_seal, seal_commit, resolved_after_commit, command)
    _require_ancestor(
        before_commit,
        seal_commit,
        command=command,
        message="before snapshot candidate is not an ancestor of the seal-introducing commit; the seal is on an unrelated or invalid history",
    )
    _require_ancestor(
        seal_commit,
        resolved_after_commit,
        command=command,
        message="seal-introducing commit is not an ancestor of the after candidate; the after candidate is on an unrelated side branch or predates the seal",
    )
    return {
        "status": "verified",
        "seal_path": relative_seal,
        "seal_sha256": file_sha256(seal_path),
        "before_candidate_commit": before_commit,
        "seal_introducing_commit": seal_commit,
        "after_candidate_commit": resolved_after_commit,
        "before_is_ancestor_of_seal": True,
        "seal_is_ancestor_of_after": True,
    }


def _validate_seal_worktree(relative_seal: str, command: GitCommand) -> None:
    shallow = command(
        ["rev-parse", "--is-shallow-repository"],
        context="cannot determine whether before-seal Git history is complete",
    ).stdout.strip()
    if shallow == "true":
        raise ValueError(
            "before-seal ancestry cannot be verified from a shallow repository; "
            "fetch complete history (for example `git fetch --unshallow`) and retry"
        )
    if shallow != "false":
        raise ValueError(
            "before-seal ancestry received an invalid shallow-history response from Git"
        )

    tracked = command(
        ["ls-files", "--error-unmatch", "--", relative_seal],
        context=f"cannot verify tracked before snapshot seal {relative_seal}",
        allowed_returncodes=(0, 1),
    )
    if tracked.returncode != 0:
        raise ValueError(
            f"before snapshot seal {relative_seal} is untracked; commit the exact seal file"
        )
    for diff_args, state in (
        (["diff", "--quiet", "--", relative_seal], "unstaged"),
        (["diff", "--cached", "--quiet", "--", relative_seal], "staged"),
    ):
        diff = command(
            diff_args,
            context=f"cannot verify {state} before snapshot seal state",
            allowed_returncodes=(0, 1),
        )
        if diff.returncode != 0:
            raise ValueError(
                f"before snapshot seal {relative_seal} has {state} modifications; "
                "restore the committed seal before qualification"
            )


def _sealed_before_commit(
    seal_path: Path,
    before: dict[str, Any],
    reader: Callable[[Path | None], dict[str, Any] | None],
    command: GitCommand,
) -> str:
    seal = reader(seal_path)
    if seal is None:
        raise ValueError("tracked before snapshot seal is unreadable")
    seal_candidate = seal.get("candidate_identity")
    before_identity = before.get("identity")
    if not isinstance(seal_candidate, dict) or not isinstance(before_identity, dict):
        raise ValueError("before snapshot and seal lack candidate commit evidence")
    seal_before_commit = seal_candidate.get("commit")
    snapshot_before_commit = before_identity.get("commit")
    if seal_before_commit != snapshot_before_commit:
        raise ValueError(
            "before snapshot candidate commit differs from the commit recorded by its seal"
        )
    return exact_git_commit(
        cast(str, seal_before_commit),
        context="before snapshot candidate",
        command=command,
    )


def _seal_introduction_commit(
    relative_seal: str, after_commit: str, command: GitCommand
) -> str:
    history = command(
        ["log", "--format=%H", "--all", "HEAD", after_commit, "--", relative_seal],
        context=f"cannot resolve immutable history for {relative_seal}",
    ).stdout.splitlines()
    history_commits = [commit.strip() for commit in history if commit.strip()]
    if len(history_commits) != 1:
        if not history_commits:
            raise ValueError(
                f"no Git commit introduces before snapshot seal {relative_seal}; "
                "commit the seal and ensure complete history is available"
            )
        raise ValueError(
            f"before snapshot seal {relative_seal} has ambiguous or mutable history; "
            f"path_commits={history_commits}"
        )
    additions = command(
        [
            "log",
            "--format=%H",
            "--diff-filter=A",
            "--all",
            "HEAD",
            after_commit,
            "--",
            relative_seal,
        ],
        context=f"cannot resolve the introducing commit for {relative_seal}",
    ).stdout.splitlines()
    addition_commits = [commit.strip() for commit in additions if commit.strip()]
    if not addition_commits:
        raise ValueError(
            f"no Git commit introduces before snapshot seal {relative_seal}; "
            "commit the seal and ensure complete history is available"
        )
    if len(addition_commits) != 1:
        raise ValueError(
            f"before snapshot seal {relative_seal} has ambiguous introduction history; "
            f"addition_commits={addition_commits}"
        )
    seal_commit = exact_git_commit(
        addition_commits[0],
        context="before snapshot seal introducing commit",
        command=command,
    )
    if history_commits[0] != seal_commit:
        raise ValueError(
            f"Git history for before snapshot seal {relative_seal} does not identify "
            "one immutable introduction commit"
        )

    return seal_commit


def _validate_seal_blobs(
    relative_seal: str, seal_commit: str, after_commit: str, command: GitCommand
) -> None:
    introduced_blob = command(
        ["rev-parse", f"{seal_commit}:{relative_seal}"],
        context="cannot read the before snapshot seal from its introducing commit",
    ).stdout.strip()
    current_blob = command(
        ["hash-object", "--", relative_seal],
        context="cannot hash the tracked before snapshot seal",
    ).stdout.strip()
    if not introduced_blob or introduced_blob != current_blob:
        raise ValueError(
            "the tracked before snapshot seal differs from the file introduced by its "
            f"resolved commit {seal_commit}; the seal must remain immutable"
        )
    after_blob = command(
        ["rev-parse", f"{after_commit}:{relative_seal}"],
        context="after candidate does not contain the committed before snapshot seal",
    ).stdout.strip()
    if after_blob != introduced_blob:
        raise ValueError(
            "after candidate contains a different before snapshot seal blob; "
            "the committed seal must remain immutable"
        )


def _require_ancestor(
    ancestor: str, descendant: str, *, command: GitCommand, message: str
) -> None:
    result = command(
        ["merge-base", "--is-ancestor", ancestor, descendant],
        context="cannot verify before-seal Git ancestry",
        allowed_returncodes=(0, 1),
    )
    if result.returncode != 0:
        raise ValueError(message)
