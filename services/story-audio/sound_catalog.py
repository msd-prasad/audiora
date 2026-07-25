"""Load the category-first sound index used by the story generator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_INDEX = Path(__file__).with_name("sound_catalog_index.json")


def load_catalog() -> dict[str, Any]:
    """Load the preprocessed manifest, or return an empty catalogue if absent."""
    index_path = Path(os.getenv("SOUND_CATALOG_INDEX", DEFAULT_INDEX))
    if not index_path.exists():
        return {"categories": {}}
    with index_path.open(encoding="utf-8") as source:
        catalog = json.load(source)
    if not isinstance(catalog.get("categories"), dict):
        raise ValueError("Sound catalogue must contain a 'categories' object.")
    return catalog


def catalog_prompt() -> str:
    """Render category -> term -> exact MP3 paths for the model context."""
    categories = load_catalog()["categories"]
    lines: list[str] = []
    for category, terms in categories.items():
        lines.append(f"[{category}]")
        for term, variants in terms.items():
            paths = ", ".join(item["file"] for item in variants)
            lines.append(f"{term} -> {paths}")
    return "\n".join(lines)


def valid_sound_pairs() -> set[tuple[str, str]]:
    """Return every permitted (term, file) pair for response validation."""
    return {
        (term, item["file"])
        for terms in load_catalog()["categories"].values()
        for term, variants in terms.items()
        for item in variants
    }
