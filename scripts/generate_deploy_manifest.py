#!/usr/bin/env python3
"""
Generate a deterministic deploy manifest with SHA-256 asset hashes,
git commit metadata, dirty-worktree status, and sanitized API configuration.
Follows SkillPulse Spec 07 (Truthful Release Recovery) §6.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"

RELEASE_FILES = [
    "index.html",
    "script.js",
    "style.css",
    "config.js",
    "_redirects",
    "_headers",
    "api/404.json",
]


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_git_metadata():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT_DIR, text=True
        ).strip()
    except Exception:
        commit = "unknown"

    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT_DIR, text=True
        ).strip()
    except Exception:
        branch = "unknown"

    try:
        status_output = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT_DIR, text=True
        ).strip()
        dirty = bool(status_output)
    except Exception:
        dirty = True

    return commit, branch, dirty


def extract_sanitized_api_base_url() -> str:
    config_file = FRONTEND_DIR / "config.js"
    if not config_file.exists():
        return ""

    raw_text = config_file.read_text(encoding="utf-8")
    for line in raw_text.splitlines():
        line = line.strip()
        if "API_BASE_URL" in line and "=" in line:
            parts = line.split("=", 1)
            val = parts[1].strip().rstrip(";").strip('"').strip("'")
            if not val:
                return ""
            try:
                parsed = urllib.parse.urlsplit(val)
                # Strip userinfo/query/fragment
                clean = urllib.parse.urlunsplit(
                    (parsed.scheme, parsed.netloc.split("@")[-1], parsed.path, "", "")
                )
                return clean.rstrip("/")
            except Exception:
                return val
    return ""


def generate_manifest():
    commit, branch, dirty = get_git_metadata()
    api_base_url = extract_sanitized_api_base_url()

    files_manifest = {}
    for rel_path in RELEASE_FILES:
        full_path = FRONTEND_DIR / rel_path
        if full_path.exists():
            files_manifest[rel_path] = {
                "sha256": sha256_file(full_path),
                "bytes": full_path.stat().st_size,
            }
        else:
            files_manifest[rel_path] = {
                "sha256": None,
                "bytes": 0,
                "missing": True,
            }

    return {
        "project": "skillpulse",
        "branch": branch,
        "commit": commit,
        "dirty": dirty,
        "api_base_url": api_base_url,
        "files": files_manifest,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate deploy manifest for SkillPulse.")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    manifest = generate_manifest()

    if args.json:
        print(json.dumps(manifest, indent=2))
        return

    print("=" * 70)
    print("SkillPulse — Production Deploy Manifest (Spec 07)")
    print("=" * 70)
    print(f"Target Project:  {manifest['project']}")
    print(f"Git Branch:      {manifest['branch']}")
    print(f"Git Commit:      {manifest['commit']}")
    print(f"Worktree Dirty:  {manifest['dirty']}")
    print(f"API Base URL:    {manifest['api_base_url'] or '(same-origin / empty)'}")
    print("-" * 70)
    print(f"{'File':<20} {'Bytes':<8} {'SHA-256 Hash'}")
    print("-" * 70)
    for fname, info in manifest["files"].items():
        h = info.get("sha256") or "MISSING"
        b = info.get("bytes", 0)
        print(f"{fname:<20} {b:<8} {h}")
    print("=" * 70)


if __name__ == "__main__":
    main()
