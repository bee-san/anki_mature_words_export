from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from jsonschema import Draft7Validator

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "yomitan"
INDEX_SCHEMA = json.loads(
    (FIXTURES_DIR / "dictionary-index-schema.json").read_text(encoding="utf-8")
)
TERM_META_BANK_V3_SCHEMA = json.loads(
    (FIXTURES_DIR / "dictionary-term-meta-bank-v3-schema.json").read_text(
        encoding="utf-8"
    )
)


def validate_index_data(index_data: dict[str, object]) -> None:
    Draft7Validator(INDEX_SCHEMA).validate(index_data)


def validate_term_meta_bank(bank_data: list[list[object]]) -> None:
    Draft7Validator(TERM_META_BANK_V3_SCHEMA).validate(bank_data)


def validate_dictionary_archive(
    zip_bytes: bytes,
) -> tuple[dict[str, object], list[list[object]], list[str]]:
    with ZipFile(BytesIO(zip_bytes)) as archive:
        names = sorted(archive.namelist())
        assert "index.json" in names
        assert all("/" not in name for name in names)

        bank_names = sorted(
            name
            for name in names
            if name.startswith("term_meta_bank_") and name.endswith(".json")
        )
        assert bank_names
        assert bank_names == [
            f"term_meta_bank_{index}.json" for index in range(1, len(bank_names) + 1)
        ]
        assert names == ["index.json", *bank_names]

        index_data = json.loads(archive.read("index.json").decode("utf-8"))
        validate_index_data(index_data)

        entries: list[list[object]] = []
        for bank_name in bank_names:
            bank_data = json.loads(archive.read(bank_name).decode("utf-8"))
            validate_term_meta_bank(bank_data)
            entries.extend(bank_data)

        return index_data, entries, names
