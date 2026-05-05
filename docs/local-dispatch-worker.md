# Local Dispatch Worker

This repository can be controlled from a phone without running OpenAI API calls in GitHub Actions.
GitHub issues become the chat room, and the PC worker prepares prompt and reply files.

Flow:

1. Create a GitHub issue from the phone.
2. Add the `dispatch` label.
3. Run the local worker on the PC.
4. The worker reads the issue body and comments.
5. The worker saves each new turn to `.codex-dispatch/issue-<number>-turn-<n>-prompt.md`.
6. The worker tracks progress in `.codex-dispatch/state.json`.
7. The worker keeps a resume summary at `.codex-dispatch/issue-<number>-summary.md`.
8. The worker comments on the issue and adds `in-progress`.
9. Open the generated prompt file in Codex on the PC.
10. Put the reply in `.codex-dispatch/issue-<number>-reply.md`.
11. Run the worker with `--post-replies` to post that reply back to the issue.

Run once:

```powershell
python scripts/local_dispatch_worker.py --once
```

Preview without posting comments, changing labels, or writing state:

```powershell
python scripts/local_dispatch_worker.py --once --dry-run --issue 8
```

Run continuously:

```powershell
python scripts/local_dispatch_worker.py --interval 300
```

Post prepared reply files:

```powershell
python scripts/local_dispatch_worker.py --once --post-replies
```

Run local Codex automatically for a single trusted issue:

```powershell
python scripts/local_dispatch_worker.py --once --issue 8 --follow-in-progress --auto-run-codex --allow-author naughtydream050-cloud
```

Create or inspect the resume summary template:

```powershell
python scripts/local_dispatch_worker.py --summary-template --issue 8
```

Options:

- `--repo naughtydream050-cloud/killstreet-insta-feed`
- `--once`
- `--interval 300`
- `--dry-run`
- `--post-replies`
- `--issue 8`
- `--follow-in-progress`
- `--summary-template`
- `--auto-run-codex`
- `--codex-command "codex"`
- `--allow-author naughtydream050-cloud`

By default, the worker reads only open issues with the `dispatch` label.
Use `--follow-in-progress` when you want to keep watching existing chat issues that already have `in-progress`.

Resume summary:

- On each issue, the durable restart file is `.codex-dispatch/issue-<number>-summary.md`.
- The worker creates a template if the summary does not exist.
- Each generated prompt includes the summary before the full comment history.
- When resuming after a long break, read the summary first, then the latest prompt.
- Long-term operation treats `summary.md` as the source of continuity. Old turn prompts and posted replies are auxiliary logs.
- After a substantial Codex reply, update the summary with the current goal, status, decisions, and next actions.
- Cleanup may remove old turn prompts and posted reply logs, but must keep `state.json` and `issue-<number>-summary.md`.

Authentication:

- Use `gh auth login` or set `GH_TOKEN` for the current shell.
- Do not save tokens in this repository.
- Do not put secrets in GitHub issue bodies.

Safety:

- The worker does not execute Codex automatically unless `--auto-run-codex` is explicitly set.
- Codex auto-run is disabled unless `--auto-run-codex` is set.
- Codex auto-run requires `--issue` and `--allow-author`.
- Codex auto-run skips when the latest comment author does not match `--allow-author`.
- Codex receives only the generated prompt file content.
- The worker does not call the OpenAI API.
- The worker does not execute issue comments as shell commands.
- The worker ignores issues with the `processed` label.
