# KILLSTREET Instagram Auto-Post — Standard Specification

> This document is the official project specification.
> All agents (Codex, successors, developers) must follow this spec for implementation and modifications.

---

## 1. Project Overview

Auto-post system for KILLSTREET BASE shop (killstreet2) to Instagram Graph API.
GitHub Actions fetches BASE items -> filters to unposted only -> posts to Instagram -> persists post history.

---

## 2. Schedule Specification (MUST MAINTAIN)

Current setting: cron '0 13 * * 0'  = Sunday 13:00 UTC = Sunday 22:00 JST

IMPORTANT - Day clarification:
- Current cron * * 0 = SUNDAY (GitHub Actions cron: 0=Sunday, 1=Monday)
- If representative intends MONDAY, change to * * 1:
  cron '0 13 * * 1'  = Monday 13:00 UTC = Monday 22:00 JST

AGENT INSTRUCTION: "月曜の自動投稿は維持せよ" (Maintain Monday auto-post) — Representative command.
If switching to Monday operation, use * * 1.
Always confirm day/time with representative before changing cron.

---

## 3. Deduplication System

### Architecture

Fetch all BASE items
  -> Load posted_history.json
  -> Filter to unposted items only
  -> Post to Instagram (update history after each success)
  -> Persist step: git commit & push [skip ci]

### posted_history.json Schema

{"posted": ["12345", "67890"], "_comment": "Auto-maintained by GitHub Actions. Do not edit manually.", "_schema": "item_id as string"}

- posted: array of posted item_id strings (sorted)
- Always kept current on GitHub
- [skip ci] in commit message prevents infinite trigger loop

### Implementation Files

| File | Role |
|------|------|
| base_to_insta_feed.py | Main script (includes dedup logic) |
| posted_history.json | Persistent store of posted IDs |
| .github/workflows/sync_feed.yml | CI definition including Persist step |

---

## 4. GitHub Actions Permissions

permissions:
  contents: write    # Required for git push (posted_history.json updates)
  pages: write       # Required for GitHub Pages (feed.xml) deployment
  id-token: write    # Required for Pages OIDC auth

- With contents: write, git push authenticates automatically via GITHUB_TOKEN
- Requires actions/checkout@v4 with persist-credentials: true (default)
- No additional Secrets or PAT needed

---

## 5. Required Secrets

| Secret | Purpose |
|--------|---------|
| BASE_CLIENT_ID | BASE OAuth2.0 Client ID |
| BASE_CLIENT_SECRET | BASE OAuth2.0 Client Secret |
| BASE_REFRESH_TOKEN | BASE refresh token for access token renewal |
| BASE_ACCESS_TOKEN | BASE access token (fallback) |
| INSTAGRAM_TOKEN | Instagram Graph API token |
| IG_USER_ID | Instagram Business Account ID |
| SHOP_ID | BASE shop ID (default: killstreet2) |

---

## 6. Manual Execution (workflow_dispatch)

Run workflow from GitHub Actions tab with optional parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| dry_run | false | If true, skip actual posting (confirmation run) |
| ig_max_posts | 1 | Max posts per CI run |
| debug | false | Verbose logging |

---

## 7. Token Rotation

BASE API refresh_token may rotate on each use.
Script automatically attempts gh secret set BASE_REFRESH_TOKEN update,
but if insufficient permissions, manual Secrets update is needed.
If log shows [AUTH] WARNING: Secrets auto-update failed, update manually.

---

## 8. Prohibited Changes (for successor agents)

- Do NOT manually clear the posted array in posted_history.json
- Do NOT remove [skip ci] from the persist commit message (causes infinite loop)
- Do NOT remove permissions: contents: write (breaks Persist step)
- Do NOT change cron schedule without representative approval

---

## 9. Change Log

| Date | Change |
|------|--------|
| 2026-05-01 | Deduplication system implemented (posted_history.json) |
| 2026-05-01 | Persist step added (CI-based history persistence) |
| 2026-05-01 | This specification document created |
