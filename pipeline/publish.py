"""Builds the website from approved items only. Output goes to site/ (plain HTML files)."""
import datetime
import json
import pathlib
import shutil
import sys

import yaml
from jinja2 import DictLoader, Environment

from . import store
from .tbills import human_date

CSS = """
:root{--ink:#0E1A2B;--ground:#F4F6F8;--card:#fff;--line:#DDE3EA;--muted:#52606F;--amber:#F5A623;--teal:#0B6E6E}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:"DM Sans",system-ui,sans-serif;line-height:1.6}
header{background:var(--ink);color:#fff}
header .in,main,footer{max-width:1000px;margin:0 auto;padding:20px 24px}
header a{color:#fff;text-decoration:none;font-weight:700;font-size:20px}
h1{font-size:34px;line-height:1.15;margin:24px 0 8px}
h2{font-size:22px;margin:32px 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin:12px 0}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:10px 8px;border-top:1px solid var(--line);font-variant-numeric:tabular-nums}
th{border-top:0;color:var(--muted);font-size:13px}
.num{text-align:right}
.muted{color:var(--muted);font-size:14px}
.scroll{overflow-x:auto}
a{color:var(--teal)}
ul.posts{list-style:none;padding:0}
ul.posts li{padding:12px 0;border-top:1px solid var(--line)}
footer{color:var(--muted);font-size:13px}
"""

TEMPLATES = {
    "base.html": """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | {{ site_name }}</title><style>{{ css }}</style></head>
<body><header><div class="in"><a href="{{ root }}index.html">{{ site_name }}</a></div></header>
<main>{% block content %}{% endblock %}</main>
<footer>{{ disclaimer }}</footer></body></html>""",

    "tbill_table.html": """<div class="scroll"><table>
<thead><tr><th>Bill</th><th class="num">Rate before tax</th><th class="num">After {{ (d.withholding_rate * 100)|round|int }}% tax</th><th class="num">Bids vs offered</th><th class="num">Accepted</th></tr></thead>
<tbody>{% for tenor in ['91','182','364'] %}{% set t = d.tenors[tenor] %}
<tr><td>{{ tenor }}-day</td>
<td class="num">{% if t.rate_pct is not none %}{{ '%.2f'|format(t.rate_pct) }}%{% else %}n/a{% endif %}</td>
<td class="num">{% if t.net_rate_pct is not none %}{{ '%.2f'|format(t.net_rate_pct) }}%{% else %}n/a{% endif %}</td>
<td class="num">{% if t.bids_m is not none and t.offered_m is not none %}{{ t.bids_m|bn }} vs {{ t.offered_m|bn }}{% else %}n/a{% endif %}</td>
<td class="num">{% if t.accepted_m is not none %}{{ t.accepted_m|bn }}{% else %}n/a{% endif %}</td></tr>{% endfor %}
</tbody></table></div>
{% if d.next_value_date %}<p class="muted">Next issue date: {{ d.next_value_date|hd }}.</p>{% endif %}""",

    "index.html": """{% extends "base.html" %}{% block content %}
<h1>This week's snapshot</h1>
<p class="muted">Updated {{ updated }}. Every item was checked by a person before publishing.</p>
{% if tbill %}<h2>{{ tbill.title }}</h2>
<div class="card">{% set d = tbill.data %}{% include "tbill_table.html" %}
<p class="muted">Source: <a href="{{ tbill.source_url }}">{{ tbill.source_name }}</a></p></div>{% endif %}
<h2>Latest posts</h2>
{% if posts %}<ul class="posts">{% for p in posts %}
<li><a href="posts/{{ p.id }}.html">{{ p.title }}</a><div class="muted">{{ p.published_on|hd }} · {{ p.source_name }}</div></li>{% endfor %}</ul>
{% else %}<p class="muted">No posts yet.</p>{% endif %}
{% endblock %}""",

    "post.html": """{% extends "base.html" %}{% block content %}
<p><a href="{{ root }}index.html">Back to the snapshot</a></p>
<h1>{{ item.title }}</h1>
<p class="muted">{{ item.published_on|hd }} · Source: <a href="{{ item.source_url }}">{{ item.source_name }}</a></p>
{% if item.kind == 'tbill_auction' %}<div class="card">{% set d = item.data %}{% include "tbill_table.html" %}</div>
{% else %}<div class="card"><p>This is a headline from {{ item.source_name }}. Read the original for the full details.</p>
<p><a href="{{ item.source_url }}">Open the original</a></p></div>{% endif %}
{% endblock %}""",
}


def _bn(millions):
    return f"KES {millions / 1000:.1f}bn"


def make_env() -> Environment:
    env = Environment(loader=DictLoader(TEMPLATES), autoescape=True)
    env.filters["hd"] = lambda iso: human_date(iso) if iso else ""
    env.filters["bn"] = _bn
    return env


def build(out_dir: str = "site", config_path: str = "config.yaml") -> pathlib.Path:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    approved = [i for i in store.load_items() if i.get("status") == "approved"]
    approved.sort(key=lambda i: (i.get("published_on") or "", i["id"]), reverse=True)
    tbills = [i for i in approved if i.get("kind") == "tbill_auction"]

    out = pathlib.Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "posts").mkdir(parents=True)

    env = make_env()
    common = {"site_name": cfg["site"]["name"], "disclaimer": cfg["disclaimer"], "css": CSS}
    if "[Add your regulatory disclaimer" in cfg["disclaimer"]:
        print("NOTE: the disclaimer in config.yaml still has its placeholder. Have it reviewed before launch.")

    updated = human_date(datetime.date.today().isoformat())
    (out / "index.html").write_text(env.get_template("index.html").render(
        title="Snapshot", root="", tbill=tbills[0] if tbills else None, posts=approved, updated=updated, **common),
        encoding="utf-8")
    for item in approved:
        (out / "posts" / f"{item['id']}.html").write_text(env.get_template("post.html").render(
            title=item["title"], root="../", item=item, **common), encoding="utf-8")

    latest = {"generated_on": datetime.date.today().isoformat(), "tbill_auction": tbills[0] if tbills else None}
    (out / "latest.json").write_text(json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Built {len(approved)} approved item(s) into {out}/")
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "site")
