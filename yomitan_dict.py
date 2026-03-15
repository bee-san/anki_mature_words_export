from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from .config import AddonConfig

BANK_CHUNK_SIZE = 50_000
INDEX_PATH = "/bees-yomitan-known/index.json"
DOWNLOAD_PATH = "/bees-yomitan-known/dictionary.zip"


@dataclass(frozen=True)
class DictionaryArtifacts:
    revision: str
    index_data: dict[str, object]
    index_bytes: bytes
    zip_bytes: bytes


def build_dictionary_artifacts(
    words: list[str], config: AddonConfig
) -> DictionaryArtifacts:
    revision = compute_revision(words)
    index_data = build_index_data(config, revision)
    index_bytes = _json_bytes(index_data)
    zip_bytes = build_yomitan_zip(words, config, revision)
    return DictionaryArtifacts(
        revision=revision,
        index_data=index_data,
        index_bytes=index_bytes,
        zip_bytes=zip_bytes,
    )


def compute_revision(words: list[str]) -> str:
    joined = "\n".join(words).encode("utf-8")
    digest = sha256(joined).hexdigest()
    return f"knownfreq-{digest[:16]}-{len(words)}"


def build_index_data(config: AddonConfig, revision: str) -> dict[str, object]:
    base_url = f"http://127.0.0.1:{config.http_port}"
    return {
        "title": f"Bee Known Words (Deck={config.deck_name}, Mature>={config.mature_days}d)",
        "format": 3,
        "revision": revision,
        "frequencyMode": "rank-based",
        "isUpdatable": True,
        "indexUrl": f"{base_url}{INDEX_PATH}",
        "downloadUrl": f"{base_url}{DOWNLOAD_PATH}",
        "description": "Known-word frequency dictionary. Updates require Anki to remain open.",
    }


def build_yomitan_zip(words: list[str], config: AddonConfig, revision: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("index.json", _json_text(build_index_data(config, revision)))
        for file_name, entries in build_term_meta_banks(words):
            archive.writestr(file_name, _json_text(entries))
    return output.getvalue()


def build_term_meta_banks(words: list[str]) -> list[tuple[str, list[list[object]]]]:
    entries = [[word, "freq", 1] for word in words]
    if not entries:
        return [("term_meta_bank_1.json", [])]

    banks: list[tuple[str, list[list[object]]]] = []
    for index, start in enumerate(range(0, len(entries), BANK_CHUNK_SIZE), start=1):
        file_name = f"term_meta_bank_{index}.json"
        banks.append((file_name, entries[start : start + BANK_CHUNK_SIZE]))
    return banks


def _json_bytes(value: object) -> bytes:
    return _json_text(value).encode("utf-8")


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
