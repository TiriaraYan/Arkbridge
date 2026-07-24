#!/usr/bin/env python3
"""Map changed files to project pipelines via .claude/pipelines.json.

Usage:
  git status --short | python3 .claude/scripts/map_pipelines.py
  python3 .claude/scripts/map_pipelines.py path/one.py path/two.md

Input: raw `git status --short` lines (status prefix + rename arrows are
stripped) or bare repo-relative paths.

Output: per-pipeline hit list with docs + rules, plus an "unregistered"
bucket for files matching no pipeline.

Deterministic logic only — the model reads the output and acts on it.
"""
import fnmatch
import json
import sys
from pathlib import Path


def find_registry():
    """Walk up from CWD to find .claude/pipelines.json."""
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".claude" / "pipelines.json"
        if candidate.is_file():
            return candidate
    # Also check next to this script
    script_dir = Path(__file__).resolve().parent.parent
    candidate = script_dir / "pipelines.json"
    if candidate.is_file():
        return candidate
    return None


def normalize(line):
    """Extract the file path from a git-status line or bare path."""
    line = line.rstrip("\n")
    if not line.strip():
        return None
    # git status --short: "XY path" or "XY old -> new"
    if len(line) > 3 and line[2] == " ":
        line = line[3:]
    if " -> " in line:
        line = line.split(" -> ", 1)[1]
    return line.strip().strip('"')


def matches(path, patterns):
    """Check if a path matches any of the glob patterns."""
    for pat in patterns:
        if fnmatch.fnmatch(path, pat):
            return True
        if pat.endswith("/**") and path.rstrip("/") == pat[:-3]:
            return True
    return False


def main():
    registry_path = find_registry()
    if not registry_path:
        print("ERROR: .claude/pipelines.json not found.")
        print("Run this script from your project root, or create the registry first.")
        print("See README.md for setup instructions.")
        return 1

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    pipelines = data.get("pipelines", data)

    raw = sys.argv[1:] or sys.stdin.read().splitlines()
    files = [f for f in (normalize(l) for l in raw) if f]
    if not files:
        print("No input files.")
        return 1

    hits, unregistered = {}, []
    for f in files:
        matched = [
            name for name, entry in pipelines.items()
            if matches(f, entry.get("paths", []))
        ]
        if matched:
            for name in matched:
                hits.setdefault(name, []).append(f)
        else:
            unregistered.append(f)

    for name in sorted(hits):
        entry = pipelines[name]
        print(f"== {name} ==")
        if entry.get("summary"):
            print(f"  ({entry['summary']})")
        for f in hits[name]:
            print(f"  file: {f}")
        for d in entry.get("docs", []):
            print(f"  doc: {d}")
        for d in entry.get("external_docs", []):
            print(f"  external_doc: {d}")
        for r in entry.get("rules", []):
            print(f"  RULE: {r}")
        print()

    if unregistered:
        print("== unregistered (consider adding to pipelines.json) ==")
        for f in unregistered:
            print(f"  {f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
