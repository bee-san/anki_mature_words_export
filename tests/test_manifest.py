from __future__ import annotations

import json
from pathlib import Path


def test_manifest_supports_external_anki_distribution() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["package"] == "anki_mature_words_export"
    assert manifest["name"] == "Bee's Anki Exporter"
