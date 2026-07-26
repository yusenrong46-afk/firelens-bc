"""Fail when a tracked text file contains a likely OpenRouter credential."""

from __future__ import annotations

import subprocess
from pathlib import Path


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [Path(value.decode()) for value in result.stdout.split(b"\0") if value]


def contains_secret(path: Path) -> bool:
    if path == Path(".env.example") or not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    token_prefix = "sk" + "-or-v1-"
    if token_prefix in text:
        return True
    variable = "OPENROUTER" + "_API_KEY"
    for line in text.splitlines():
        if line.strip().startswith(f"{variable}="):
            value = line.split("=", 1)[1].strip()
            if value and not value.startswith("your-"):
                return True
    return False


def main() -> None:
    matches = [str(path) for path in tracked_files() if contains_secret(path)]
    if matches:
        raise SystemExit("Secret-like value found in tracked file(s): " + ", ".join(matches))
    print("Tracked secret scan passed.")


if __name__ == "__main__":
    main()
