import requests
from bs4 import BeautifulSoup

url = "https://marsol.az/partnyorlarimiz/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Connection": "keep-alive"
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")

session = requests.Session()
session.headers.update(headers)

import re

last_page = 1
for a in soup.select('a[href*="/partnyorlarimiz/page/"]'):
    m = re.search(r"/page/(\d+)/?$", a.get("href",""))
    if m:
        last_page = max(last_page, int(m.group(1)))
print("last_page:", last_page)


from urllib.parse import urljoin
import re, time

all_items = []
seen_urls = set()

for page in range(1, last_page + 1):
    page_url = url if page == 1 else urljoin(url, f"page/{page}/")
    r = session.get(page_url, headers=headers, timeout=30); r.raise_for_status()
    sp = BeautifulSoup(r.text, "html.parser")

    for card in sp.select("div.gdlr-core-blog-grid-content-wrap"):
        a = card.select_one("h3 a[href]")
        if not a:
            continue
        t = a.get_text(strip=True)
        u = a["href"]
        cat = " | ".join(x.get_text(strip=True)
                         for x in card.select(".gdlr-core-blog-info-category a")) or ""
        if u not in seen_urls:
            seen_urls.add(u)
            all_items.append((t, u, cat))

    print(f"page {page}: total items so far {len(all_items)}")
    time.sleep(0.4)

print("TOTAL listing URLs:", len(all_items))


