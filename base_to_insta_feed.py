import os
import sys
import json
import time
import traceback
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
IG_MAX_POSTS  = int(os.environ.get("IG_MAX_POSTS", "1"))
DEBUG         = True   # forced ON for diagnostics
DRY_RUN       = os.environ.get("DRY_RUN", "false").lower() == "true"


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
            print(f"[AUTH] Token response: HTTP {resp.status_code} | {resp.text[:300]}")
            if resp.status_code == 200:
                data = resp.json()
                new_rt = data.get("refresh_token", "")
                if new_rt and new_rt != REFRESH_TOKEN:
                    print("[AUTH] refresh_token rotated -> attempting Secrets update")
                    ret = os.system(
                        f'gh secret set BASE_REFRESH_TOKEN '
                        f'-R naughtydream050-cloud/killstreet-insta-feed '
                        f'--body "{new_rt}" 2>&1'
                    )
                    if ret != 0:
                        print("[AUTH] WARNING: Secrets auto-update failed (permission denied) - update manually")
                print("[AUTH] BASE access token obtained successfully")
                return data["access_token"]
            else:
                print(f"[AUTH] Refresh failed: HTTP {resp.status_code} -> {resp.text[:300]}")
        except Exception as e:
            print(f"[AUTH ERROR] Exception during token refresh: {e}")
            traceback.print_exc()

    if ACCESS_TOKEN:
        print("[AUTH] Using BASE_ACCESS_TOKEN as fallback")
        return ACCESS_TOKEN

    print("[AUTH ERROR] Neither BASE_REFRESH_TOKEN nor BASE_ACCESS_TOKEN is set.")
    sys.exit(1)


# ── BASE item helpers ─────────────────────────────────────────────────────────
def is_public(item):
    visible = item.get("visible", item.get("is_visible", None))
    if visible in (True, 1, "1", "true"):
        return True
    status = str(item.get("status", "")).lower()
    return status in ("selling", "published", "visible", "active")


def _get_image_url(item):
    imgs = item.get("images", [])
    if imgs:
        img = imgs[0]
        if DEBUG:
            print(f"[IMG DEBUG] id={item.get('item_id')} image keys={list(img.keys())} | raw={json.dumps(img, ensure_ascii=False)[:300]}")
        # BASE API uses "original" as the full-size image key
        url = (img.get("original") or img.get("origin") or
               img.get("url") or img.get("large") or "")
        print(f"[IMG] id={item.get('item_id')} -> image_url={url[:80] if url else '(empty)'}")
        return url
    fallback = item.get("list_image_url") or item.get("detail_image_url") or ""
    print(f"[IMG] id={item.get('item_id')} -> no images array, fallback={fallback[:80] if fallback else '(empty)'}")
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
            print(f"[ERROR] Request exception: {e}")
            traceback.print_exc()
            sys.exit(1)

        print(f"[INFO] BASE API response: HTTP {r.status_code} | offset={offset}")
        if r.status_code == 401:
            print("[ERROR] 401 Unauthorized: token has expired.")
            sys.exit(1)
        if r.status_code == 403:
            print("[ERROR] 403 Forbidden: missing read_items scope.")
            sys.exit(1)
        r.raise_for_status()
        data = r.json()
        if "items" not in data:
            print(f"[ERROR] 'items' key not found in response: {json.dumps(data)[:500]}")
            sys.exit(1)
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
        count += 1
        e = ET.SubElement(ch, "item")
        ET.SubElement(e, "g:id").text = str(item["item_id"])
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


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[INFO] === KILLSTREET Instagram Auto-Post ===")
    print(f"[INFO] SHOP_ID={SHOP_ID} | DRY_RUN={DRY_RUN} | IG_MAX_POSTS={IG_MAX_POSTS} | DEBUG={DEBUG}")
    print(f"[INFO] IG_TOKEN set={bool(IG_TOKEN)} | IG_USER_ID set={bool(IG_USER_ID)}")

    # Fetch BASE items
    base_token = get_base_token()
    all_items  = fetch_items(base_token)

    # Generate and save feed.xml
    feed = build_feed(all_items)
    os.makedirs("docs", exist_ok=True)
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(feed)
    print("[INFO] feed.xml saved")

    # Instagram posting
    if not IG_TOKEN or not IG_USER_ID:
        print("[IG] INSTAGRAM_TOKEN or IG_USER_ID not set - skipping Instagram post")
        return

    public_items = [i for i in all_items if is_public(i)]
    print(f"[IG] {len(public_items)} public items found -> posting up to {IG_MAX_POSTS}")

    if not public_items:
        print("[IG] No public items available to post")
        return

    posted = 0
    for item in public_items[:IG_MAX_POSTS]:
        try:
            ok = ig_post(item)
            if ok:
                posted += 1
        except Exception as e:
            print(f"[IG ERROR] Unhandled exception for item {item.get('item_id')}: {e}")
            traceback.print_exc()
        time.sleep(3)

    print(f"\n[IG] Done: {posted}/{min(len(public_items), IG_MAX_POSTS)} posted")


if __name__ == "__main__":
    main()
