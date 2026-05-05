# Local Dispatch Worker

This repository can be controlled from a phone without running OpenAI API calls in GitHub Actions.

Flow:

1. Create a GitHub issue from the phone.
2. Add the `dispatch` label.
3. Run the local worker on the PC.
4. The worker saves the issue body to `.codex-dispatch/issue-<number>-prompt.md`.
5. The worker comments on the issue and adds `in-progress`.
6. Open the generated prompt file in Codex on the PC.

Run once:

```powershell
python scripts/local_dispatch_worker.py --once
```

Run continuously:

```powershell
python scripts/local_dispatch_worker.py --interval 300
```

Authentication:

- Use `gh auth login` or set `GH_TOKEN` for the current shell.
- Do not save tokens in this repository.
- Do not put secrets in GitHub issue bodies.

The worker does not execute Codex automatically. It only receives the phone dispatch and prepares a local prompt.
