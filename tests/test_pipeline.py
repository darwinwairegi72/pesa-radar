import json

import pytest

from pipeline import headlines, publish, store, tbills

# Text laid out like the CBK results PDF of 31 August 2026 (shape seen on the CBK site).
FIXTURE = """A. RESULTS OF 91, 182 & 364 DAYS TREASURY  BILLS ISSUES 2697/091, 2671/182 & 2626/364  DATED 31/08/2026
Tenor 91 DAYS 182 DAYS 364 DAYS TOTAL
Due Date 30/11/2026 01/03/2027 30/08/2027
Amount Offered (Kshs. M) 8,000.00                      10,000.00                    10,000.00                          28,000.00
Bids Received (Kshs. M) 23,697.72                    26,876.20                    6,161.29                            56,735.22
Performance Rate (%) 296.22                         268.76                         61.61                                 202.63
Total Amount Accepted (Kshs. M) 23,108.63                    15,053.79                    6,159.48                            44,321.90
Bid-to-Cover Ratio 1.03 1.79 1.00 1.28
This Auction Last Auction Variance
91 - day       8.7692 8.7700 0.0008
182-day 8.9400 8.9480 0.0080
364 - day     9.0323 9.0356 0.0033
Auction Dates & Bids Closure 03/09/2026 03/09/2026 03/09/2026
Results Announcement 03/09/2026 03/09/2026 03/09/2026
NEXT TREASURY BILLS AUCTIONS: ISSUE NOS. 2698/091, 2672/182 & 2627/364 DATED 07/09/2026
"""

CFG = {"tax": {"withholding_rate": 0.15}}


def test_parses_numbers_and_dates():
    p = tbills.parse_tbill_text(FIXTURE)
    assert p["problems"] == []
    assert p["value_date"] == "2026-08-31"
    assert p["auction_date"] == "2026-09-03"
    assert p["next_value_date"] == "2026-09-07"
    t91 = p["tenors"]["91"]
    assert t91["offered_m"] == 8000.0
    assert t91["bids_m"] == 23697.72
    assert t91["accepted_m"] == 23108.63
    assert t91["rate_pct"] == 8.7692
    assert p["tenors"]["364"]["rate_pct"] == 9.0323


def test_weighted_average_line_is_used_when_present_and_must_agree():
    agree = FIXTURE + "\nWeighted Average Interest Rate of accepted bids 8.7692% 8.9400% 9.0323%\n"
    assert tbills.parse_tbill_text(agree)["problems"] == []
    clash = FIXTURE + "\nWeighted Average Interest Rate of accepted bids 8.1000% 8.9400% 9.0323%\n"
    problems = tbills.parse_tbill_text(clash)["problems"]
    assert any("91-day rate differs" in p for p in problems)


def test_sanity_checks_flag_bad_numbers():
    bad = FIXTURE.replace("23,108.63", "99,999.00")
    assert any("accepted amount is larger" in p for p in tbills.parse_tbill_text(bad)["problems"])
    missing = FIXTURE.replace("Bids Received", "Bids Recvd")
    assert any("Bids Received" in p for p in tbills.parse_tbill_text(missing)["problems"])
    assert tbills.parse_tbill_text("nothing useful here")["problems"]


def test_item_is_pending_when_clean_and_needs_attention_when_not():
    clean = tbills.build_item(tbills.parse_tbill_text(FIXTURE), "https://example.org/x.pdf", CFG, "2026-08-31")
    assert clean["status"] == "pending"
    assert clean["id"] == "tbill-2026-08-31"
    assert clean["data"]["tenors"]["91"]["net_rate_pct"] == 7.45
    assert clean["title"] == "Treasury bill auction results, 3 September 2026"
    wrong_name = tbills.build_item(tbills.parse_tbill_text(FIXTURE), "u", CFG, "2026-08-24")
    assert wrong_name["status"] == "needs_attention"


def test_find_pdf_links_picks_newest_first():
    html = """<a href="/uploads/91_day_historical_treasury_bill_results/a%20DATED%2031-08-2026.pdf">x</a>
              <a href="/uploads/91_day_historical_treasury_bill_results/b%20DATED%2028-09-2026.pdf">y</a>
              <a href="/other.pdf">z</a>"""
    links = tbills.find_pdf_links(html, "https://www.centralbank.go.ke/bills-bonds/treasury-bills/")
    assert [d for _, d in links] == ["2026-09-28", "2026-08-31"]
    assert links[0][0].startswith("https://www.centralbank.go.ke/uploads/")


def test_headlines_match_keywords_only():
    html = """<a href="/n1">CBK opens KSh50 billion Treasury bond sale</a>
              <a href="/n2">Annual staff picnic photos from the weekend</a>
              <a href="/n3">Short</a>"""
    found = headlines.find_headlines(html, "https://example.org/", ["bond"])
    assert found == [("CBK opens KSh50 billion Treasury bond sale", "https://example.org/n1")]


def test_only_approved_items_are_published(tmp_path, monkeypatch):
    monkeypatch.setenv("PESA_DATA_DIR", str(tmp_path / "data"))
    approved = tbills.build_item(tbills.parse_tbill_text(FIXTURE), "https://example.org/a.pdf", CFG, "2026-08-31")
    approved["status"] = "approved"
    store.save_item(approved)
    pending = dict(approved, id="notice-pending", kind="notice", status="pending", title="SECRET DRAFT TITLE", data={})
    store.save_item(pending)
    (store.items_dir() / "broken.json").write_text("{ not json", encoding="utf-8")

    out = publish.build(str(tmp_path / "site"), config_path="config.yaml")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Treasury bill auction results, 3 September 2026" in index
    assert "8.77%" in index and "7.45%" in index
    assert "SECRET DRAFT TITLE" not in index
    assert (out / "posts" / "tbill-2026-08-31.html").exists()
    assert not (out / "posts" / "notice-pending.html").exists()
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assert latest["tbill_auction"]["id"] == "tbill-2026-08-31"


def test_save_rejects_unknown_status(tmp_path, monkeypatch):
    monkeypatch.setenv("PESA_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        store.save_item({"id": "x", "status": "maybe"})
