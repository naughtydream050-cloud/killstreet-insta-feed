import json
import os
import random
import re
import traceback

import requests


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
COPY_AI_PROVIDER = os.environ.get("COPY_AI_PROVIDER", "gemini").strip().lower() or "gemini"
COPY_AI_FALLBACK = os.environ.get("COPY_AI_FALLBACK", "true").strip().lower() != "false"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"


def _safe_json_from_text(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _fallback_copy(copy_bank, reason):
    copy = random.choice(copy_bank) if copy_bank else "ストリートを、飾る。"
    print(f"[COPY] fallback_used=true reason={reason}")
    print(f"[COPY] ai_copy_used=false")
    print(f"[COPY] ai_copy_selected={copy}")
    print("[COPY] ai_copy_score=0")
    return {
        "copy": copy,
        "score": 0,
        "ai_used": False,
        "fallback_used": True,
        "provider": COPY_AI_PROVIDER,
    }


def select_brand_copy(template_type, copy_bank):
    print(f"[COPY] copy_ai_provider={COPY_AI_PROVIDER}")
    if template_type != "morning_worldview":
        return _fallback_copy(copy_bank, "fixed-template")

    if COPY_AI_PROVIDER != "gemini":
        return _fallback_copy(copy_bank, "provider-disabled")
    if not GEMINI_API_KEY:
        return _fallback_copy(copy_bank, "GEMINI_API_KEY not set")

    prompt = """
KILL STREETのInstagramストーリー用コピーを1つ作ってください。
条件:
- 日本語中心
- 1行8〜18文字程度
- 最大2行まで
- ダークコア、退廃、鑑賞芸術、飾るダンス着、ストリート
- 説明しすぎない
- 安っぽい煽りにしない
- 他ブランドのコピーを真似しない
- ブランド名を連呼しない

必ずJSONだけで返してください。
{
  "candidates": [
    {"copy": "ストリートを、飾る。", "score": 94, "reason": "短い理由"}
  ],
  "selected": {"copy": "ストリートを、飾る。", "score": 94}
}
""".strip()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 160,
            "responseMimeType": "application/json"
        }
    }
    try:
        resp = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        print(f"[COPY] Gemini response: HTTP {resp.status_code}")
        if resp.status_code != 200:
            return _fallback_copy(copy_bank, f"Gemini HTTP {resp.status_code}")

        data = resp.json()
        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        parsed = _safe_json_from_text(text)
        selected = (parsed or {}).get("selected", {})
        copy = str(selected.get("copy", "")).strip()
        score = int(selected.get("score", 0) or 0)
        if not copy:
            return _fallback_copy(copy_bank, "Gemini JSON missing selected.copy")

        print("[COPY] ai_copy_used=true")
        print("[COPY] fallback_used=false")
        print(f"[COPY] ai_copy_selected={copy}")
        print(f"[COPY] ai_copy_score={score}")
        return {
            "copy": copy,
            "score": score,
            "ai_used": True,
            "fallback_used": False,
            "provider": COPY_AI_PROVIDER,
        }
    except Exception as e:
        print(f"[COPY][WARN] Gemini failed: {e}")
        traceback.print_exc()
        if COPY_AI_FALLBACK:
            return _fallback_copy(copy_bank, "Gemini exception")
        raise
