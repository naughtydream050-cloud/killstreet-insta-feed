import os, sys, json, requests, subprocess
import xml.etree.ElementTree as ET

CLIENT_ID     = os.environ.get("BASE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("BASE_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.environ.get("BASE_REFRESH_TOKEN", "").strip()
ACCESS_TOKEN  = os.environ.get("BASE_ACCESS_TOKEN", "").strip()
SHOP_ID       = os.environ.get("SHOP_ID", "").strip() or "killstreet2"
DEBUG         = True  # 今回は強制ON

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
            new_rt = data.get("refresh_token", "")
            if new_rt and new_rt != REFRESH_TOKEN:
                print("[AUTH] リフレッシュトークンをローテーション → Secrets更新")
                subprocess.run(["gh", "secret", "set", "BASE_REFRESH_TOKEN",
                                "-R", "naughtydream050-cloud/killstreet-insta-feed",
                                "--body", new_rt], capture_output=True)
            print("[AUTH] アクセストークン取得成功")
            return data["access_token"]
        else:
            print(f"[AUTH] リフレッシュ失敗: HTTP {resp.status_code} → {resp.text[:300]}")
    if ACCESS_TOKEN:
        print("[AUTH] ACCESS_TOKEN フォールバック使用")
        return ACCESS_TOKEN
    print("[AUTH ERROR] 有効なトークンなし")
    sys.exit(1)

def get_items(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    items, limit, offset = [], 100, 0
    while True:
        r = requests.get("https://api.thebase.in/1/items", headers=headers,
                         params={"limit": limit, "offset": offset, "order": "new"})
        if r.status_code == 401:
            print("[ERROR] 401: トークン失効")
            sys.exit(1)
        if r.status_code == 403:
            print("[ERROR] 403: read_items スコープ不足")
            sys.exit(1)
        r.raise_for_status()
        data = r.json()
        if "items" not in data:
            print(f"[ERROR] items キーなし: {json.dumps(data)[:500]}")
            sys.exit(1)
        batch = data["items"]
        if offset == 0:
            print(f"[INFO] フィールド一覧: {list(batch[0].keys()) if batch else []}")
            print("[INFO] 全商品のステータス確認:")
            for i, item in enumerate(batch):
                st = item.get("status", "N/A")
                vis = item.get("visible", "N/A")
                tid = item.get("item_id", "?")
                title = item.get("title", "")[:30]
                print(f"  [{i}] id={tid} status={st!r} visible={vis!r} title={title!r}")
        if DEBUG:
            print(f"[DEBUG] raw response (offset={offset}):")
            print(json.dumps(data, ensure_ascii=False)[:3000])
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return items

def _get_img(item):
    imgs = item.get("images", [])
    if imgs:
        return imgs[0].get("origin", imgs[0].get("url", ""))
    return item.get("list_image_url", item.get("detail_image_url", ""))

def is_public(item):
    # BASEのステータスは "selling" か visible==1 など複数パターンあり
    st = item.get("status", "")
    vis = item.get("visible", None)
    # selling か visible が truthy なら公開
    if st == "selling":
        return True
    if vis is not None and vis not in (0, False, "0", "hidden", "draft"):
        return True
    # statusが "list" や "on_sale" 等の場合も対応
    if st in ("list", "on_sale", "published", "open", "visible"):
        return True
    return False

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
            print(f"[SKIP] id={item.get('item_id')} status={item.get('status')!r} visible={item.get('visible')!r}")
            continue
        count += 1
        e = ET.SubElement(ch, "item")
        ET.SubElement(e, "g:id").text = str(item["item_id"])
        ET.SubElement(e, "g:title").text = item.get("title", "")
        ET.SubElement(e, "g:description").text = item.get("detail", "")[:5000]
        ET.SubElement(e, "g:link").text = item.get("item_url", "")
        img = _get_img(item)
        if img:
            ET.SubElement(e, "g:image_link").text = img
        ET.SubElement(e, "g:price").text = str(item.get("price", 0)) + " JPY"
        ET.SubElement(e, "g:availability").text = "in stock" if item.get("stock", 0) > 0 else "out of stock"
        ET.SubElement(e, "g:condition").text = "new"
    print(f"[INFO] feed対象: {count}件 / 全{len(items)}件")
    return ET.tostring(rss, encoding="unicode", xml_declaration=False)

def main():
    print(f"[INFO] SHOP_ID={SHOP_ID} DEBUG={DEBUG}")
    token = get_access_token()
    items = get_items(token)
    print(f"[INFO] 合計取得: {len(items)}件")
    feed = build_feed(items)
    os.makedirs("docs", exist_ok=True)
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(feed)
    print("[INFO] feed.xml 生成完了")

if __name__ == "__main__":
    main()
