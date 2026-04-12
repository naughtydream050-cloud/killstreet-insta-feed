import os
import sys
import json
import requests
import xml.etree.ElementTree as ET

CLIENT_ID     = os.environ.get("BASE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("BASE_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.environ.get("BASE_REFRESH_TOKEN", "").strip()
ACCESS_TOKEN  = os.environ.get("BASE_ACCESS_TOKEN", "").strip()
SHOP_ID       = os.environ.get("SHOP_ID", "").strip() or "killstreet2"
DEBUG         = True  # 強制ON（診断用）


def get_access_token():
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
            new_refresh = data.get("refresh_token", "")
            if new_refresh and new_refresh != REFRESH_TOKEN:
                print("[AUTH] 新しいリフレッシュトークンを取得 → GitHub Secrets を更新")
                os.system(
                    f'gh secret set BASE_REFRESH_TOKEN '
                    f'-R naughtydream050-cloud/killstreet-insta-feed '
                    f'--body "{new_refresh}"'
                )
            print("[AUTH] アクセストークン取得成功")
            return data["access_token"]
        else:
            print(f"[AUTH] リフレッシュ失敗: HTTP {resp.status_code} → {resp.text[:300]}")
    if ACCESS_TOKEN:
        print("[AUTH] BASE_ACCESS_TOKEN をフォールバックとして使用")
        return ACCESS_TOKEN
    print("[AUTH ERROR] 有効なトークンがありません。BASE_REFRESH_TOKEN または BASE_ACCESS_TOKEN を設定してください。")
    sys.exit(1)


def get_items(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    items = []
    limit, offset = 100, 0
    while True:
        params = {"limit": limit, "offset": offset, "order": "new"}
        r = requests.get("https://api.thebase.in/1/items", headers=headers, params=params)
        if r.status_code == 401:
            print("[ERROR] 401 Unauthorized: トークンが失効しています。再認証が必要です。")
            sys.exit(1)
        if r.status_code == 403:
            print("[ERROR] 403 Forbidden: read_items スコープが不足しています。BASEで再認証してください。")
            sys.exit(1)
        r.raise_for_status()
        data = r.json()
        if DEBUG:
            print(f"[DEBUG] API response (offset={offset}): {json.dumps(data, ensure_ascii=False)[:2000]}")
        if "items" not in data:
            print(f"[ERROR] レスポンスに items キーがありません: {json.dumps(data)[:500]}")
            sys.exit(1)
        batch = data.get("items", [])
        if offset == 0:
            keys = list(batch[0].keys()) if batch else []
            print(f"[INFO] 最初のバッチ: {len(batch)} 件取得。利用可能なフィールド: {keys}")
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return items


def is_public(item):
    """公開中とみなせる商品かどうか判定（status が selling / published / visible 等）"""
    status = str(item.get("status", "")).lower()
    visible = item.get("visible", item.get("is_visible", item.get("published", None)))
    return status in ("selling", "published", "visible", "active", "1", "true") or visible in (True, 1, "1", "true")


def _get_image_url(item):
    imgs = item.get("images", [])
    if imgs:
        return imgs[0].get("origin", imgs[0].get("url", ""))
    return item.get("list_image_url", item.get("detail_image_url", ""))


def build_feed(items):
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:g", "http://base.google.com/ns/1.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "KILLSTREET"
    ET.SubElement(channel, "link").text = "https://killstreet.thebase.in"
    ET.SubElement(channel, "description").text = "KILLSTREET product feed"
    for item in items:
        status = item.get("status", "N/A")
        visible = item.get("visible", item.get("is_visible", item.get("published", "N/A")))
        item_id = item.get("item_id", "?")
        title = item.get("title", "")[:30]
        if not is_public(item):
            print(f"[SKIP] id={item_id} title={title!r} status={status} visible={visible}")
            continue
        print(f"[INFO] feed対象: id={item_id} title={title!r} status={status} visible={visible}")
        entry = ET.SubElement(channel, "item")
        ET.SubElement(entry, "g:id").text = str(item["item_id"])
        ET.SubElement(entry, "g:title").text = item.get("title", "")
        ET.SubElement(entry, "g:description").text = item.get("detail", "")[:5000]
        ET.SubElement(entry, "g:link").text = item.get("item_url", "")
        img_url = _get_image_url(item)
        if img_url:
            ET.SubElement(entry, "g:image_link").text = img_url
        ET.SubElement(entry, "g:price").text = str(item.get("price", 0)) + " JPY"
        stock = item.get("stock", 0)
        ET.SubElement(entry, "g:availability").text = "in stock" if stock > 0 else "out of stock"
        ET.SubElement(entry, "g:condition").text = "new"
    return ET.tostring(rss, encoding="unicode", xml_declaration=False)


def main():
    print(f"[INFO] SHOP_ID = {SHOP_ID}, DEBUG = {DEBUG}")
    token = get_access_token()
    items = get_items(token)
    print(f"[INFO] 全 {len(items)} 件取得")
    for item in items:
        status = item.get("status", "N/A")
        visible = item.get("visible", item.get("is_visible", item.get("published", "N/A")))
        item_id = item.get("item_id", "?")
        title = item.get("title", "")[:30]
        print(f"[DEBUG] 商品ステータス: id={item_id} title={title!r} status={status} visible={visible}")
    feed_items = [i for i in items if is_public(i)]
    feed = build_feed(items)
    os.makedirs("docs", exist_ok=True)
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(feed)
    print(f"[INFO] feed対象: {len(feed_items)}件 / 全{len(items)}件")


if __name__ == "__main__":
    main()
