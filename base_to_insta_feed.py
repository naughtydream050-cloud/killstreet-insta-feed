import os
import sys
import json
import time
import requests
import xml.etree.ElementTree as ET

# 笏笏 迺ｰ蠅・､画焚 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
CLIENT_ID      = os.environ.get("BASE_CLIENT_ID", "").strip()
CLIENT_SECRET  = os.environ.get("BASE_CLIENT_SECRET", "").strip()
REFRESH_TOKEN  = os.environ.get("BASE_REFRESH_TOKEN", "").strip()
ACCESS_TOKEN   = os.environ.get("BASE_ACCESS_TOKEN", "").strip()
SHOP_ID        = os.environ.get("SHOP_ID", "").strip() or "killstreet2"
IG_TOKEN       = os.environ.get("INSTAGRAM_TOKEN", "").strip()
IG_USER_ID     = os.environ.get("IG_USER_ID", "").strip()
IG_MAX_POSTS   = int(os.environ.get("IG_MAX_POSTS", "1"))   # 1蝗槭・螳溯｡後〒謚慕ｨｿ縺吶ｋ譛螟ｧ莉ｶ謨ｰ
DEBUG          = True  # 蠑ｷ蛻ｶON・郁ｨｺ譁ｭ逕ｨ・・DRY_RUN        = os.environ.get("DRY_RUN", "false").lower() == "true"


# 笏笏 BASE 隱崎ｨｼ 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
def get_base_token():
    if REFRESH_TOKEN and CLIENT_ID and CLIENT_SECRET:
        print("[AUTH] 繝ｪ繝輔Ξ繝・す繝･繝医・繧ｯ繝ｳ縺ｧ繧｢繧ｯ繧ｻ繧ｹ繝医・繧ｯ繝ｳ繧貞叙蠕嶺ｸｭ...")
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
                print("[AUTH] 繝ｪ繝輔Ξ繝・す繝･繝医・繧ｯ繝ｳ繧偵Ο繝ｼ繝・・繧ｷ繝ｧ繝ｳ 竊・Secrets 譖ｴ譁ｰ隧ｦ陦・)
                ret = os.system(
                    f'gh secret set BASE_REFRESH_TOKEN '
                    f'-R naughtydream050-cloud/killstreet-insta-feed '
                    f'--body "{new_rt}" 2>&1'
                )
                if ret != 0:
                    print("[AUTH] Secrets 閾ｪ蜍墓峩譁ｰ縺ｯ讓ｩ髯蝉ｸ崎ｶｳ縺ｧ繧ｹ繧ｭ繝・・・域焔蜍墓峩譁ｰ繧呈耳螂ｨ・・)
            print("[AUTH] BASE 繧｢繧ｯ繧ｻ繧ｹ繝医・繧ｯ繝ｳ蜿門ｾ玲・蜉・)
            return data["access_token"]
        else:
            print(f"[AUTH] 繝ｪ繝輔Ξ繝・す繝･螟ｱ謨・ HTTP {resp.status_code} 竊・{resp.text[:300]}")
    if ACCESS_TOKEN:
        print("[AUTH] BASE_ACCESS_TOKEN 繧偵ヵ繧ｩ繝ｼ繝ｫ繝舌ャ繧ｯ縺ｨ縺励※菴ｿ逕ｨ")
        return ACCESS_TOKEN
    print("[AUTH ERROR] BASE_REFRESH_TOKEN 縺ｾ縺溘・ BASE_ACCESS_TOKEN 繧定ｨｭ螳壹＠縺ｦ縺上□縺輔＞縲・)
    sys.exit(1)


# 笏笏 BASE 蝠・刀蜿門ｾ・笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
def is_public(item):
    """visible: 1 縺ｾ縺溘・ selling 繧ｹ繝・・繧ｿ繧ｹ縺ｮ蝠・刀繧貞・髢九→縺ｿ縺ｪ縺・""
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
            print("[ERROR] 401 Unauthorized: 繝医・繧ｯ繝ｳ縺悟､ｱ蜉ｹ縺励※縺・∪縺吶・)
            sys.exit(1)
        if r.status_code == 403:
            print("[ERROR] 403 Forbidden: read_items 繧ｹ繧ｳ繝ｼ繝励′荳崎ｶｳ縺励※縺・∪縺吶・)
            sys.exit(1)
        r.raise_for_status()
        data = r.json()
        if "items" not in data:
            print(f"[ERROR] items 繧ｭ繝ｼ縺後≠繧翫∪縺帙ｓ: {json.dumps(data)[:500]}")
            sys.exit(1)
        batch = data["items"]
        if offset == 0 and batch:
            print(f"[INFO] 繝輔ぅ繝ｼ繝ｫ繝我ｸ隕ｧ: {list(batch[0].keys())}")
        if DEBUG and batch:
            print(f"[DEBUG] offset={offset} response: {json.dumps(data, ensure_ascii=False)[:2000]}")
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    print(f"[INFO] 蜈ｨ {len(items)} 莉ｶ蜿門ｾ・)
    for it in items:
        v = it.get("visible", it.get("is_visible", "N/A"))
        s = it.get("status", "N/A")
        print(f"  id={it.get('item_id')} status={s!r} visible={v!r} title={str(it.get('title',''))[:25]!r}")
    return items


# 笏笏 feed.xml 逕滓・ 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
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
    print(f"[INFO] feed.xml 蟇ｾ雎｡: {count} 莉ｶ")
    return ET.tostring(rss, encoding="unicode", xml_declaration=False)


# 笏笏 Instagram 謚慕ｨｿ 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
def ig_post(item):
    """Instagram Graph API 縺ｧ逕ｻ蜒上ｒ謚慕ｨｿ縺吶ｋ・・繧ｹ繝・ャ繝暦ｼ・""
    img_url = _get_image_url(item)
    if not img_url:
        print(f"[IG SKIP] id={item.get('item_id')} 窶・逕ｻ蜒酋RL縺ｪ縺・)
        return False

    title   = item.get("title", "")
    price   = item.get("price", 0)
    item_url = item.get("item_url", "")
    caption = f"{title}\n\nﾂ･{price:,}\n\n{item_url}\n\n#killstreet #streetwear"

    print(f"[IG] 謚慕ｨｿ髢句ｧ・ id={item.get('item_id')} title={title[:30]!r}")
    print(f"[IG] image_url={img_url}")

    if DRY_RUN:
        print(f"[DRY RUN] 謚慕ｨｿ繧偵せ繧ｭ繝・・・・aption={caption[:60]}...・・)
        return True

    # 繧ｹ繝・ャ繝・: 繝｡繝・ぅ繧｢繧ｳ繝ｳ繝・リ菴懈・
    create_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    resp1 = requests.post(create_url, data={
        "image_url": img_url,
        "caption": caption,
        "access_token": IG_TOKEN,
    })
    if resp1.status_code != 200:
        print(f"[IG ERROR] 繝｡繝・ぅ繧｢菴懈・螟ｱ謨・ HTTP {resp1.status_code} 竊・{resp1.text[:500]}")
        return False
    creation_id = resp1.json().get("id")
    if not creation_id:
        print(f"[IG ERROR] creation_id 縺悟叙蠕励〒縺阪∪縺帙ｓ: {resp1.text[:300]}")
        return False
    print(f"[IG] creation_id = {creation_id}")

    # 繧ｹ繝・ャ繝・: 蜈ｬ髢・    time.sleep(2)  # API 繝ｬ繝ｼ繝亥宛髯仙ｯｾ遲・    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    resp2 = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": IG_TOKEN,
    })
    if resp2.status_code != 200:
        print(f"[IG ERROR] 蜈ｬ髢句､ｱ謨・ HTTP {resp2.status_code} 竊・{resp2.text[:500]}")
        return False

    post_id = resp2.json().get("id", "unknown")
    print(f"[IG] 笨・謚慕ｨｿ謌仙粥! post_id={post_id}")
    return True


# 笏笏 繝｡繧､繝ｳ 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
def main():
    print(f"[INFO] SHOP_ID={SHOP_ID} | DRY_RUN={DRY_RUN} | IG_MAX_POSTS={IG_MAX_POSTS}")

    # BASE 蝠・刀蜿門ｾ・    base_token = get_base_token()
    all_items  = fetch_items(base_token)

    # feed.xml 逕滓・ & 菫晏ｭ・    feed = build_feed(all_items)
    os.makedirs("docs", exist_ok=True)
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(feed)
    print("[INFO] feed.xml 逕滓・螳御ｺ・)

    # Instagram 謚慕ｨｿ
    if not IG_TOKEN or not IG_USER_ID:
        print("[IG] INSTAGRAM_TOKEN 縺ｾ縺溘・ IG_USER_ID 縺梧悴險ｭ螳壹・縺溘ａ繧ｹ繧ｭ繝・・")
        return

    public_items = [i for i in all_items if is_public(i)]
    print(f"[IG] 蜈ｬ髢句膚蜩・{len(public_items)} 莉ｶ 竊・譛螟ｧ {IG_MAX_POSTS} 莉ｶ謚慕ｨｿ")

    posted = 0
    for item in public_items[:IG_MAX_POSTS]:
        ok = ig_post(item)
        if ok:
            posted += 1
        time.sleep(3)  # 騾｣邯壽兜遞ｿ繧､繝ｳ繧ｿ繝ｼ繝舌Ν

    print(f"[IG] 謚慕ｨｿ螳御ｺ・ {posted}/{min(len(public_items), IG_MAX_POSTS)} 莉ｶ")


if __name__ == "__main__":
    main()

