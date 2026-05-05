#!/usr/bin/env python3
"""Poll GitHub issues and hand dispatch prompts to the local PC.

This worker intentionally does not run Codex automatically. It receives
mobile-created GitHub issues, writes the prompt to a local ignored directory,
marks the issue as in progress, and posts a receipt comment.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPO = "naughtydream050-cloud/killstreet-insta-feed"
DEFAULT_OUT_DIR = ".codex-dispatch"
DISPATCH_LABEL = "dispatch"
IN_PROGRESS_LABEL = "in-progress"
PROCESSED_LABEL = "processed"


def run_gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"gh {' '.join(args)} failed: {message}")
    return result.stdout


def ensure_gh_auth() -> None:
    run_gh(["auth", "status"])


def ensure_label(repo: str, name: str, color: str, description: str) -> None:
    result = subprocess.run(
        [
            "gh",
            "label",
            "create",
            name,
            "--repo",
            repo,
            "--color",
            color,
            "--description",
            description,
            "--force",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"failed to ensure label {name}: {message}")


def list_dispatch_issues(repo: str) -> list[dict[str, Any]]:
    raw = run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--label",
            DISPATCH_LABEL,
            "--json",
            "number,title,body,labels,url",
            "--limit",
            "50",
        ]
    )
    issues = json.loads(raw)
    return [issue for issue in issues if not has_blocking_label(issue)]


def has_blocking_label(issue: dict[str, Any]) -> bool:
    labels = {label.get("name") for label in issue.get("labels", [])}
    return IN_PROGRESS_LABEL in labels or PROCESSED_LABEL in labels


def build_prompt(repo: str, issue: dict[str, Any]) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    body = issue.get("body") or ""
    return "\n".join(
        [
            "# Local Codex Dispatch",
            "",
            f"- Repository: {repo}",
            f"- Issue: #{issue['number']} {issue.get('title', '')}",
            f"- URL: {issue.get('url', '')}",
            f"- Received at: {timestamp}",
            "",
            "## Issue Body",
            "",
            body.strip(),
            "",
        ]
    )


def write_prompt(out_dir: Path, issue: dict[str, Any], content: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    final_path = out_dir / f"issue-{issue['number']}-prompt.md"
    tmp_path = out_dir / f".issue-{issue['number']}-prompt.md.tmp"
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(final_path)
    return final_path


def claim_issue(repo: str, issue_number: int) -> None:
    run_gh(
        [
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            repo,
            "--add-label",
            IN_PROGRESS_LABEL,
        ]
    )


def post_receipt(repo: str, issue: dict[str, Any], prompt_path: Path) -> None:
    body = "\n".join(
        [
            "## Local dispatch worker",
            "",
            "- Status: received-on-pc",
            f"- Prompt file: `{prompt_path}`",
            "- Codex auto-execution: disabled",
            "",
            "This issue was received by the local PC worker. Open the prompt file in Codex to continue without using the OpenAI API from GitHub Actions.",
        ]
    )
    run_gh(
        [
            "issue",
            "comment",
            str(issue["number"]),
            "--repo",
            repo,
            "--body",
            body,
        ]
    )


def process_once(repo: str, out_dir: Path) -> int:
    issues = list_dispatch_issues(repo)
    if not issues:
        print("No pending dispatch issues.")
        return 0

    for issue in issues:
        prompt = build_prompt(repo, issue)
        prompt_path = write_prompt(out_dir, issue, prompt)
        claim_issue(repo, issue["number"])
        post_receipt(repo, issue, prompt_path)
        print(f"Received issue #{issue['number']}: {prompt_path}")

    return len(issues)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local GitHub issue dispatch worker.")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)

    try:
        ensure_gh_auth()
        ensure_label(args.repo, IN_PROGRESS_LABEL, "fbca04", "Local worker has received this dispatch.")
        ensure_label(args.repo, PROCESSED_LABEL, "0e8a16", "Local dispatch has been completed.")

        while True:
            process_once(args.repo, out_dir)
            if args.once:
                return 0
            time.sleep(max(args.interval, 30))
    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
