import os
import sys
import json
import time
import base64
import traceback
import argparse
import html
import re
import requests
import xml.etree.ElementTree as ET

# ── Environment variables ─────────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("BASE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("BASE_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.environ.get("BASE_REFRESH_TOKEN", "").strip()
ACCESS_TOKEN  = os.environ.get("BASE_ACCESS_TOKEN", "").strip()
SHOP_ID       = os.environ.get("SHOP_ID", "").strip() or "killstreet2"
IG_TOKEN      = os.environ.get("INSTAGRAM_TOKEN", "").strip()
IG_USER_ID    = os.environ.get("IG_USER_ID", "").strip()
IG_MAX_POSTS      = int(os.environ.get("IG_MAX_POSTS", "1"))
DEBUG             = os.environ.get("DEBUG", "false").lower() == "true"
DRY_RUN           = os.environ.get("DRY_RUN", "false").lower() == "true"
GH_PAT_SECRETS    = os.environ.get("GH_PAT_SECRETS", "").strip()
GH_REPO           = "naughtydream050-cloud/killstreet-insta-feed"
TEST_ITEMS_JSON   = os.environ.get("TEST_ITEMS_JSON", "").strip()
TEST_ITEMS_FILE   = os.environ.get("TEST_ITEMS_FILE", "").strip()
FEED_FALLBACK_URL = "https://naughtydream050-cloud.github.io/killstreet-insta-feed/feed.xml"
BASE_SHOP_URL     = os.environ.get("BASE_SHOP_URL", "https://killstreet2.base.shop/").strip() or "https://killstreet2.base.shop/"


class BaseApiError(RuntimeError):
    pass


def short_response_text(resp, limit=500):
    return (resp.text or "").replace("\n", "\\n")[:limit]


def apply_cli_overrides():
    global DEBUG, DRY_RUN, IG_MAX_POSTS, TEST_ITEMS_JSON, TEST_ITEMS_FILE, HISTORY_FILE

    parser = argparse.ArgumentParser(description="Sync BASE products to Instagram")
    parser.add_argument("--dry-run", action="store_true",
                        help="Select and log a product without Instagram posting or history update")
    parser.add_argument("--debug", action="store_true", help="Enable debug logs")
    parser.add_argument("--ig-max-posts", type=int, help="Maximum Instagram posts per run")
    parser.add_argument("--test-items-json", help="JSON list/object used instead of BASE API")
    parser.add_argument("--test-items-file", help="Path to a JSON file used instead of BASE API")
    parser.add_argument("--history-file", help="Path to posted history JSON")
    args = parser.parse_args()

    if args.dry_run:
        DRY_RUN = True
    if args.debug:
        DEBUG = True
    if args.ig_max_posts is not None:
        IG_MAX_POSTS = args.ig_max_posts
    if args.test_items_json:
        TEST_ITEMS_JSON = args.test_items_json
    if args.test_items_file:
        TEST_ITEMS_FILE = args.test_items_file
    if args.history_file:
        HISTORY_FILE = args.history_file


# ── GitHub Secret auto-updater (PyNaCl + REST API) ───────────────────────────
def update_github_secret(secret_name, secret_value):
    """
    GitHub REST API + PyNaCl を使って Actions Secret を自動更新する。
    GH_PAT_SECRETS に secrets:write スコープの fine-grained PAT が必要。
    """
    if not GH_PAT_SECRETS:
        print(f"[SECRET] GH_PAT_SECRETS not set -> cannot auto-rotate {secret_name}")
        return False

    try:
        from nacl import public as nacl_public
    except ImportError:
        print("[SECRET] PyNaCl not installed -> skipping secret update")
        return False

    headers = {
        "Authorization": f"Bearer {GH_PAT_SECRETS}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Step 1: リポジトリの公開鍵を取得（暗号化に必要）
    try:
        key_resp = requests.get(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
            headers=headers, timeout=30
        )
        print(f"[SECRET] Public key fetch: HTTP {key_resp.status_code}")
        if key_resp.status_code != 200:
            print(f"[SECRET] Public key error: {key_resp.text[:300]}")
            return False
        key_data = key_resp.json()
        key_id = key_data["key_id"]
        pub_key_bytes = base64.b64decode(key_data["key"])
    except Exception as e:
        print(f"[SECRET] Exception fetching public key: {e}")
        traceback.print_exc()
        return False

    # Step 2: libsodium SealedBox で暗号化
    try:
        sealed_box = nacl_public.SealedBox(nacl_public.PublicKey(pub_key_bytes))
        encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
        encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")
    except Exception as e:
        print(f"[SECRET] Encryption failed: {e}")
        traceback.print_exc()
        return False

    # Step 3: PUT で Secret を上書き
    try:
        put_resp = requests.put(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
            headers=headers,
            json={"encrypted_value": encrypted_b64, "key_id": key_id},
            timeout=30
        )
        print(f"[SECRET] PUT {secret_name}: HTTP {put_resp.status_code}")
        if put_resp.status_code in (201, 204):
            print(f"[SECRET] ✅ {secret_name} auto-rotated successfully via GitHub API")
            return True
        else:
            print(f"[SECRET] ❌ PUT failed: {put_resp.text[:300]}")
            return False
    except Exception as e:
        print(f"[SECRET] Exception updating secret: {e}")
        traceback.print_exc()
        return False


# ── BASE authentication ───────────────────────────────────────────────────────
def get_base_token():
    print(f"[AUTH] REFRESH_TOKEN set: {bool(REFRESH_TOKEN)} | CLIENT_ID set: {bool(CLIENT_ID)}")
    if REFRESH_TOKEN and CLIENT_ID and CLIENT_SECRET:
        print("[AUTH] Requesting access token via refresh_token...")
        try:
            resp = requests.post("https://api.thebase.in/1/oauth/token", data={
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": REFRESH_TOKEN,
            }, timeout=30)
            print(f"[AUTH] Token response: HTTP {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                new_rt = data.get("refresh_token", "")
                if new_rt and new_rt != REFRESH_TOKEN:
                    print("[AUTH] refresh_token rotated -> attempting Secrets auto-update via GitHub API")
                    if not update_github_secret("BASE_REFRESH_TOKEN", new_rt):
                        print("[AUTH] WARNING: Secrets auto-update failed - update BASE_REFRESH_TOKEN manually")
                print("[AUTH] BASE access token obtained successfully")
                return data["access_token"]
            else:
                print(f"[AUTH ERROR] Refresh token exchange failed: HTTP {resp.status_code} -> {short_response_text(resp, 300)}")
        except Exception as e:
            print(f"[AUTH ERROR] Exception during token refresh: {e}")
            traceback.print_exc()

    if ACCESS_TOKEN:
        print("[AUTH] Using BASE_ACCESS_TOKEN as fallback after refresh_token path failed")
        return ACCESS_TOKEN

    print("[AUTH ERROR] Neither BASE_REFRESH_TOKEN nor BASE_ACCESS_TOKEN is set.")
    raise BaseApiError("No BASE token available")


# ── BASE item helpers ─────────────────────────────────────────────────────────
def is_public(item):
    visible = item.get("visible", item.get("is_visible", None))
    if visible in (True, 1, "1", "true"):
        return True
    status = str(item.get("status", "")).lower()
    return status in ("selling", "published", "visible", "active")


def item_key(item):
    key = item.get("item_id")
    if key not in (None, ""):
        return str(key)

    url = item.get("item_url") or item.get("url")
    if url:
        return str(url).strip()

    return ""


def item_label(item):
    key = item_key(item) or "(no-key)"
    title = str(item.get("title", ""))[:60]
    return f"key={key!r} title={title!r}"


def _get_image_url(item):
    item_id = item.get("item_id")

    # Pattern 1: nested images array (standard)
    imgs = item.get("images", [])
    if imgs:
        img = imgs[0]
        if DEBUG:
            print(f"[IMG DEBUG] id={item_id} image keys={list(img.keys())} | raw={json.dumps(img, ensure_ascii=False)[:300]}")
        url = (img.get("original") or img.get("origin") or
               img.get("url") or img.get("large") or "")
        if url:
            print(f"[IMG] id={item_id} -> {url[:80]}")
            return url

    # Pattern 2: flat fields  img1_origin, img1_url, img1_thumb_url, etc.
    for suffix in ("origin", "url", "thumb_url"):
        for prefix in ("img1", "image1", "img"):
            key = f"{prefix}_{suffix}"
            val = item.get(key, "")
            if val:
                print(f"[IMG] id={item_id} -> found via key '{key}': {val[:80]}")
                return val

    # Pattern 3: legacy flat keys
    fallback = (item.get("list_image_url") or item.get("detail_image_url") or
                item.get("image_url") or "")
    if fallback:
        print(f"[IMG] id={item_id} -> fallback key: {fallback[:80]}")
    else:
        print(f"[IMG] id={item_id} -> no image URL found. Available keys: {[k for k in item.keys() if 'img' in k.lower() or 'image' in k.lower()]}")
    return fallback


# ── BASE item fetching ────────────────────────────────────────────────────────
def fetch_items(base_token):
    headers = {"Authorization": f"Bearer {base_token}"}
    items, limit, offset = [], 100, 0
    print("[INFO] Fetching items from BASE API...")
    while True:
        params = {"limit": limit, "offset": offset, "order": "new"}
        try:
            r = requests.get("https://api.thebase.in/1/items", headers=headers, params=params, timeout=30)
        except Exception as e:
            print(f"[BASE ERROR] Request exception while fetching /1/items: {e}")
            traceback.print_exc()
            raise BaseApiError("BASE /1/items request failed") from e

        print(f"[INFO] BASE API response: HTTP {r.status_code} | offset={offset}")
        if r.status_code == 401:
            print(f"[BASE ERROR] /1/items unauthorized: HTTP 401 -> {short_response_text(r)}")
            raise BaseApiError("BASE /1/items unauthorized")
        if r.status_code == 403:
            print(f"[BASE ERROR] /1/items forbidden: HTTP 403 -> {short_response_text(r)}")
            raise BaseApiError("BASE /1/items forbidden")
        if r.status_code != 200:
            print(f"[BASE ERROR] /1/items failed: HTTP {r.status_code} -> {short_response_text(r)}")
            raise BaseApiError(f"BASE /1/items returned HTTP {r.status_code}")
        data = r.json()
        if "items" not in data:
            print(f"[BASE ERROR] 'items' key not found in response: {json.dumps(data)[:500]}")
            raise BaseApiError("BASE /1/items response missing items")
        batch = data["items"]
        if offset == 0 and batch:
            print(f"[INFO] Field names: {list(batch[0].keys())}")
        if DEBUG and batch:
            print(f"[DEBUG] First item raw: {json.dumps(batch[0], ensure_ascii=False)[:1000]}")
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    print(f"[INFO] Total {len(items)} items fetched")
    for it in items:
        v = it.get("visible", it.get("is_visible", "N/A"))
        s = it.get("status", "N/A")
        title = str(it.get("title", ""))[:30]
        pub = is_public(it)
        print(f"  id={it.get('item_id')} status={s!r} visible={v!r} public={pub} title={title!r}")
    return items


def load_test_items():
    if TEST_ITEMS_FILE:
        try:
            with open(TEST_ITEMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = data.get("items", [])
            if not isinstance(data, list):
                print("[TEST][ERROR] TEST_ITEMS_FILE must contain a JSON list or an object with an items list")
                sys.exit(1)
            print(f"[TEST] Loaded {len(data)} items from TEST_ITEMS_FILE={TEST_ITEMS_FILE}")
            return data
        except OSError as e:
            print(f"[TEST][ERROR] Failed to read TEST_ITEMS_FILE={TEST_ITEMS_FILE}: {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"[TEST][ERROR] Failed to parse TEST_ITEMS_FILE={TEST_ITEMS_FILE}: {e}")
            sys.exit(1)

    if not TEST_ITEMS_JSON:
        return None
    try:
        data = json.loads(TEST_ITEMS_JSON)
        if isinstance(data, dict):
            data = data.get("items", [])
        if not isinstance(data, list):
            print("[TEST][ERROR] TEST_ITEMS_JSON must be a JSON list or an object with an items list")
            sys.exit(1)
        print(f"[TEST] Loaded {len(data)} items from TEST_ITEMS_JSON")
        return data
    except json.JSONDecodeError as e:
        print(f"[TEST][ERROR] Failed to parse TEST_ITEMS_JSON: {e}")
        sys.exit(1)


def parse_price(value):
    text = str(value or "")
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else 0


def clean_base_title(value):
    text = html.unescape(str(value or "")).strip()
    text = re.sub(r"\s*\|\s*KILL\s*STREET.*$", "", text, flags=re.I)
    text = re.sub(r"\s*\|\s*KILLSTREET.*$", "", text, flags=re.I)
    text = re.sub(r"\s*[-|]\s*BASE\s*$", "", text, flags=re.I)
    return text.strip()


def product_id_from_url(url):
    m = re.search(r"/items/(\d+)", str(url or ""))
    return m.group(1) if m else ""


def html_meta_content(page, name):
    patterns = [
        rf'<meta\s+property=["\']{re.escape(name)}["\']\s+content=["\']([^"\']+)["\']',
        rf'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']{re.escape(name)}["\']',
        rf'<meta\s+name=["\']{re.escape(name)}["\']\s+content=["\']([^"\']+)["\']',
        rf'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, page, flags=re.I)
        if m:
            return html.unescape(m.group(1)).replace("\\/", "/").strip()
    return ""


def xml_child_text(node, tag):
    for child in node:
        if child.tag.split("}", 1)[-1] == tag:
            return child.text or ""
    return ""


def parse_feed_items(feed_xml, source):
    try:
        root = ET.fromstring(feed_xml)
    except ET.ParseError as e:
        print(f"[FEED FALLBACK][ERROR] Failed to parse feed from {source}: {e}")
        return []

    items = []
    for node in root.findall(".//item"):
        item_id = xml_child_text(node, "id").strip()
        title = xml_child_text(node, "title").strip()
        link = xml_child_text(node, "link").strip()
        image_url = xml_child_text(node, "image_link").strip()
        detail = xml_child_text(node, "description").strip()
        price = parse_price(xml_child_text(node, "price"))
        if not item_id:
            print(f"[FEED FALLBACK][SKIP] feed item without id: title={title[:60]!r}")
            continue
        if not link:
            print(f"[FEED FALLBACK][WARN] item_id={item_id} has empty g:link; Instagram caption product URL will be empty")
        items.append({
            "item_id": item_id,
            "title": title,
            "detail": detail,
            "item_url": link,
            "image_url": image_url,
            "price": price,
            "stock": 1,
            "visible": True,
            "status": "active",
        })

    print(f"[FEED FALLBACK] Loaded {len(items)} items from {source}")
    return items


def fetch_items_from_base_shop_scrape():
    print(f"[SHOP SCRAPE] Loading product URLs from {BASE_SHOP_URL}")
    try:
        resp = requests.get(BASE_SHOP_URL, timeout=30)
        print(f"[SHOP SCRAPE] shop response: HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise BaseApiError(f"BASE shop page returned HTTP {resp.status_code}")
    except Exception as e:
        print(f"[SHOP SCRAPE][ERROR] shop page request failed: {e}")
        traceback.print_exc()
        raise BaseApiError("BASE shop scrape failed") from e

    urls = []
    for raw in re.findall(r'(?:https://killstreet2\.base\.shop)?/items/\d+', resp.text):
        url = raw if raw.startswith("http") else f"https://killstreet2.base.shop{raw}"
        if url not in urls:
            urls.append(url)

    items = []
    for url in urls[:50]:
        item_id = product_id_from_url(url)
        try:
            page_resp = requests.get(url, timeout=30)
            print(f"[SHOP SCRAPE] item_id={item_id} response: HTTP {page_resp.status_code}")
            if page_resp.status_code != 200:
                continue
            page = page_resp.text
            title = clean_base_title(html_meta_content(page, "og:title"))
            image_url = html_meta_content(page, "og:image")
            if not title:
                m = re.search(r"<title>(.*?)</title>", page, flags=re.I | re.S)
                title = clean_base_title(m.group(1) if m else "")
            if not item_id or not image_url:
                print(f"[SHOP SCRAPE][SKIP] item_id={item_id!r} missing image")
                continue
            items.append({
                "item_id": item_id,
                "title": title or f"KILL STREET item {item_id}",
                "detail": "",
                "item_url": url,
                "image_url": image_url,
                "price": 0,
                "stock": 1,
                "visible": True,
                "status": "active",
            })
        except Exception as e:
            print(f"[SHOP SCRAPE][WARN] item_url={url} failed: {e}")

    if not items:
        raise BaseApiError("BASE shop scrape found no usable items")
    print(f"[SHOP SCRAPE] Loaded {len(items)} items from BASE shop")
    return items


def fetch_items_from_feed_fallback():
    print("[WARN] BASE API failed; using feed fallback. Feed data may be stale.")

    local_feed = os.path.join("docs", "feed.xml")
    if os.path.exists(local_feed):
        try:
            with open(local_feed, "r", encoding="utf-8") as f:
                return parse_feed_items(f.read(), local_feed)
        except OSError as e:
            print(f"[FEED FALLBACK][WARN] Could not read {local_feed}: {e}")

    try:
        resp = requests.get(FEED_FALLBACK_URL, timeout=30)
        print(f"[FEED FALLBACK] Public feed response: HTTP {resp.status_code}")
        if resp.status_code == 200:
            return parse_feed_items(resp.text, FEED_FALLBACK_URL)
        print(f"[FEED FALLBACK][ERROR] Public feed failed: HTTP {resp.status_code} -> {short_response_text(resp)}")
    except Exception as e:
        print(f"[FEED FALLBACK][ERROR] Public feed request failed: {e}")
        traceback.print_exc()

    print("[FEED FALLBACK] Public feed unavailable; using BASE shop scrape fallback")
    return fetch_items_from_base_shop_scrape()


# ── feed.xml generation ───────────────────────────────────────────────────────
def build_feed(items):
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:g", "http://base.google.com/ns/1.0")
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = "KILLSTREET"
    ET.SubElement(ch, "link").text = "https://killstreet.thebase.in"
    ET.SubElement(ch, "description").text = "KILLSTREET product feed"
    count = 0
    for item in items:
        if not is_public(item):
            continue
        key = item_key(item)
        if not key:
            print(f"[FEED][SKIP] Public item has no stable key: {item_label(item)}")
            continue
        count += 1
        e = ET.SubElement(ch, "item")
        ET.SubElement(e, "g:id").text = key
        ET.SubElement(e, "g:title").text = item.get("title", "")
        ET.SubElement(e, "g:description").text = item.get("detail", "")[:5000]
        ET.SubElement(e, "g:link").text = item.get("item_url", "")
        img = _get_image_url(item)
        if img:
            ET.SubElement(e, "g:image_link").text = img
        ET.SubElement(e, "g:price").text = str(item.get("price", 0)) + " JPY"
        stock = item.get("stock", 0)
        ET.SubElement(e, "g:availability").text = "in stock" if stock > 0 else "out of stock"
        ET.SubElement(e, "g:condition").text = "new"
    print(f"[INFO] feed.xml: {count} public items")
    return ET.tostring(rss, encoding="unicode", xml_declaration=False)


# ── Instagram posting ─────────────────────────────────────────────────────────
def ig_post(item):
    print(f"\n[IG] ===== Starting post for item id={item.get('item_id')} =====")

    img_url = _get_image_url(item)
    if not img_url:
        print(f"[IG SKIP] id={item.get('item_id')} - no image URL found")
        return False

    title    = item.get("title", "")
    price    = item.get("price", 0)
    item_url = item.get("item_url", "")
    caption  = f"{title}\n\n\u00a5{price:,}\n\n{item_url}\n\n#killstreet #streetwear"

    print(f"[IG] title={title[:40]!r}")
    print(f"[IG] image_url={img_url}")
    print(f"[IG] caption preview: {caption[:80]!r}")
    print(f"[IG] DRY_RUN={DRY_RUN} | IG_USER_ID={IG_USER_ID[:6]}... | IG_TOKEN set={bool(IG_TOKEN)}")

    if DRY_RUN:
        print(f"[DRY RUN] Skipping actual post (dry run mode)")
        return True

    # Step 1: Create media container
    print("[IG] Step 1: Creating media container...")
    try:
        create_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
        resp1 = requests.post(create_url, data={
            "image_url": img_url,
            "caption": caption,
            "access_token": IG_TOKEN,
        }, timeout=60)
        print(f"[IG] Step 1 response: HTTP {resp1.status_code}")
        print(f"[IG] Step 1 body: {resp1.text[:1000]}")
    except Exception as e:
        print(f"[IG ERROR] Exception in Step 1: {e}")
        traceback.print_exc()
        return False

    if resp1.status_code != 200:
        print(f"[IG ERROR] Media container creation failed: HTTP {resp1.status_code} -> {resp1.text[:500]}")
        return False

    creation_id = resp1.json().get("id")
    if not creation_id:
        print(f"[IG ERROR] creation_id missing from response: {resp1.text[:300]}")
        return False
    print(f"[IG] creation_id = {creation_id}")

    # Step 2: Publish
    print("[IG] Waiting 5s before publish...")
    time.sleep(5)
    print("[IG] Step 2: Publishing media...")
    try:
        publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
        resp2 = requests.post(publish_url, data={
            "creation_id": creation_id,
            "access_token": IG_TOKEN,
        }, timeout=60)
        print(f"[IG] Step 2 response: HTTP {resp2.status_code}")
        print(f"[IG] Step 2 body: {resp2.text[:1000]}")
    except Exception as e:
        print(f"[IG ERROR] Exception in Step 2: {e}")
        traceback.print_exc()
        return False

    if resp2.status_code != 200:
        print(f"[IG ERROR] Publish failed: HTTP {resp2.status_code} -> {resp2.text[:500]}")
        return False

    post_id = resp2.json().get("id", "unknown")
    print(f"[IG] SUCCESS! post_id={post_id}")
    return True


# ── Deduplication helpers ─────────────────────────────────────────────────────
HISTORY_FILE = os.environ.get("HISTORY_FILE", "posted_history.json").strip() or "posted_history.json"

def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_posted = data.get("posted", [])
        # [ID AUDIT] Normalize all IDs to str regardless of JSON type (int or str)
        ids = set()
        for x in raw_posted:
            raw_type = type(x).__name__
            str_id = str(x)
            ids.add(str_id)
            if DEBUG:
                print(f"[HISTORY][AUDIT] id={str_id!r} raw_type={raw_type} -> stored as str")
        print(f"[HISTORY] Loaded {len(ids)} previously posted item IDs: {sorted(ids)}")
        return data, ids
    except FileNotFoundError:
        print("[HISTORY] posted_history.json not found - starting fresh")
        return {
            "posted": [],
            "_comment": "Automatically maintained by GitHub Actions. Do not edit manually.",
            "_schema": "item_id as string"
        }, set()
    except json.JSONDecodeError as e:
        print(f"[HISTORY][ERROR] JSON parse failed: {e} - starting fresh to prevent crash")
        return {
            "posted": [],
            "_comment": "Automatically maintained by GitHub Actions. Do not edit manually.",
            "_schema": "item_id as string"
        }, set()

def save_history(data, ids):
    data["posted"] = sorted(list(ids), key=lambda x: int(x) if x.isdigit() else x)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[HISTORY] Saved {len(ids)} posted item IDs to {HISTORY_FILE}")


def select_unposted_items(public_items, posted_ids):
    keyed_public = []
    skipped_no_key = 0

    for item in public_items:
        key = item_key(item)
        if not key:
            skipped_no_key += 1
            print(f"[HISTORY][SKIP] Public item has no item_id or item_url: {item_label(item)}")
            continue
        keyed_public.append((key, item))

    unposted_items = [item for key, item in keyed_public if key not in posted_ids]
    print(f"[HISTORY] fetched_public={len(public_items)} | keyed_public={len(keyed_public)} | "
          f"posted_history={len(posted_ids)} | already_posted={len(keyed_public) - len(unposted_items)} | "
          f"unposted={len(unposted_items)} | skipped_no_key={skipped_no_key}")

    if unposted_items:
        print(f"[IG] Selected candidate: {item_label(unposted_items[0])}")
    else:
        print("[IG] No unposted products remain. Exiting successfully.")

    return unposted_items


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    apply_cli_overrides()
    print(f"[INFO] === KILLSTREET Instagram Auto-Post ===")
    print(f"[INFO] SHOP_ID={SHOP_ID} | DRY_RUN={DRY_RUN} | IG_MAX_POSTS={IG_MAX_POSTS} | DEBUG={DEBUG}")
    print(f"[INFO] IG_TOKEN set={bool(IG_TOKEN)} | IG_USER_ID set={bool(IG_USER_ID)}")

    # Load posted history (deduplication)
    history_data, posted_ids = load_history()

    # Fetch BASE items
    test_items = load_test_items()
    if test_items is not None:
        all_items = test_items
    else:
        try:
            base_token = get_base_token()
            all_items  = fetch_items(base_token)
        except BaseApiError as e:
            print(f"[BASE ERROR] {e}")
            all_items = fetch_items_from_feed_fallback()

    # Generate and save feed.xml
    feed = build_feed(all_items)
    os.makedirs("docs", exist_ok=True)
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(feed)
    print("[INFO] feed.xml saved")

    public_items = [i for i in all_items if is_public(i)]

    # Filter out already-posted items
    unposted_items = select_unposted_items(public_items, posted_ids)

    if not unposted_items:
        return

    # Instagram posting
    if not DRY_RUN and (not IG_TOKEN or not IG_USER_ID):
        print("[IG ERROR] INSTAGRAM_TOKEN or IG_USER_ID not set - cannot post to Instagram")
        sys.exit(1)

    print(f"[IG] Posting up to {IG_MAX_POSTS} unposted items")

    posted = 0
    for item in unposted_items[:IG_MAX_POSTS]:
        post_key = item_key(item)

        # ── [SAFETY NET] Double-check: reload history from disk right before posting ──
        # Guards against race conditions (concurrent runs) and in-loop saves by
        # a previous iteration that may have updated the file since we started.
        _, live_posted_ids = load_history()
        if post_key in live_posted_ids:
            print(f"[HISTORY][DOUBLE-CHECK][SKIP] key={post_key} already in on-disk history "
                  f"(concurrent run or previous loop iteration) - skipping to prevent duplicate")
            # Sync in-memory state with what's on disk
            posted_ids.update(live_posted_ids)
            time.sleep(3)
            continue
        print(f"[HISTORY][DOUBLE-CHECK][OK] key={post_key} not in on-disk history - safe to post")

        try:
            ok = ig_post(item)
            if ok:
                posted += 1
                if DRY_RUN:
                    print(f"[HISTORY][DRY RUN] Not recording key={post_key}")
                elif post_key:
                    posted_ids.add(post_key)
                    save_history(history_data, posted_ids)
                    print(f"[HISTORY] Recorded key={post_key}")
        except Exception as e:
            print(f"[IG ERROR] Unhandled exception for item {item.get('item_id')}: {e}")
            traceback.print_exc()
        time.sleep(3)

    expected = min(len(unposted_items), IG_MAX_POSTS)
    print(f"\n[IG] Done: {posted}/{expected} posted")
    if not DRY_RUN and expected > 0 and posted == 0:
        print("[IG ERROR] No selected products were posted successfully")
        sys.exit(1)


if __name__ == "__main__":
    main()
