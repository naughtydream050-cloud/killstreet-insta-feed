import os
import sys
import json
import time
import requests
import xml.etree.ElementTree as ET

# ── 環境変数 ──────────────────────────────────────────────────────────────────
CLIENT_ID      = os.environ.get("BASE_CLIENT_ID", "").strip()
CLIENT_SECRET  = os.environ.get("BASE_CLIENT_SECRET", "").strip()
REFRESH_TOKEN  = os.environ.get("BASE_REFRESH_TOKEN", "").strip()
ACCESS_TOKEN   = os.environ.get("BASE_ACCESS_TOKEN", "").strip()
SHOP_ID        = os.environ.get("SHOP_ID", "").strip() or "killstreet2"
IG_TOKEN       = os.environ.get("INSTAGRAM_TOKEN", "").strip()
IG_USER_ID     = os.environ.get("IG_USER_ID", "").strip()
IG_MAX_POSTS   = int(os.environ.get("IG_MAX_POSTS", "1"))   # 1回の実行で投稿する最大件数
DEBUG          = True  # 強制ON（診断用）
DRY_RUN        = os.environ.get("DRY_RUN", "false").lower() == "true"


# ── BASE 認証 ─────────────────────────────────────────────────────────────────
def get_base_token():
    if REFRESH_TOKEN and CLIENT_ID and CLIENT_SECRET:
        print("[AUTH] リフレッシュトークンでアクセストークンを取得中...")
        resp = requests.post("https://api.thebase.in/1/oauth/token", data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
        })
        if resp.status_code == 200:
            data = resp.json()
            new_rt = data.get("refresh_token", "")
            if new_rt and new_rt != REFRESH_TOKEN:
                print("[AUTH] リフレッシュトークンをローテーション → Secrets 更新試行")
                ret = os.system(
                    f'gh secret set BASE_REFRESH_TOKEN '
                    f'-R naughtydream050-cloud/killstreet-insta-feed '
                    f'--body "{new_rt}" 2>&1'
                )
                if ret != 0:
                    print("[AUTH] Secrets 自動更新は権限不足でスキップ（手動更新を推奨）")
            print("[AUTH] BASE アクセストークン取得成功")
            return data["access_token"]
        else:
            print(f"[AUTH] リフレッシュ失敗: HTTP {resp.status_code} → {resp.text[:300]}")
    if ACCESS_TOKEN:
        print("[AUTH] BASE_ACCESS_TOKEN をフォールバックとして使用")
        return ACCESS_TOKEN
    print("[AUTH ERROR] BASE_REFRESH_TOKEN または BASE_ACCESS_TOKEN を設定してください。")
    sys.exit(1)


# ── BASE 商品取得 ──────────────────────────────────────────────────────────────
def is_public(item):
    """visible: 1 または selling ステータスの商品を公開とみなす"""
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
            print(f"[IMG DEBUG] keys={list(img.keys())} sample={json.dumps(img, ensure_ascii=False)[:200]}")
        # BASE API returns "original" (not "origin") as the full-size image key
        return (img.get("original") or img.get("origin") or
                img.get("url") or img.get("large") or "")
    return (item.get("list_image_url") or item.get("detail_image_url") or "")


def fetch_items(base_token):
    headers = {"Authorization": f"Bearer {base_token}"}
    items, limit, offset = [], 100, 0
    while True:
        params = {"limit": limit, "offset": offset, "order": "new"}
        r = requests.get("https://api.thebase.in/1/items", headers=headers, params=params)
        if r.status_code == 401:
            print("[ERROR] 401 Unauthorized: トークンが失効しています。")
            sys.exit(1)
        if r.status_code == 403:
            print("[ERROR] 403 Forbidden: read_items スコープが不足しています。")
            sys.exit(1)
        r.raise_for_status()
        data = r.json()
        if "items" not in data:
            print(f"[ERROR] items キーがありません: {json.dumps(data)[:500]}")
            sys.exit(1)
        batch = data["items"]
        if offset == 0 and batch:
            print(f"[INFO] フィールド一覧: {list(batch[0].keys())}")
        if DEBUG and batch:
            print(f"[DEBUG] offset={offset} response: {json.dumps(data, ensure_ascii=False)[:2000]}")
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    print(f"[INFO] 全 {len(items)} 件取得")
    for it in items:
        v = it.get("visible", it.get("is_visible", "N/A"))
        s = it.get("status", "N/A")
        print(f"  id={it.get('item_id')} status={s!r} visible={v!r} title={str(it.get('title',''))[:25]!r}")
    return items


# ── feed.xml 生成 ─────────────────────────────────────────────────────────────
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
    print(f"[INFO] feed.xml 対象: {count} 件")
    return ET.tostring(rss, encoding="unicode", xml_declaration=False)


# ── Instagram 投稿 ────────────────────────────────────────────────────────────
def ig_post(item):
    """Instagram Graph API で画像を投稿する（2ステップ）"""
    img_url = _get_image_url(item)
    if not img_url:
        print(f"[IG SKIP] id={item.get('item_id')} — 画像URLなし")
        return False

    title   = item.get("title", "")
    price   = item.get("price", 0)
    item_url = item.get("item_url", "")
    caption = f"{title}\n\n¥{price:,}\n\n{item_url}\n\n#killstreet #streetwear"

    print(f"[IG] 投稿開始: id={item.get('item_id')} title={title[:30]!r}")
    print(f"[IG] image_url={img_url}")

    if DRY_RUN:
        print(f"[DRY RUN] 投稿をスキップ（caption={caption[:60]}...）")
        return True

    # ステップ1: メディアコンテナ作成
    create_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    resp1 = requests.post(create_url, data={
        "image_url": img_url,
        "caption": caption,
        "access_token": IG_TOKEN,
    })
    if resp1.status_code != 200:
        print(f"[IG ERROR] メディア作成失敗: HTTP {resp1.status_code} → {resp1.text[:500]}")
        return False
    creation_id = resp1.json().get("id")
    if not creation_id:
        print(f"[IG ERROR] creation_id が取得できません: {resp1.text[:300]}")
        return False
    print(f"[IG] creation_id = {creation_id}")

    # ステップ2: 公開
    time.sleep(2)  # API レート制限対策
    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    resp2 = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": IG_TOKEN,
    })
    if resp2.status_code != 200:
        print(f"[IG ERROR] 公開失敗: HTTP {resp2.status_code} → {resp2.text[:500]}")
        return False

    post_id = resp2.json().get("id", "unknown")
    print(f"[IG] ✅ 投稿成功! post_id={post_id}")
    return True


# ── メイン ────────────────────────────────────────────────────────────────────
def main():
    print(f"[INFO] SHOP_ID={SHOP_ID} | DRY_RUN={DRY_RUN} | IG_MAX_POSTS={IG_MAX_POSTS}")

    # BASE 商品取得
    base_token = get_base_token()
    all_items  = fetch_items(base_token)

    # feed.xml 生成 & 保存
    feed = build_feed(all_items)
    os.makedirs("docs", exist_ok=True)
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(feed)
    print("[INFO] feed.xml 生成完了")

    # Instagram 投稿
    if not IG_TOKEN or not IG_USER_ID:
        print("[IG] INSTAGRAM_TOKEN または IG_USER_ID が未設定のためスキップ")
        return

    public_items = [i for i in all_items if is_public(i)]
    print(f"[IG] 公開商品 {len(public_items)} 件 → 最大 {IG_MAX_POSTS} 件投稿")

    posted = 0
    for item in public_items[:IG_MAX_POSTS]:
        ok = ig_post(item)
        if ok:
            posted += 1
        time.sleep(3)  # 連続投稿インターバル

    print(f"[IG] 投稿完了: {posted}/{min(len(public_items), IG_MAX_POSTS)} 件")


if __name__ == "__main__":
    main()
                   