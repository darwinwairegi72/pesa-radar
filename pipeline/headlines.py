"""Looks at a web page for headlines that match keywords (new bond sale, IPO approval, ...).

By design this collector saves only the headline and the link. It does not try to extract
facts such as prices or dates, because a wrong figure in a financial post does real harm.
A person reads the original and decides whether to approve the notice.
"""
import datetime
import hashlib
import urllib.parse

from bs4 import BeautifulSoup

from . import http, store


def find_headlines(html: str, base_url: str, keywords: list) -> list:
    soup = BeautifulSoup(html, "html.parser")
    wanted = [k.lower() for k in keywords]
    seen, found = set(), []
    for a in soup.find_all("a", href=True):
        title = " ".join(a.get_text(" ", strip=True).split())
        if len(title) < 20 or not any(k in title.lower() for k in wanted):
            continue
        url = urllib.parse.urljoin(base_url, a["href"])
        if url in seen or url.startswith("mailto:") or url.rstrip("/") == base_url.rstrip("/"):
            continue
        seen.add(url)
        found.append((title, url))
    return found


def collect(source: dict, cfg: dict):
    new_items, messages = [], []
    html = http.get(source["url"], cfg)
    found = find_headlines(html, source["url"], source["keywords"])
    if not found:
        messages.append(f"{source['name']}: no matching headlines found. Check the address in config.yaml.")
        return new_items, messages
    today = datetime.date.today().isoformat()
    for title, url in found:
        if len(new_items) >= source.get("max_new_per_run", 10):
            break
        item_id = "notice-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        if store.item_exists(item_id):
            continue
        item = {
            "id": item_id,
            "kind": "notice",
            "status": "pending",
            "title": title,
            "published_on": today,
            "source_name": source["name"],
            "source_url": url,
            "problems": [],
            "data": {},
            "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        store.save_item(item)
        new_items.append(item)
    return new_items, messages
