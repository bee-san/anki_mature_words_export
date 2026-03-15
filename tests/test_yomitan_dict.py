from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile


def test_build_dictionary_artifacts_and_zip_contents(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    yomitan = addon_env.import_module("yomitan_dict")
    config = config_mod.AddonConfig(
        deck_name="Deck One", mature_days=30, http_port=9999
    )

    artifacts = yomitan.build_dictionary_artifacts(["Cat", "Dog"], config)

    assert artifacts.revision == yomitan.compute_revision(["Cat", "Dog"])
    assert (
        artifacts.index_data["indexUrl"]
        == "http://127.0.0.1:9999/bees-yomitan-known/index.json"
    )
    with ZipFile(BytesIO(artifacts.zip_bytes)) as archive:
        assert sorted(archive.namelist()) == ["index.json", "term_meta_bank_1.json"]
        assert (
            json.loads(archive.read("index.json").decode("utf-8"))["frequencyMode"]
            == "rank-based"
        )
        assert json.loads(archive.read("term_meta_bank_1.json").decode("utf-8")) == [
            ["Cat", "freq", 1],
            ["Dog", "freq", 1],
        ]


def test_build_term_meta_banks_empty_and_chunked(addon_env) -> None:
    addon_env.import_module("config")
    yomitan = addon_env.import_module("yomitan_dict")

    assert yomitan.build_term_meta_banks([]) == [("term_meta_bank_1.json", [])]

    words = [f"word-{index}" for index in range(50_001)]
    banks = yomitan.build_term_meta_banks(words)
    assert len(banks) == 2
    assert len(banks[0][1]) == 50_000
    assert banks[1][1] == [["word-50000", "freq", 1]]
