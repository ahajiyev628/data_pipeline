import time
import re
import urllib3
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging, sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("az-yp")

BASE = "https://www.azerbaijanyp.com"
BROWSE_URL = f"{BASE}/browse-business-directory"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36"
}
PAGE_DELAY_SEC = 1.0
COMPANY_DELAY_SEC = 0.6

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def clean_text(a):
    return a.get_text(" ", strip=True) if a else None

def get_soup(session, url):
    r = session.get(url, headers=HEADERS, timeout=30, verify=False)
    r.raise_for_status()
    r.encoding = "utf-8"
    return BeautifulSoup(r.text, "html.parser")

def by_label_text(soup, label_text):
    lab = soup.find("div", class_="label",
                    string=lambda s: s and s.strip().lower() == label_text.lower())
    if not lab:
        return None

    sib = lab.find_next_sibling("div", class_="text")
    if sib:
        tel = sib.select_one("a[href^='tel:']")
        if tel:
            return clean_text(tel)
        a = sib.select_one("a[href]")
        if a:
            return clean_text(a)
        return clean_text(sib)

    cont = lab.find_parent("div", class_="info")
    if cont:
        parts = list(cont.stripped_strings)
        if parts and parts[0].strip().lower() == label_text.lower():
            parts = parts[1:]
        return " ".join(parts) if parts else None

    return None

def normalize_az_phone(raw: str) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)

    if len(digits) <= 7:
        return raw.strip()

    if digits.startswith("00994"):
        return "+994" + digits[5:]
    if digits.startswith("994"):
        return "+" + digits
    if digits.startswith("0"):
        digits = digits[1:]

    return "+994" + digits


def phones_by_label(soup, label_text):
    lab = soup.find("div", class_="label", string=lambda s: s and s.strip().lower() == label_text.lower())
    if not lab:
        return None

    nums = []

    tx = lab.find_next_sibling("div", class_="text")
    if tx:
        for a in tx.select("a[href^='tel:']"):
            v = a.get_text(" ", strip=True)
            if v:
                nums.append(v)
        if not nums:
            nums = [s for s in (s.strip() for s in tx.stripped_strings) if s]

    if not nums:
        cont = lab.find_parent("div", class_="info")
        if cont:
            parts = list(cont.stripped_strings)
            if parts and parts[0].strip().lower() == label_text.lower():
                parts = parts[1:]
            nums = parts

    seen, out = set(), []
    for n in nums:
        std = normalize_az_phone(n)
        if std and std not in seen:
            seen.add(std)
            out.append(std)

    return ", ".join(out) if out else None

def split_contact_three(numbers_str: str):
    if not numbers_str:
        return None, None, None
    parts = [p.strip() for p in numbers_str.split(",") if p.strip()]
    first  = parts[0] if len(parts) > 0 else None
    second = parts[1] if len(parts) > 1 else None
    rest   = ", ".join(parts[2:]) if len(parts) > 2 else None
    return first, second, rest


def extract_all_categories(session):
    soup = get_soup(session, BROWSE_URL)
    out = []
    for ul in soup.select("ul.icats"):
        group_name = ul.get_text()
        for li in ul.find_all("li", recursive=False):
            if li.find("div", class_="icats_empty"):
                continue
            a = li.find("a", href=True)
            out.append({"group": group_name, "url": urljoin(BASE, a["href"])})
    return out

def extract_all_categories(session):
    soup = get_soup(session, BROWSE_URL)
    out = []
    for ul in soup.select("ul.icats"):
        for li in ul.find_all("li", recursive=False):
            if li.find("div", class_="icats_empty"):
                continue
            a = li.find("a", href=True)
            if not a:
                continue
            span = a.find("span")
            if span:
                span.decompose()
            cat_name = clean_text(a)
            out.append({
                "group": cat_name,
                "url": urljoin(BASE, a["href"])
            })
    return out


def find_next_page_url(soup):
    nxt = soup.select_one("a.pages_arrow[rel='next']")
    return urljoin(BASE, nxt["href"]) if nxt and nxt.has_attr("href") else None

def collect_company_links_for_category(session, category_url):
    urls, seen = [], set()
    url = category_url
    page_no = 0
    while url:
        page_no += 1
        log.info(f"[CAT] Page {page_no} => {url}")
        soup = get_soup(session, url)

        before = len(urls)
        for a in soup.select("div.company[data-cmpid] h3 a[href]"):
            raw = (a.get("href") or "").strip()
            if not raw:
                continue
            href = urljoin(BASE, raw)
            if href not in seen:
                seen.add(href)
                urls.append(href)
        log.info(f"[CAT] Page {page_no} found {len(urls)-before} companies (total: {len(urls)})")

        url = find_next_page_url(soup)
        time.sleep(PAGE_DELAY_SEC)
    return urls


def parse_company_page(session, url):
    soup = get_soup(session, url)

    name = clean_text(soup.select_one("#company_name")) or by_label_text(soup, "Company name")

    address = clean_text(soup.select_one("#company_address")) or by_label_text(soup, "Address")

    contact_all = phones_by_label(soup, "Contact number")
    contact_1, contact_2, contact_rest = split_contact_three(contact_all)
    phone_number = phones_by_label(soup, "Mobile phone")
    website_address = by_label_text(soup, "Website address")

    fax = phones_by_label(soup, "Fax")
    establishment_year = by_label_text(soup, "Establishment year")
    employees = by_label_text(soup, "Employees")

    return {
        "company name": name,
        "address": address,
        "url": url,
        # "contact number": contact_number,
        "contact number 1": contact_1,
        "contact number 2": contact_2,
        "contact numbers (others)": contact_rest,
        "phone number": phone_number,
        "website address": website_address,
        "fax": fax,
        "establishment year": establishment_year,
        "employees": employees,
    }



def scrape_all_companies():
    rows = []
    with requests.Session() as sess:
        categories = extract_all_categories(sess)
        total_cats = len(categories)
        log.info(f"Discovered {total_cats} non-empty categories")

        for ci, cat in enumerate(categories, 1):
            group = cat["group"]; cat_url = cat["url"]
            log.info(f"[CAT {ci}/{total_cats}] {group} -> {cat_url}")

            company_urls = collect_company_links_for_category(sess, cat_url)
            log.info(f"[CAT {ci}/{total_cats}] Queued {len(company_urls)} company pages")

            for j, c_url in enumerate(company_urls, 1):
                if j % 100 == 1 or j == len(company_urls):
                    log.info(f"[CAT {ci}/{total_cats}] Company {j}/{len(company_urls)}")
                try:
                    data = parse_company_page(sess, c_url)
                    data["category"] = group
                    rows.append(data)
                except Exception as e:
                    log.warning(f"[CAT {ci}/{total_cats}] Failed company {j}: {c_url} ({e})")
                time.sleep(COMPANY_DELAY_SEC)

    # cols = ["company name","category","url","address","contact number","phone number","website address","fax","establishment year","employees"]
    cols = [
        "company name",
        "category",
        "address",
        "contact number 1",
        "contact number 2",
        "contact numbers (others)",
        "phone number",
        "fax",
        "establishment year",
        "employees",
        "website address",
    ]
    return pd.DataFrame(rows, columns=cols)

df = scrape_all_companies()
df.to_excel("yp8.xlsx", index=False)
