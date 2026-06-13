import base64
import json
import os
import sys
import time
from typing import Any, Callable

import requests


GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v25.0").strip()
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "naughtydream050-cloud/killstreet-insta-feed").strip()
IG_REFRESH_THRESHOLD_DAYS = int(os.environ.get("IG_REFRESH_THRESHOLD_DAYS", "14"))


REQUIRED_IG_SCOPES = {
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
}


def now_epoch() -> int:
    return int(time.time())


def safe_print(record: dict[str, Any]) -> None:
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))


def short_error(response: requests.Response, limit: int = 240) -> str:
    try:
        data = response.json()
        message = data.get("error_description") or data.get("error", {}).get("message") or data.get("error")
        if message:
            return str(message)[:limit]
    except Exception:
        pass
    return (response.text or "")[:limit].replace("\n", "\\n")


def update_github_secret(secret_name: str, secret_value: str) -> bool:
    gh_token = os.environ.get("GH_PAT_SECRETS", "").strip()
    if not gh_token:
        safe_print({"component": "github_secret", "secret": secret_name, "status": "skipped", "reason": "GH_PAT_SECRETS not set"})
        return False

    try:
        from nacl import public as nacl_public
    except ImportError:
        safe_print({"component": "github_secret", "secret": secret_name, "status": "skipped", "reason": "PyNaCl not installed"})
        return False

    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    key_resp = requests.get(f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key", headers=headers, timeout=30)
    if key_resp.status_code != 200:
        safe_print({"component": "github_secret", "secret": secret_name, "status": "failed", "http": key_resp.status_code})
        return False

    key_data = key_resp.json()
    public_key = nacl_public.PublicKey(base64.b64decode(key_data["key"]))
    encrypted = nacl_public.SealedBox(public_key).encrypt(secret_value.encode("utf-8"))
    put_resp = requests.put(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
        headers=headers,
        json={"encrypted_value": base64.b64encode(encrypted).decode("utf-8"), "key_id": key_data["key_id"]},
        timeout=30,
    )
    ok = put_resp.status_code in (201, 204)
    safe_print({"component": "github_secret", "secret": secret_name, "status": "updated" if ok else "failed", "http": put_resp.status_code})
    return ok


def check_instagram(
    session: requests.Session,
    token: str,
    ig_user_id: str,
    secret_updater: Callable[[str, str], bool] = update_github_secret,
    refresh_threshold_days: int = IG_REFRESH_THRESHOLD_DAYS,
) -> dict[str, Any]:
    if not token or not ig_user_id:
        return {"component": "instagram", "status": "missing", "reason": "INSTAGRAM_TOKEN or IG_USER_ID not set"}

    debug = session.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/debug_token",
        params={"input_token": token, "access_token": token},
        timeout=30,
    )
    if debug.status_code != 200:
        return {"component": "instagram", "status": "invalid", "http": debug.status_code, "reason": short_error(debug)}

    data = debug.json().get("data", {})
    if not data.get("is_valid"):
        return {"component": "instagram", "status": "invalid", "reason": "debug_token reported invalid"}

    scopes = set(data.get("scopes") or [])
    missing_scopes = sorted(REQUIRED_IG_SCOPES - scopes)
    expires_at = int(data.get("expires_at") or 0)
    seconds_left = expires_at - now_epoch() if expires_at else None
    days_left = round(seconds_left / 86400, 2) if seconds_left is not None else None
    base = {
        "component": "instagram",
        "status": "valid",
        "expires_at": expires_at or None,
        "days_left": days_left,
        "missing_scopes": missing_scopes,
    }
    if missing_scopes:
        base["status"] = "permission_missing"
        return base

    probe = session.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_user_id}",
        params={"fields": "id,username", "access_token": token},
        timeout=30,
    )
    if probe.status_code != 200:
        base.update({"status": "permission_missing", "http": probe.status_code, "reason": short_error(probe)})
        return base

    if seconds_left is None:
        base["refresh_status"] = "unknown_expiry"
        return base
    if seconds_left <= 0:
        base["status"] = "expired"
        base["refresh_status"] = "manual_reauth_required"
        return base
    if seconds_left > refresh_threshold_days * 86400:
        base["refresh_status"] = "not_needed"
        return base

    refreshed = session.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=30,
    )
    if refreshed.status_code != 200 or not refreshed.json().get("access_token"):
        base.update({"status": "valid_refresh_failed", "refresh_status": "manual_reauth_required", "refresh_http": refreshed.status_code, "reason": short_error(refreshed)})
        return base

    new_token = refreshed.json()["access_token"]
    if secret_updater("INSTAGRAM_TOKEN", new_token):
        base.update({"status": "refreshed", "refresh_status": "secret_updated"})
    else:
        base.update({"status": "valid_refresh_not_saved", "refresh_status": "secret_update_failed"})
    return base


def check_base(
    session: requests.Session,
    access_token: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    secret_updater: Callable[[str, str], bool] = update_github_secret,
) -> dict[str, Any]:
    if not access_token:
        current = requests.Response()
        current.status_code = 401
    else:
        current = session.get("https://api.thebase.in/1/items", params={"limit": "1"}, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)

    if current.status_code == 200:
        return {"component": "base", "status": "valid"}

    base = {"component": "base", "status": "access_invalid", "http": current.status_code, "reason": short_error(current)}
    if not (refresh_token and client_id and client_secret):
        base.update({"refresh_status": "manual_reauth_required", "reason": "refresh token or client credentials missing"})
        return base

    refreshed = session.post(
        "https://api.thebase.in/1/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    if refreshed.status_code != 200:
        base.update({"status": "refresh_failed", "refresh_http": refreshed.status_code, "refresh_status": "manual_reauth_required", "reason": short_error(refreshed)})
        return base

    payload = refreshed.json()
    new_access = payload.get("access_token", "")
    new_refresh = payload.get("refresh_token", refresh_token)
    if not new_access:
        base.update({"status": "refresh_failed", "refresh_status": "manual_reauth_required", "reason": "refresh response missing access_token"})
        return base

    verify = session.get("https://api.thebase.in/1/items", params={"limit": "1"}, headers={"Authorization": f"Bearer {new_access}"}, timeout=30)
    if verify.status_code != 200:
        base.update({"status": "refresh_verify_failed", "refresh_status": "manual_reauth_required", "verify_http": verify.status_code, "reason": short_error(verify)})
        return base

    saved_access = secret_updater("BASE_ACCESS_TOKEN", new_access)
    saved_refresh = secret_updater("BASE_REFRESH_TOKEN", new_refresh)
    base.update({"status": "refreshed" if saved_access and saved_refresh else "refreshed_not_saved", "refresh_status": "secret_updated" if saved_access and saved_refresh else "secret_update_failed"})
    return base


def check_hf(session: requests.Session, token: str) -> dict[str, Any]:
    if not token:
        return {"component": "huggingface", "status": "missing", "reason": "HF_TOKEN/HUGGINGFACE_TOKEN not set"}
    response = session.get("https://huggingface.co/api/whoami-v2", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if response.status_code == 200:
        data = response.json()
        return {"component": "huggingface", "status": "valid", "user": data.get("name"), "type": data.get("type")}
    if response.status_code in (401, 403):
        return {"component": "huggingface", "status": "invalid", "http": response.status_code}
    return {"component": "huggingface", "status": "unknown", "http": response.status_code, "reason": short_error(response)}


def classify_hf_generation_error(message: str) -> str:
    text = (message or "").lower()
    if "zerogpu quota" in text or "quota" in text or "no gpu was available" in text:
        return "quota_limited"
    if "unauthorized" in text or "invalid token" in text or "401" in text or "403" in text:
        return "token_invalid"
    return "generation_failed"


def main() -> int:
    session = requests.Session()
    results = [
        check_instagram(session, os.environ.get("INSTAGRAM_TOKEN", "").strip(), os.environ.get("IG_USER_ID", "").strip()),
        check_base(
            session,
            os.environ.get("BASE_ACCESS_TOKEN", "").strip(),
            os.environ.get("BASE_REFRESH_TOKEN", "").strip(),
            os.environ.get("BASE_CLIENT_ID", "").strip(),
            os.environ.get("BASE_CLIENT_SECRET", "").strip(),
        ),
        check_hf(session, (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()),
    ]
    for result in results:
        safe_print(result)

    failing = {"missing", "invalid", "expired", "permission_missing", "refresh_failed", "refresh_verify_failed", "refreshed_not_saved", "valid_refresh_not_saved"}
    return 1 if any(result.get("status") in failing for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
