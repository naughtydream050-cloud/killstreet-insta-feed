import argparse
import json
import os
import random
import subprocess
import sys
import textwrap
import time
import traceback
from datetime import datetime, timezone, timedelta
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from brand_copy_ai import select_brand_copy
from base_to_insta_feed import (
    BaseApiError,
    fetch_items,
    fetch_items_from_feed_fallback,
    get_base_token,
    is_public,
    item_key,
    _get_image_url,
    short_response_text,
)


DRY_RUN = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
DEBUG = os.environ.get("DEBUG", "false").strip().lower() == "true"
STORY_MAX_POSTS = int(os.environ.get("STORY_MAX_POSTS", "1"))
SHOP_URL = os.environ.get("SHOP_URL", "https://killstreet2.base.shop/").strip() or "https://killstreet2.base.shop/"
SHOP_URL_DISPLAY = os.environ.get("SHOP_URL_DISPLAY", "KILLSTREET2.BASE.SHOP").strip() or "KILLSTREET2.BASE.SHOP"
IG_TOKEN = os.environ.get("INSTAGRAM_TOKEN", "").strip()
IG_USER_ID = os.environ.get("IG_USER_ID", "").strip()
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "naughtydream050-cloud/killstreet-insta-feed").strip()
GITHUB_RUN_ID = os.environ.get("GITHUB_RUN_ID", str(int(time.time()))).strip()
PAGES_BASE_URL = os.environ.get(
    "PAGES_BASE_URL",
    f"https://{GITHUB_REPOSITORY.split('/')[0]}.github.io/{GITHUB_REPOSITORY.split('/')[-1]}",
).rstrip("/")

TEMPLATES_FILE = "story_templates.json"
HISTORY_FILE = os.environ.get("STORY_HISTORY_FILE", "story_history.json").strip() or "story_history.json"
PAYLOAD_FILE = os.environ.get("STORY_PAYLOAD_FILE", ".story_payload.json").strip() or ".story_payload.json"
OUTPUT_DIR = os.path.join("docs", "story", "generated")


def utc_now():
    return datetime.now(timezone.utc)


def select_template(template_type):
    if template_type and template_type != "auto":
        return template_type
    hour = utc_now().hour
    if hour == 0:
        return "morning_worldview"
    if hour == 6:
        return "afternoon_product"
    if hour == 12:
        return "night_cta"
    if hour < 6:
        return "morning_worldview"
    if hour < 12:
        return "afternoon_product"
    return "night_cta"


def load_templates():
    with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_story_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        stories = data.get("stories", [])
        if not isinstance(stories, list):
            print("[STORY HISTORY][WARN] stories is not a list; starting empty in memory")
            stories = []
        print(f"[STORY HISTORY] loaded={len(stories)}")
        return data, stories
    except FileNotFoundError:
        print("[STORY HISTORY] story_history.json not found - starting fresh")
    except json.JSONDecodeError as e:
        print(f"[STORY HISTORY][WARN] JSON parse failed: {e} - starting fresh in memory")
    return {
        "stories": [],
        "_comment": "Automatically maintained by GitHub Actions. Story history only. Do not edit manually.",
        "_schema": "asset_id as string, posted_at as UTC ISO-8601"
    }, []


def save_story_history(data, stories):
    data["stories"] = stories[-120:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[STORY HISTORY] Saved {len(data['stories'])} story records to {HISTORY_FILE}")


def fetch_assets():
    assets = fetch_instagram_media_assets()
    try:
        base_token = get_base_token()
        items = fetch_items(base_token)
        print("[STORY] BASE API source=base_api")
    except BaseApiError as e:
        print(f"[STORY][WARN] BASE API failed: {e}")
        items = fetch_items_from_feed_fallback()
        print("[STORY] BASE API source=feed_fallback")

    for item in items:
        if not is_public(item):
            continue
        key = item_key(item)
        image_url = _get_image_url(item)
        if not key or not image_url:
            print(f"[STORY][SKIP] missing stable key or image: key={key!r} title={str(item.get('title', ''))[:60]!r}")
            continue
        assets.append({
            "asset_type": "base_product",
            "id": str(key),
            "title": item.get("title", ""),
            "image_url": image_url,
            "permalink": item.get("item_url") or SHOP_URL,
            "price": item.get("price", 0),
        })
    print(f"[STORY] fetched_public={len([i for i in items if is_public(i)])} | usable_assets={len(assets)}")
    return assets


def fetch_instagram_media_assets():
    if not IG_TOKEN or not IG_USER_ID:
        print("[STORY] Instagram media source skipped: IG token/user not set")
        return []

    try:
        resp = requests.get(
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
            params={
                "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp",
                "limit": 25,
                "access_token": IG_TOKEN,
            },
            timeout=45,
        )
        print(f"[STORY] Instagram media fetch: HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"[STORY][WARN] Instagram media fetch failed: {short_response_text(resp, 500)}")
            return []
        rows = resp.json().get("data", [])
    except Exception as e:
        print(f"[STORY][WARN] Instagram media fetch exception: {e}")
        traceback.print_exc()
        return []

    assets = []
    for row in rows:
        image_url = row.get("thumbnail_url") or row.get("media_url") or ""
        media_id = str(row.get("id", "")).strip()
        if not media_id or not image_url:
            continue
        caption = str(row.get("caption", "")).strip()
        title = caption.splitlines()[0][:90] if caption else "KILL STREET"
        assets.append({
            "asset_type": "instagram_media",
            "id": media_id,
            "title": title,
            "image_url": image_url,
            "permalink": row.get("permalink") or SHOP_URL,
            "price": 0,
            "timestamp": row.get("timestamp", ""),
        })
    print(f"[STORY] instagram_media_assets={len(assets)}")
    return assets


def parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def select_asset(assets, story_records):
    if not assets:
        raise RuntimeError("No usable story assets")
    cutoff = utc_now() - timedelta(hours=24)
    recent_ids = {
        str(r.get("asset_id", ""))
        for r in story_records
        if parse_time(str(r.get("posted_at", ""))) >= cutoff
    }
    fresh = [a for a in assets if a["id"] not in recent_ids]
    if fresh:
        selected = fresh[0]
        print(f"[STORY] rotation=avoid_recent_24h recent={len(recent_ids)}")
    else:
        last_used = {}
        for r in story_records:
            last_used[str(r.get("asset_id", ""))] = parse_time(str(r.get("posted_at", "")))
        selected = sorted(assets, key=lambda a: last_used.get(a["id"], datetime.fromtimestamp(0, tz=timezone.utc)))[0]
        print("[STORY] rotation=all_recent_reuse_oldest")
    print(f"[STORY] selected_asset_type={selected['asset_type']}")
    print(f"[STORY] selected_id={selected['id']}")
    print(f"[STORY] selected_title_or_caption={selected['title']}")
    return selected


def font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/YuGothB.ttc" if bold else "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrapped(draw, text, max_width, fnt):
    lines = []
    for raw in str(text).splitlines():
        if not raw:
            lines.append("")
            continue
        line = ""
        for ch in raw:
            test = line + ch
            if draw.textbbox((0, 0), test, font=fnt)[2] <= max_width:
                line = test
            else:
                if line:
                    lines.append(line)
                line = ch
        if line:
            lines.append(line)
    return lines


def draw_centered_text(draw, text, y, fnt, fill, max_width, line_gap=10, shadow=True):
    lines = wrapped(draw, text, max_width, fnt)
    total_h = sum(draw.textbbox((0, 0), line, font=fnt)[3] for line in lines) + line_gap * max(0, len(lines) - 1)
    cy = y - total_h // 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=fnt)
        x = (1080 - (box[2] - box[0])) // 2
        if shadow:
            draw.text((x + 3, cy + 3), line, font=fnt, fill=(0, 0, 0, 180))
        draw.text((x, cy), line, font=fnt, fill=fill)
        cy += (box[3] - box[1]) + line_gap


def download_image(url):
    resp = requests.get(url, timeout=45)
    print(f"[STORY IMAGE] product image response: HTTP {resp.status_code}")
    if resp.status_code != 200:
        raise RuntimeError(f"Product image download failed: HTTP {resp.status_code}")
    return Image.open(BytesIO(resp.content)).convert("RGB")


def render_story_image(asset, template_type, copy_text):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    story_name = f"story_{GITHUB_RUN_ID}_{template_type}_{asset['id']}.jpg"
    output_path = os.path.join(OUTPUT_DIR, story_name)

    canvas = Image.new("RGB", (1080, 1920), (8, 8, 10))
    draw = ImageDraw.Draw(canvas, "RGBA")

    product = download_image(asset["image_url"])
    bg = ImageOps.fit(product, (1080, 1920), method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(24))
    bg = Image.blend(bg, Image.new("RGB", (1080, 1920), (5, 5, 7)), 0.62)
    canvas.paste(bg)
    draw.rectangle((0, 0, 1080, 1920), fill=(0, 0, 0, 90))

    header_h = 132
    draw.rounded_rectangle((42, 42, 1038, header_h), radius=32, fill=(255, 255, 255, 238))
    draw.ellipse((78, 62, 126, 110), fill=(12, 12, 14, 255))
    draw.text((148, 70), "killstreetbrand", font=font(36, True), fill=(20, 20, 22, 255))

    main_box = (90, 330, 990, 1260)
    product_fit = ImageOps.contain(product, (860, 860), method=Image.Resampling.LANCZOS)
    px = (1080 - product_fit.width) // 2
    py = 420 if template_type == "morning_worldview" else 360
    shadow = Image.new("RGBA", (product_fit.width + 50, product_fit.height + 50), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((25, 25, product_fit.width + 25, product_fit.height + 25), radius=28, fill=(0, 0, 0, 160))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.paste(shadow.convert("RGB"), (px - 25, py - 25), shadow)
    canvas.paste(product_fit, (px, py))

    if template_type == "morning_worldview":
        draw_centered_text(draw, copy_text, 265, font(66, True), (245, 245, 240, 255), 900, line_gap=16)
    elif template_type == "afternoon_product":
        draw_centered_text(draw, copy_text, 265, font(56, True), (245, 245, 240, 255), 900, line_gap=12)
    else:
        draw.rounded_rectangle((175, 235, 905, 330), radius=22, fill=(246, 246, 241, 240))
        draw_centered_text(draw, "送料無料", 282, font(58, True), (12, 12, 14, 255), 680, shadow=False)
        draw_centered_text(draw, copy_text, 372, font(42, True), (245, 245, 240, 255), 900, line_gap=10)

    sticker_y = 1280
    draw.rounded_rectangle((210, sticker_y, 870, sticker_y + 98), radius=34, fill=(255, 255, 255, 245))
    draw_centered_text(draw, SHOP_URL_DISPLAY, sticker_y + 50, font(38, True), (20, 20, 22, 255), 600, shadow=False)

    draw.rounded_rectangle((94, 1468, 986, 1698), radius=34, fill=(250, 250, 246, 232))
    title = asset["title"] or "KILL STREET"
    card_text = f"killstreetbrand {title}"
    card_lines = wrapped(draw, card_text, 800, font(38, True))[:3]
    y = 1515
    for line in card_lines:
        draw_centered_text(draw, line, y, font(38, True), (18, 18, 20, 255), 820, shadow=False)
        y += 46

    draw_centered_text(draw, "プロフィールリンクから購入", 1782, font(44, True), (248, 248, 244, 255), 900)
    draw_centered_text(draw, SHOP_URL_DISPLAY, 1844, font(34, True), (248, 248, 244, 255), 900)

    canvas.save(output_path, "JPEG", quality=92, optimize=True)
    print(f"[STORY IMAGE] generated_story_image_path={output_path}")
    return output_path, f"{PAGES_BASE_URL}/story/generated/{story_name}"


def load_payload(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_payload(payload):
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[STORY] payload_file={PAYLOAD_FILE}")


def git_commit_generated_image(path):
    if DRY_RUN:
        return
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", path], check=True)
        diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff.returncode == 0:
            print("[STORY IMAGE] No generated image changes to commit")
            return
        subprocess.run(["git", "commit", "-m", "chore: publish story image [skip ci]"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("[STORY IMAGE] generated story image pushed for public URL")
    except Exception as e:
        print(f"[STORY IMAGE][WARN] Could not commit generated image before posting: {e}")


def ig_publish_story(image_url):
    print(f"[IG STORY] DRY_RUN={DRY_RUN} | IG_USER_ID set={bool(IG_USER_ID)} | IG_TOKEN set={bool(IG_TOKEN)}")
    if DRY_RUN:
        print("[DRY RUN] Instagram story posting skipped")
        return True, "dry-run"
    if not IG_TOKEN or not IG_USER_ID:
        print("[IG STORY][ERROR] INSTAGRAM_TOKEN or IG_USER_ID not set")
        return False, ""

    try:
        create_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
        resp1 = requests.post(create_url, data={
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": IG_TOKEN,
        }, timeout=60)
        print(f"[IG STORY] Step 1 create container: HTTP {resp1.status_code}")
        print(f"[IG STORY] Step 1 body: {short_response_text(resp1, 800)}")
        if resp1.status_code != 200:
            return False, ""
        creation_id = resp1.json().get("id")
        if not creation_id:
            print("[IG STORY][ERROR] creation_id missing")
            return False, ""

        time.sleep(8)
        publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
        resp2 = requests.post(publish_url, data={
            "creation_id": creation_id,
            "access_token": IG_TOKEN,
        }, timeout=60)
        print(f"[IG STORY] Step 2 publish: HTTP {resp2.status_code}")
        print(f"[IG STORY] Step 2 body: {short_response_text(resp2, 800)}")
        if resp2.status_code != 200:
            return False, ""
        story_id = resp2.json().get("id", "unknown")
        print(f"[IG STORY] SUCCESS story_id={story_id}")
        return True, story_id
    except Exception as e:
        print(f"[IG STORY][ERROR] Exception while publishing: {e}")
        traceback.print_exc()
        return False, ""


def prepare_story(template_type):
    templates = load_templates()
    selected_template = select_template(template_type)
    if selected_template not in templates:
        raise RuntimeError(f"Unknown template_type={selected_template}")

    print(f"[STORY] selected_template={selected_template}")
    assets = fetch_assets()
    history_data, records = load_story_history()
    asset = select_asset(assets, records)
    copy_result = select_brand_copy(selected_template, templates[selected_template]["copy_bank"])
    image_path, public_url = render_story_image(asset, selected_template, copy_result["copy"])
    print(f"[STORY] public_story_image_url={public_url}")
    print(f"[STORY] story_link_url={SHOP_URL}")
    print("[STORY] link_sticker=false official_api_image_only=true")

    payload = {
        "selected_template": selected_template,
        "asset": asset,
        "copy": copy_result,
        "generated_story_image_path": image_path,
        "public_story_image_url": public_url,
        "story_link_url": SHOP_URL,
        "prepared_at": utc_now().isoformat().replace("+00:00", "Z"),
    }
    write_payload(payload)
    if DRY_RUN:
        print("[STORY HISTORY][DRY RUN] Not recording story history")
    return payload


def post_prepared(payload_path):
    payload = load_payload(payload_path)
    ok, story_id = ig_publish_story(payload["public_story_image_url"])
    if not ok:
        print("[STORY HISTORY] Not updating story_history.json because Instagram story publish failed")
        sys.exit(1)
    if DRY_RUN:
        print("[STORY HISTORY][DRY RUN] Not recording story history")
        return

    history_data, records = load_story_history()
    records.append({
        "asset_id": str(payload["asset"]["id"]),
        "asset_type": payload["asset"]["asset_type"],
        "title": payload["asset"]["title"],
        "template": payload["selected_template"],
        "story_id": story_id,
        "image_url": payload["public_story_image_url"],
        "shop_url": SHOP_URL,
        "posted_at": utc_now().isoformat().replace("+00:00", "Z"),
    })
    save_story_history(history_data, records)
    print(f"[STORY HISTORY] Recorded asset_id={payload['asset']['id']}")


def main():
    parser = argparse.ArgumentParser(description="Post KILL STREET brand story")
    parser.add_argument("--prepare-only", action="store_true", help="Generate story image and payload only")
    parser.add_argument("--post-prepared", help="Post a previously prepared payload JSON")
    parser.add_argument("--template-type", default=os.environ.get("TEMPLATE_TYPE", "auto"))
    args = parser.parse_args()

    print("[STORY] === KILL STREET Brand Story Auto-Post ===")
    print(f"[STORY] DRY_RUN={DRY_RUN} | STORY_MAX_POSTS={STORY_MAX_POSTS} | DEBUG={DEBUG}")
    print(f"[STORY] SHOP_URL={SHOP_URL} | SHOP_URL_DISPLAY={SHOP_URL_DISPLAY}")
    if STORY_MAX_POSTS != 1:
        print("[STORY][WARN] STORY_MAX_POSTS is accepted for workflow parity, but this job posts exactly 1 story per run")

    if args.post_prepared:
        post_prepared(args.post_prepared)
        return

    payload = prepare_story(args.template_type)
    if args.prepare_only:
        return

    if not DRY_RUN:
        git_commit_generated_image(payload["generated_story_image_path"])
    post_prepared(PAYLOAD_FILE)


if __name__ == "__main__":
    main()
