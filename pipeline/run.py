"""Runs every collector. One collector failing never stops the others.

Writes out/summary.md when there is something for a person to look at. The GitHub workflow
turns that file into an issue, which emails the owner.
"""
import os
import pathlib

import yaml

from . import headlines, tbills


def edit_link(item_id: str) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    path = f"data/items/{item_id}.json"
    return f"https://github.com/{repo}/edit/main/{path}" if repo else path


def write_summary(new_items: list, messages: list) -> None:
    out = pathlib.Path("out")
    out.mkdir(exist_ok=True)
    summary = out / "summary.md"
    if not new_items and not messages:
        if summary.exists():
            summary.unlink()
        print("Nothing new.")
        return
    lines = ["# Pesa Radar: please review", ""]
    if new_items:
        lines += ["## New drafts", ""]
        for item in new_items:
            flag = " (**needs attention**)" if item["status"] == "needs_attention" else ""
            lines.append(f"- **{item['title']}**{flag}")
            lines.append(f"  - Check it against the source: {item['source_url']}")
            lines.append(f"  - To publish, open {edit_link(item['id'])} and change `\"pending\"` to `\"approved\"`, "
                         "then choose Commit changes. To skip it, change it to `\"rejected\"`.")
            for problem in item.get("problems", []):
                lines.append(f"  - Problem found: {problem}")
        lines.append("")
    if messages:
        lines += ["## Things that did not work", ""] + [f"- {m}" for m in messages] + [""]
    summary.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    new_items, messages = [], []

    try:
        items, msgs = tbills.collect(cfg)
        new_items += items
        messages += msgs
    except Exception as err:  # noqa: BLE001 - we want to keep going and report it
        messages.append(f"T-bill collector failed: {err}")

    for source in cfg.get("headline_sources", []):
        try:
            items, msgs = headlines.collect(source, cfg)
            new_items += items
            messages += msgs
        except Exception as err:  # noqa: BLE001
            messages.append(f"{source['name']} collector failed: {err}")

    write_summary(new_items, messages)


if __name__ == "__main__":
    main()
