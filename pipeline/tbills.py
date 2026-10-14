"""Collects CBK Treasury bill auction results.

Flow: open the CBK page -> find results PDFs -> read the numbers -> run sanity checks ->
save a draft. Drafts that fail the checks are marked "needs_attention" so a person looks at
them closely. Nothing is published until a person approves it.
"""
import datetime
import io
import re
import urllib.parse

from bs4 import BeautifulSoup
from pypdf import PdfReader

from . import http, store

TENORS = ("91", "182", "364")
NUM = r"[\d,]+\.\d{2}"          # amounts like 23,697.72
RATE = r"\d{1,2}\.\d{2,4}"      # rates like 8.7692


def human_date(iso: str) -> str:
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


def _iso(dmy: str) -> str:
    """'12-10-2026' or '12/10/2026' -> '2026-10-12'."""
    day, month, year = re.split(r"[-/]", dmy)
    return f"{year}-{month}-{day}"


def _signature_date(text: str):
    """The Director's sign-off date ('October 08, 2026') is the date the results were announced."""
    m = re.search(r"Director,?\s+Financial\s+Markets\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", text)
    if not m:
        return None
    try:
        d = datetime.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y")
    except ValueError:
        return None
    return d.date().isoformat()


def _normalise(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", text.replace("\u00a0", " "))


def extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _three_amounts(text: str, label: str):
    """Finds a row such as 'Amount Offered (Kshs. M) 8,000.00 10,000.00 10,000.00 28,000.00'."""
    pattern = label + r"[^\d]{0,60}?((?:" + NUM + r"\s*){3,4})"
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    numbers = re.findall(NUM, match.group(1))[:3]
    return [float(n.replace(",", "")) for n in numbers]


def _rates(text: str):
    """Returns (rates from the 'Weighted Average Interest Rate' line, rates from the table)."""
    label_rates = None
    m = re.search(
        r"Weighted\s+Average\s+Interest\s+Rate\s+of\s+accepted\s+bids[\s\S]{0,40}?(" + RATE + r")\s*%[\s\S]{0,20}?("
        + RATE + r")\s*%[\s\S]{0,20}?(" + RATE + r")\s*%", text, re.I)
    if m:
        label_rates = [float(x) for x in m.groups()]
    table = {}
    for tenor in TENORS:
        mt = re.search(r"\b" + tenor + r"\s*-\s*day\s+(" + RATE + r")\s+(" + RATE + r")", text, re.I)
        if mt:
            table[tenor] = (float(mt.group(1)), float(mt.group(2)))
    return label_rates, table


def parse_tbill_text(text: str) -> dict:
    """Turns the PDF text into numbers and a list of problems found by the sanity checks."""
    text = _normalise(text)
    problems = []
    parsed = {"tenors": {}, "problems": problems}

    # The "NEXT TREASURY BILLS AUCTIONS ... DATED <date>" line belongs to the FOLLOWING auction.
    # Take it out before looking for this auction's own date, or the two get mixed up.
    nxt = re.search(r"NEXT\s+TREASURY\s+BILLS?\s+AUCTIONS?[\s\S]{0,150}?DATED\s+(\d{2}[-/]\d{2}[-/]\d{4})", text, re.I)
    parsed["next_value_date"] = _iso(nxt.group(1)) if nxt else None
    own_text = text.replace(nxt.group(0), " ") if nxt else text

    m = re.search(r"DATED\s*\.?\s*(\d{2}[-/]\d{2}[-/]\d{4})", own_text)
    parsed["value_date"] = _iso(m.group(1)) if m else None   # build_item falls back to the file name

    # NOTE: the "Results Announcement" row in these PDFs describes the NEXT auction, so it is not used here.
    parsed["auction_date"] = _signature_date(text)
    m = re.search(r"Auction\s+Dates\s*&\s*Bids\s+Closure\s+(\d{2}[-/]\d{2}[-/]\d{4})", text, re.I)
    parsed["next_auction_date"] = _iso(m.group(1)) if m else None

    offered = _three_amounts(text, r"Amount\s+Offered")
    bids = _three_amounts(text, r"Bids\s+Received")
    accepted = _three_amounts(text, r"Total\s+Amount\s+Accepted")
    for name, row in (("Amount Offered", offered), ("Bids Received", bids), ("Total Amount Accepted", accepted)):
        if row is None or len(row) != 3:
            problems.append(f"Could not read the '{name}' row.")

    label_rates, table = _rates(text)
    table_rates = [table[t][0] for t in TENORS] if all(t in table for t in TENORS) else None
    if label_rates is None and table_rates is None:
        problems.append("Could not read the interest rates.")
    rates = label_rates or table_rates
    if label_rates and table_rates:
        for tenor, a, b in zip(TENORS, label_rates, table_rates):
            if abs(a - b) > 0.0001:
                problems.append(f"{tenor}-day rate differs between two places in the PDF ({a} vs {b}).")

    for i, tenor in enumerate(TENORS):
        entry = {
            "offered_m": offered[i] if offered and len(offered) == 3 else None,
            "bids_m": bids[i] if bids and len(bids) == 3 else None,
            "accepted_m": accepted[i] if accepted and len(accepted) == 3 else None,
            "rate_pct": rates[i] if rates and len(rates) == 3 else None,
            "previous_rate_pct": table[tenor][1] if tenor in table else None,
        }
        parsed["tenors"][tenor] = entry
        rate = entry["rate_pct"]
        if rate is not None and not (0 < rate < 30):
            problems.append(f"{tenor}-day rate {rate} looks wrong.")
        if entry["accepted_m"] is not None and entry["bids_m"] is not None:
            if entry["accepted_m"] > entry["bids_m"] + 0.01:
                problems.append(f"{tenor}-day: accepted amount is larger than bids received.")
    return parsed


def build_item(parsed: dict, source_url: str, cfg: dict, expected_date: str = None) -> dict:
    wht = cfg.get("tax", {}).get("withholding_rate", 0.15)
    problems = list(parsed["problems"])
    value_date = parsed.get("value_date") or expected_date
    if not value_date:
        problems.append("Could not find the issue date in the PDF or the file name.")
    if expected_date and parsed.get("value_date") and parsed["value_date"] != expected_date:
        problems.append(f"The date in the PDF ({parsed['value_date']}) differs from the file name ({expected_date}).")
    tenors = {}
    for tenor, entry in parsed["tenors"].items():
        entry = dict(entry)
        entry["net_rate_pct"] = round(entry["rate_pct"] * (1 - wht), 2) if entry["rate_pct"] is not None else None
        tenors[tenor] = entry
    headline_date = parsed.get("auction_date") or value_date
    if parsed.get("auction_date"):
        title = f"Treasury bill auction results, {human_date(parsed['auction_date'])}"
    elif value_date:
        title = f"Treasury bill results, issue date {human_date(value_date)}"
    else:
        title = "Treasury bill auction results"
    return {
        "id": f"tbill-{value_date}",
        "kind": "tbill_auction",
        "status": "needs_attention" if problems else "pending",
        "title": title,
        "published_on": headline_date,
        "source_name": "Central Bank of Kenya",
        "source_url": source_url,
        "problems": problems,
        "data": {
            "value_date": value_date,
            "auction_date": parsed.get("auction_date"),
            "next_auction_date": parsed.get("next_auction_date"),
            "next_value_date": parsed.get("next_value_date"),
            "withholding_rate": wht,
            "tenors": tenors,
        },
        "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }


def find_pdf_links(html: str, base_url: str):
    """Returns [(pdf_url, iso_date)] newest first, using the date in the file name (DATED dd-mm-yyyy)."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(base_url, a["href"])
        plain = urllib.parse.unquote(href)
        if ".pdf" in plain.lower() and "treasury_bill_results" in plain.lower():
            m = re.search(r"DATED\s*(\d{2})-(\d{2})-(\d{4})", plain, re.I)
            if m:
                found[http.safe_url(href)] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return sorted(found.items(), key=lambda kv: kv[1], reverse=True)


def collect(cfg: dict):
    new_items, messages = [], []
    settings = cfg["tbills"]
    html = http.get(settings["listing_url"], cfg)
    links = find_pdf_links(html, settings["listing_url"])
    if not links:
        messages.append("T-bills: no results PDFs were found on the CBK page. The page layout may have changed.")
        return new_items, messages
    for href, iso in links[: settings.get("look_at_latest", 3)]:
        if store.item_exists(f"tbill-{iso}"):
            continue
        if len(new_items) >= settings.get("max_new_per_run", 2):
            break
        text = extract_pdf_text(http.get(href, cfg, binary=True))
        item = build_item(parse_tbill_text(text), href, cfg, expected_date=iso)
        if store.item_exists(item["id"]):
            continue
        store.save_item(item)
        new_items.append(item)
    return new_items, messages
