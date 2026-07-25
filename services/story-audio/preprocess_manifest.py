"""Build a category-first index from the flat sound manifest.

Example:
    python preprocess_manifest.py C:\\Users\\sriya\\Downloads\\manifest.json sound_catalog_index.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import PurePosixPath, Path
from typing import Any


def category_from_path(file_path: str) -> str:
    """Return the first directory in a portable manifest path.

    ``fantasy/078_teleport.mp3`` becomes ``fantasy``. Files stored directly
    in the audio root are placed under ``uncategorized``.
    """
    parent = PurePosixPath(file_path.replace("\\", "/")).parent
    return parent.parts[0] if parent.parts and parent.parts[0] != "." else "uncategorized"


def build_index(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Group sounds as category -> normalized term -> one or more sound files."""
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for entry in entries:
        term = str(entry.get("term", "")).strip()
        file_path = str(entry.get("file", "")).strip()
        if not term or not file_path:
            continue

        category = category_from_path(file_path)
        # A list retains alternatives when the same term appears more than once.
        grouped[category][term].append(
            {
                "file": file_path,
                "source_id": entry.get("source_id"),
                "source_name": entry.get("source_name"),
                "source_url": entry.get("source_url"),
                "creator": entry.get("creator"),
                "license": entry.get("license"),
                "duration_seconds": entry.get("duration_seconds"),
            }
        )

    categories = {
        category: {
            term: sorted(variants, key=lambda item: item["file"])
            for term, variants in sorted(terms.items())
        }
        for category, terms in sorted(grouped.items())
    }
    return {
        "schema_version": 1,
        "description": "Choose a category first, then a sound term; use the selected file path to fetch the MP3.",
        "categories": categories,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Group a sound manifest by its top-level audio directory.")
    parser.add_argument("input", type=Path, help="Flat manifest JSON file")
    parser.add_argument("output", type=Path, help="Destination category-first index JSON file")
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as source:
        entries = json.load(source)
    if not isinstance(entries, list):
        raise ValueError("Input manifest must be a JSON array of sound entries.")

    index = build_index(entries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as destination:
        json.dump(index, destination, ensure_ascii=False, indent=2)
        destination.write("\n")

    category_count = len(index["categories"])
    sound_count = sum(len(variants) for terms in index["categories"].values() for variants in terms.values())
    print(f"Wrote {sound_count} sounds in {category_count} categories to {args.output}")


if __name__ == "__main__":
    main()
