"""Looks at a web page for headlines that match keywords (new bond sale, IPO approval, ...).

By design this collector saves only the headline and the link. It does not try to extract
facts such as prices or dates, because a wrong figure in a financial post does real harm.
A person reads the original and decides whether to approve the notice.

To keep the review list short, it skips general pages (rules, checklists, licensing), links that
only jump around a page, and dated results older than a few weeks.
"""
import datetime
import hashlib
import re
import urllib.parse

from bs4 import BeautifulSoup

from . import http, store

# Defaults. Any of these can be overridden per source in config.yaml.
DEFAULT_EXCLUDE_WORDS = ["checklist", "guidelines", "rules", "licence", "license", "licensing",
                         "coffee", "intermediary"]
DEFAULT_EXCLUDE_URL_PARTS = ["/forms/", "#"]
DEFAULT_MAX_AGE_DAYS = 45


def date_in_text(text: str):
    """Finds a date written like 'DATED 29-06-2026' or 'DATED 10/11/25' and returns a date, or None."""
    plain = urllib.parse.unquote(text)
    m = re.search(r"DATED\s*(\d{2})[-/](\d{2})[-/](\d{2,4})", plain, re.I)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def find_headlines(html: str, base_url: str, keywords: list, exclude_words=None,
                   exclude_url_parts=None, max_age_days=DEFAULT_MAX_AGE_DAYS, today=None) -> list:
    """Returns [(title, raw_url, date_or_None)] for links that look like fresh, relevant headlines."""
    exclude_words = [w.lower() for w in (DEFAULT_EXCLUDE_WORDS if exclude_words is None else exclude_words)]
    exclude_url_parts = DEFAULT_EXCLUDE_URL_PARTS if exclude_url_parts is None else exclude_url_parts
    today = today or datetime.date.today()
    soup = BeautifulSoup(html, "html.parser")
    wanted = [k.lower() for k in keywords]
    seen, found = set(), []
    for a in soup.find_all("a", href=True):
        title = " ".join(a.get_text(" ", strip=True).split())
        lower = title.lower()
        if len(title) < 20 or not any(k in lower for k in wanted):
            continue
        if any(w in lower for w in exclude_words):
            continue
        url = urllib.parse.urljoin(base_url, a["href"])
        if url in seen or url.startswith("mailto:") or url.rstrip("/") == base_url.rstrip("/"):
            continue
        if any(part in url for part in exclude_url_parts):
            continue
        dated = date_in_text(title) or date_in_text(url)
        if dated and max_age_days is not None and (today - dated).days > max_age_days:
            continue
        seen.add(url)
        found.append((title, url, dated))
    return found


def collect(source: dict, cfg: dict):
    new_items, messages = [], []
    html = http.get(source["url"], cfg)
    found = find_headlines(
        html, source["url"], source["keywords"],
        exclude_words=source.get("exclude_keywords"),
        exclude_url_parts=source.get("exclude_url_parts"),
        max_age_days=source.get("max_age_days", DEFAULT_MAX_AGE_DAYS),
    )
    if not found:
        messages.append(f"{source['name']}: no recent matching headlines found. "
                        "That can be normal; if it keeps happening, check the address in config.yaml.")
        return new_items, messages
    today = datetime.date.today().isoformat()
    for title, raw_url, dated in found:
        if len(new_items) >= source.get("max_new_per_run", 10):
            break
        # The id comes from the raw link so items collected earlier are still recognised.
        item_id = "notice-" + hashlib.sha1(raw_url.encode("utf-8")).hexdigest()[:10]
        if store.item_exists(item_id):
            continue
        item = {
            "id": item_id,
            "kind": "notice",
            "status": "pending",
            "title": title,
            "published_on": dated.isoformat() if dated else today,
            "source_name": source["name"],
            "source_url": http.safe_url(raw_url),
            "problems": [],
            "data": {},
            "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        store.save_item(item)
        new_items.append(item)
    return new_items, messages
