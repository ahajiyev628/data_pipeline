import re, unicodedata
from bs4 import BeautifulSoup, Tag

# Before: "5. Ünvan" → After: "Ünvan"
def lstrip_to_first_alpha(s):
    s = (s or "").strip()
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[i:]
    return s

# Before: "İnstagram" → After: "instagram"
def norm_key(txt):
    s = unicodedata.normalize("NFKD", (txt or "").casefold())
    return "".join(ch for ch in s if not unicodedata.combining(ch))

# Before: existing="+994 12 123 45 67", new="+ 994 50 765 43 21" → After: "+994 12 123 45 67; +994 50 765 43 21"
def phone_extractor(existing, newval):
    if not newval:
        return existing or ""
    v = re.sub(r"\+\s+(\d)", r"+\1", newval.strip())
    if not v:
        return existing or ""
    if not existing:
        return v
    return existing if v in existing else (existing + ("; " if not existing.endswith("; ") else "") + v)

# Before: "  Bakı ,  Azərbaycan  " → After: "Bakı ,  Azərbaycan"
def address_extractor(v):
    return (v or "").strip()

# Before: "<strong>Facebook</strong> : <a href='https://fb.com/page'>…</a>" → After: "https://fb.com/page"
# Before: "<strong>İnstagram:</strong> soel.parfum" → After: "soel.parfum"
def social_extractor(block_strong_tag, inline_text, follow_text):
    for sib in block_strong_tag.next_siblings:
        if isinstance(sib, Tag) and sib.name == "strong":
            break
        if isinstance(sib, Tag):
            a = sib if (sib.name == "a" and sib.has_attr("href")) else sib.find("a", href=True)
            if a:
                return (a.get("href") or a.get_text(" ", strip=True) or "").strip()
    return (inline_text + " " + follow_text).strip()

# Before: "www.example.az" → After: "www.example.az"
def web_extractor(v):
    return (v or "").strip()

# Before: '<span class="__cf_email__" data-cfemail="...">[email protected]</span>' → After: "[email protected]"
# Before: "e-mail: contact@gilasoptic.az" → After: "contact@gilasoptic.az"
# Before: "<strong>E-mail:</strong> info@foo.az" → After: "info@foo.az"
def email_extractor(block_strong_tag, inline_text, follow_text):
    for sib in block_strong_tag.next_siblings:
        if isinstance(sib, Tag) and sib.name == "strong":
            break
        if isinstance(sib, Tag):
            a = sib if (sib.name == "a") else sib.find("a") or sib
            txt = a.get_text(" ", strip=True)
            if txt:
                return txt.strip()
    return (inline_text + " " + follow_text).strip()

ALIAS = {
    "unvan": "address",
    "telefon": "telefon",
    "mobil": "mobil",
    "instagram": "instagram",
    "facebook": "facebook",
    "web": "web", "veb": "web", "sayt": "web",
    "e-mail": "email", "email": "email", "mail": "email",
    "e-mektub": "email", "e-məktub": "email", "e-poct": "email", "e-poçt": "email",
}

# Before: messy DOM (colon outside, next-strong, <br> lists, embeds) → After: clean dict rows
def extract_rows(session, headers, all_items):
    rows = []
    for company, url, category in all_items:
        r = session.get(url, headers=headers, timeout=30); r.raise_for_status()
        d = BeautifulSoup(r.text, "html.parser")
        mapped, last_field = {}, None
        box = d.select_one("div.financity-single-article-content")

        if box:
            for blk in box.select("p, li"):
                for s in blk.find_all("strong"):
                    if s.find_parent("strong") is not None:
                        continue
                    stxt = s.get_text(" ", strip=True).replace("\xa0", " ").replace("：", ":").strip()
                    if ":" in stxt:
                        key_raw, v_inline = (t.strip() for t in stxt.split(":", 1))
                    else:
                        key_raw, v_inline = stxt, ""
                    key_norm = norm_key(lstrip_to_first_alpha(key_raw).rstrip(":").strip())

                    segs = []
                    for sib in s.next_siblings:
                        if isinstance(sib, Tag) and sib.name == "strong":
                            break
                        t = sib.get_text(" ", strip=True) if isinstance(sib, Tag) else str(sib)
                        t = t.replace("\xa0", " ").strip()
                        if not t:
                            continue
                        if not segs and t.startswith(":"):
                            t = t[1:].lstrip()
                            if not t:
                                continue
                        segs.append(t)
                    v_follow = " ".join(segs).strip()
                    v = v_inline if v_inline else v_follow

                    if not v:
                        nxt = s.find_next_sibling("strong")
                        if nxt:
                            cand = nxt.get_text(" ", strip=True).replace("\xa0", " ").replace("：", ":").strip()
                            if cand.startswith(":"):
                                v = cand.lstrip(":").strip()
                            elif ":" not in cand:
                                v = cand
                            else:
                                pre, post = (t.strip() for t in cand.split(":", 1))
                                if not pre or norm_key(lstrip_to_first_alpha(pre)) not in ALIAS:
                                    v = post

                    if (":" in stxt) or (key_norm in ALIAS):
                        labels = [lstrip_to_first_alpha(x.strip()) for x in re.split(r"\s*(?:,|/| və )\s*", key_clean) if x.strip()]
                        for lab in labels:
                            canon = ALIAS.get(norm_key(lab), norm_key(lab))

                            if canon in ("telefon", "mobil"):
                                mapped[canon] = phone_extractor(mapped.get(canon, ""), v)

                            elif canon == "email":
                                if "email" not in mapped:
                                    mapped["email"] = email_extractor(s, v_inline, v_follow)

                            elif canon in ("instagram", "facebook"):
                                sv = social_extractor(s, v_inline, v_follow)
                                if sv and canon not in mapped:
                                    mapped[canon] = sv
                                if canon == "facebook":
                                    rt = (v_inline + " " + v_follow).strip()
                                    m = re.search(r"(?:İnstagram|Instagram)\s*:\s*([^\s,;]+)", rt, re.I)
                                    if m and "instagram" not in mapped:
                                        mapped["instagram"] = m.group(1).strip()

                            elif canon == "web":
                                if v and "web" not in mapped:
                                    mapped["web"] = web_extractor(v)

                            elif canon == "address":
                                if v and "address" not in mapped:
                                    mapped["address"] = address_extractor(v)

                            else:
                                if v and canon not in mapped:
                                    mapped[canon] = v.strip()

                            last_field = canon if len(labels) == 1 else last_field
                    else:
                        cont = stxt
                        if cont:
                            if last_field in ("telefon", "mobil"):
                                mapped[last_field] = phone_extractor(mapped.get(last_field, ""), cont)
                            elif last_field in ("facebook", "instagram", "web", "address"):
                                prev = mapped.get(last_field, "") or ""
                                if cont not in prev:
                                    mapped[last_field] = (prev + (" " if prev else "") + cont).strip()

            for blk in box.select("p, li"):
                flat = blk.get_text("\n", strip=True).replace("\xa0", " ")
                for line in (x for x in flat.split("\n") if ":" in x):
                    k, v = (t.strip() for t in line.split(":", 1))
                    key = lstrip_to_first_alpha(k)
                    canon = ALIAS.get(norm_key(key), norm_key(key))
                    if canon in ("telefon", "mobil"):
                        mapped[canon] = phone_extractor(mapped.get(canon, ""), v)
                    elif canon == "email" and "email" not in mapped:
                        mapped["email"] = v.strip()
                    elif canon in ("instagram", "facebook") and canon not in mapped:
                        mapped[canon] = v.strip()
                    elif canon == "web" and "web" not in mapped:
                        mapped["web"] = web_extractor(v)
                    elif canon == "address" and "address" not in mapped:
                        mapped["address"] = address_extractor(v)

            for w in box.select("figure .wp-block-embed__wrapper, .wp-block-embed__wrapper"):
                txt = (w.get_text(" ", strip=True) or "").strip()
                if not txt:
                    continue
                if "instagram.com" in txt and "instagram" not in mapped:
                    mapped["instagram"] = txt
                elif "facebook.com" in txt and "facebook" not in mapped:
                    mapped["facebook"] = txt
                elif "web" not in mapped:
                    mapped["web"] = txt

        if "web" not in mapped:
            sayta = d.find(lambda t: hasattr(t, "get_text") and t.name in ("h3", "p") and "Sayta keçid" in t.get_text())
            if sayta:
                a = sayta.find("a", href=True)
                if a:
                    mapped["web"] = (a.get("href") or a.get_text(" ", strip=True) or "").strip()

        rows.append({
            "company": company,
            "url": url,
            "category": category,
            "address": mapped.get("address", ""),
            "telefon": mapped.get("telefon", ""),
            "mobil": mapped.get("mobil", ""),
            "instagram": mapped.get("instagram", ""),
            "facebook": mapped.get("facebook", ""),
            "web": mapped.get("web", ""),
            "email": mapped.get("email", ""),
        })
    return rows

import pandas as pd

df = pd.DataFrame(rows)

df = df.replace('', pd.NA)
df = df.drop_duplicates(subset=['url'])
df = df.assign(
    company=df['company'].str.strip(),
    category=df['category'].astype('string'),
    address=df['address'].astype('string'),
    telefon=df['telefon'].astype('string'),
    mobil=df['mobil'].astype('string'),
    email=df['email'].astype('string'),
    web=df['web'].astype('string'),
    facebook=df['facebook'].astype('string'),
    instagram=df['instagram'].astype('string'),
)

df = df[[
    'company', 'category', 'url',
    'address', 'telefon', 'mobil',
    'email', 'web', 'facebook', 'instagram'
]]

df.to_excel('partners13.xlsx', index=False)
