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
7. The worker comments on the issue and adds `in-progress`.
8. Open the generated prompt file in Codex on the PC.
9. Put the reply in `.codex-dispatch/issue-<number>-reply.md`.
10. Run the worker with `--post-replies` to post that reply back to the issue.

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

Options:

- `--repo naughtydream050-cloud/killstreet-insta-feed`
- `--once`
- `--interval 300`
- `--dry-run`
- `--post-replies`
- `--issue 8`
- `--follow-in-progress`

By default, the worker reads only open issues with the `dispatch` label.
Use `--follow-in-progress` when you want to keep watching existing chat issues that already have `in-progress`.

Authentication:

- Use `gh auth login` or set `GH_TOKEN` for the current shell.
- Do not save tokens in this repository.
- Do not put secrets in GitHub issue bodies.

Safety:

- The worker does not execute Codex automatically.
- The worker does not call the OpenAI API.
- The worker does not execute issue comments as shell commands.
- The worker ignores issues with the `processed` label.
