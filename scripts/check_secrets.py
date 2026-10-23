"""Fail CI when committed source looks like it contains credentials.

The scanner never opens `.env`; it reports only a file, line number and rule
name, never the matching value.  It complements (but does not replace) a
repository secret-scanning product such as GitHub secret scanning or Gitleaks.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "data",
    "logs",
    "models",
    "node_modules",
}
TEXT_SUFFIXES = {
    ".css",
    ".env.example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
RULES = {
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai-style-key": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "signed-url": re.compile(r"(?:X-Amz-Signature|X-Goog-Signature|Signature=)[A-Fa-f0-9]{20,}"),
}


def _tracked_files() -> set[str]:
    completed = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "ls-files"],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    return {line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()}


def _candidate_files():
    tracked = _tracked_files()
    files = (PROJECT_ROOT / relative for relative in tracked) if tracked else PROJECT_ROOT.rglob("*")
    for path in files:
        if not path.is_file() or any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative == ".env":
            yield path
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Dockerfile", "Dockerfile.full"}:
            yield path


def main() -> int:
    tracked = _tracked_files()
    findings: list[tuple[str, int, str]] = []
    if ".env" in tracked:
        findings.append((".env", 0, "tracked-env-file"))

    for path in _candidate_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative == ".env":
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(lines, start=1):
            for rule_name, pattern in RULES.items():
                if pattern.search(line):
                    findings.append((relative, line_number, rule_name))

    if findings:
        print("Potential secret material detected (values intentionally hidden):")
        for relative, line_number, rule_name in findings:
            print(f"- {relative}:{line_number or '-'} [{rule_name}]")
        return 1
    print("Secret scan passed: no credential patterns found in candidate source files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
