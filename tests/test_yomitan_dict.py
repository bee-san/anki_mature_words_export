from __future__ import annotations

import json

from tests.yomitan_validation import validate_dictionary_archive, validate_index_data


def test_build_dictionary_artifacts_and_zip_contents(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    yomitan = addon_env.import_module("yomitan_dict")
    config = config_mod.AddonConfig(
        deck_name="Deck One", mature_days=30, http_port=9999
    )

    artifacts = yomitan.build_dictionary_artifacts(["Cat", "Dog"], config)
    validate_index_data(artifacts.index_data)
    index_data, entries, names = validate_dictionary_archive(artifacts.zip_bytes)

    assert artifacts.revision == yomitan.compute_revision(["Cat", "Dog"])
    assert json.loads(artifacts.index_bytes.decode("utf-8")) == artifacts.index_data
    assert index_data == artifacts.index_data
    assert names == ["index.json", "term_meta_bank_1.json"]
    assert entries == [["Cat", "freq", 1], ["Dog", "freq", 1]]
    assert (
        artifacts.index_data["indexUrl"]
        == "http://127.0.0.1:9999/bees-yomitan-known/index.json"
    )
    assert index_data["frequencyMode"] == "rank-based"


def test_build_term_meta_banks_empty_and_chunked(addon_env) -> None:
    addon_env.import_module("config")
    yomitan = addon_env.import_module("yomitan_dict")

    assert yomitan.build_term_meta_banks([]) == [("term_meta_bank_1.json", [])]

    words = [f"word-{index}" for index in range(50_001)]
    banks = yomitan.build_term_meta_banks(words)
    assert len(banks) == 2
    assert len(banks[0][1]) == 50_000
    assert [entry for _file_name, bank_entries in banks for entry in bank_entries] == [
        [word, "freq", 1] for word in sorted(words)
    ]


def test_empty_dictionary_archive_is_schema_valid(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    yomitan = addon_env.import_module("yomitan_dict")
    config = config_mod.AddonConfig(deck_name="Deck")

    artifacts = yomitan.build_dictionary_artifacts([], config)
    index_data, entries, names = validate_dictionary_archive(artifacts.zip_bytes)

    assert names == ["index.json", "term_meta_bank_1.json"]
    assert entries == []
    assert index_data["revision"] == artifacts.revision


def test_multi_bank_archive_is_schema_valid_and_complete(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    yomitan = addon_env.import_module("yomitan_dict")
    config = config_mod.AddonConfig(deck_name="Deck", http_port=9001)
    words = [f"word-{index}" for index in range(yomitan.BANK_CHUNK_SIZE + 3)]

    artifacts = yomitan.build_dictionary_artifacts(words, config)
    index_data, entries, names = validate_dictionary_archive(artifacts.zip_bytes)

    assert names == [
        "index.json",
        "term_meta_bank_1.json",
        "term_meta_bank_2.json",
    ]
    assert index_data["downloadUrl"] == (
        "http://127.0.0.1:9001/bees-yomitan-known/dictionary.zip"
    )
    assert entries == [[word, "freq", 1] for word in sorted(words)]


def test_dictionary_building_normalizes_unordered_duplicate_words(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    yomitan = addon_env.import_module("yomitan_dict")
    config = config_mod.AddonConfig(deck_name="Deck")

    words = ["Dog", "Cat", "Dog", "Ant"]
    artifacts = yomitan.build_dictionary_artifacts(words, config)
    index_data, entries, names = validate_dictionary_archive(artifacts.zip_bytes)

    assert names == ["index.json", "term_meta_bank_1.json"]
    assert entries == [["Ant", "freq", 1], ["Cat", "freq", 1], ["Dog", "freq", 1]]
    assert artifacts.revision == yomitan.compute_revision(["Dog", "Ant", "Cat"])
    assert index_data["revision"] == artifacts.revision
