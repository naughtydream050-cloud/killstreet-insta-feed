import os
import requests
import xml.etree.ElementTree as ET

CLIENT_ID = os.environ['BASE_CLIENT_ID']
CLIENT_SECRET = os.environ['BASE_CLIENT_SECRET']
REFRESH_TOKEN = os.environ.get('BASE_REFRESH_TOKEN', '')

def get_access_token():
    if not REFRESH_TOKEN:
        raise ValueError('BASE_REFRESH_TOKEN not set')
    resp = requests.post('https://api.thebase.in/1/oauth/token', data={
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN,
        'redirect_uri': 'http://localhost:8080/callback'
    })
    resp.raise_for_status()
    data = resp.json()
    new_refresh = data.get('refresh_token', REFRESH_TOKEN)
    os.system(f'echo "{new_refresh}" | gh secret set BASE_REFRESH_TOKEN -R naughtydream050-cloud/killstreet-insta-feed')
    return data['access_token']

def get_items(access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    items = []
    limit, offset = 100, 0
    while True:
        r = requests.get('https://api.thebase.in/1/items', headers=headers, params={'limit': limit, 'offset': offset})
        r.raise_for_status()
        data = r.json()
        batch = data.get('items', [])
        items.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return items

def build_feed(items):
    rss = ET.Element('rss', version='2.0')
    rss.set('xmlns:g', 'http://base.google.com/ns/1.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'KILLSTREET'
    ET.SubElement(channel, 'link').text = 'https://killstreet.thebase.in'
    ET.SubElement(channel, 'description').text = 'KILLSTREET product feed'
    for item in items:
        if item.get('status') != 'selling':
            continue
        entry = ET.SubElement(channel, 'item')
        ET.SubElement(entry, 'g:id').text = str(item['item_id'])
        ET.SubElement(entry, 'g:title').text = item.get('title', '')
        ET.SubElement(entry, 'g:description').text = item.get('detail', '')[:5000]
        ET.SubElement(entry, 'g:link').text = item.get('item_url', '')
        imgs = item.get('images', [])
        if imgs:
            ET.SubElement(entry, 'g:image_link').text = imgs[0].get('origin', '')
        ET.SubElement(entry, 'g:price').text = str(item.get('price', 0)) + ' JPY'
        ET.SubElement(entry, 'g:availability').text = 'in stock' if item.get('stock', 0) > 0 else 'out of stock'
        ET.SubElement(entry, 'g:condition').text = 'new'
    return ET.tostring(rss, encoding='unicode', xml_declaration=False)

def main():
    token = get_access_token()
    items = get_items(token)
    feed = build_feed(items)
    os.makedirs('docs', exist_ok=True)
    with open('docs/feed.xml', 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(feed)
    print(f'Generated feed.xml with {len(items)} items')

if __name__ == '__main__':
    main()
