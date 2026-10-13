"""Reads and writes items (drafts and approved posts) as small JSON files in data/items/."""
import json
import os
import pathlib

# pending          = collected, waiting for a person to check it
# needs_attention  = collected, but the numbers did not pass the automatic checks
# approved         = a person checked it; it will appear on the site
# rejected         = a person decided not to publish it
STATUSES = ("pending", "needs_attention", "approved", "rejected")


def data_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("PESA_DATA_DIR", "data"))


def items_dir() -> pathlib.Path:
    d = data_dir() / "items"
    d.mkdir(parents=True, exist_ok=True)
    return d


def item_path(item_id: str) -> pathlib.Path:
    return items_dir() / f"{item_id}.json"


def item_exists(item_id: str) -> bool:
    return item_path(item_id).exists()


def save_item(item: dict) -> None:
    if item.get("status") not in STATUSES:
        raise ValueError(f"Unknown status: {item.get('status')!r}")
    text = json.dumps(item, indent=2, ensure_ascii=False) + "\n"
    item_path(item["id"]).write_text(text, encoding="utf-8")


def load_items() -> list:
    """Returns every readable item. A file with a typo is skipped with a warning, not a crash."""
    items = []
    for path in sorted(items_dir().glob("*.json")):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as err:
            print(f"WARNING: {path} is not valid JSON and was skipped ({err}). "
                  "Check for a missing quote or comma.")
    return items
