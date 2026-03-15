from __future__ import annotations

import pytest

from conftest import FakeCollection


def test_config_load_save_and_summary(addon_env) -> None:
    config = addon_env.import_module("config")
    addon_env.state.config_data = {
        "deckName": "Deck A",
        "matureDays": 30,
        "fieldName": "Expression",
        "httpPort": 9000,
        "includeSuspended": True,
        "dedupeStrategy": "case_sensitive_trim",
        "noteCardRule": "all_cards_mature",
    }
    addon_env.state.mw.col = FakeCollection(deck_names=["Deck A"])

    parsed = config.load_config(addon_env.state.mw.col)
    assert parsed.deck_name == "Deck A"
    assert parsed.include_suspended is True
    assert (
        config.config_summary(parsed)
        == "Deck: Deck A | Mature: >=30d | Field: Expression"
    )

    config.save_config(parsed)
    assert addon_env.state.write_config_calls[-1][1]["httpPort"] == 9000


def test_load_raw_config_returns_empty_dict_when_missing(addon_env) -> None:
    config = addon_env.import_module("config")
    addon_env.state.config_data = None

    assert config.load_raw_config() == {}


def test_load_config_rejects_missing_deck(addon_env) -> None:
    config = addon_env.import_module("config")
    addon_env.state.config_data = {
        "deckName": "Missing",
        "matureDays": 21,
        "fieldName": "Expression",
        "httpPort": 8766,
        "includeSuspended": False,
        "dedupeStrategy": "case_sensitive_trim",
        "noteCardRule": "any_mature_card",
    }

    with pytest.raises(config.ConfigValidationError) as error:
        config.load_config(FakeCollection(deck_names=["Present"]))

    assert 'Deck "Missing" does not exist' in str(error.value)


def test_parse_config_validation_errors(addon_env) -> None:
    config = addon_env.import_module("config")

    with pytest.raises(config.ConfigValidationError) as error:
        config.parse_config(
            {
                "deckName": "",
                "fieldName": "",
                "matureDays": 0,
                "httpPort": 70000,
                "includeSuspended": "maybe",
                "dedupeStrategy": "bad",
                "noteCardRule": "bad",
            }
        )

    message = str(error.value)
    assert "deckName must be a non-empty string." in message
    assert "fieldName must be a non-empty string." in message
    assert "matureDays must be a positive integer." in message
    assert "httpPort must be between 1 and 65535." in message
    assert "includeSuspended must be a boolean." in message


def test_build_wizard_seed_config_preserves_valid_advanced_settings(addon_env) -> None:
    config = addon_env.import_module("config")
    addon_env.state.config_data = {
        "deckName": "Default",
        "matureDays": "45",
        "fieldName": "Front",
        "httpPort": "9999",
        "includeSuspended": "true",
        "dedupeStrategy": "case_sensitive_trim",
        "noteCardRule": "all_cards_mature",
    }

    seed = config.build_wizard_seed_config(FakeCollection(deck_names=["Default"]))
    assert seed.mature_days == 45
    assert seed.http_port == 9999
    assert seed.include_suspended is True
    assert seed.note_card_rule == "all_cards_mature"


def test_build_wizard_seed_config_falls_back_for_invalid_advanced_settings(
    addon_env,
) -> None:
    config = addon_env.import_module("config")
    addon_env.state.config_data = {
        "deckName": "Ghost",
        "matureDays": "bad",
        "fieldName": " ",
        "httpPort": "70000",
        "includeSuspended": "bad",
        "dedupeStrategy": "bad",
        "noteCardRule": "bad",
    }

    seed = config.build_wizard_seed_config(FakeCollection(deck_names=["Deck 1"]))
    assert seed.deck_name == "Deck 1"
    assert seed.mature_days == 21
    assert seed.field_name == "Expression"
    assert seed.http_port == 8766
    assert seed.include_suspended is False
    assert seed.dedupe_strategy == "case_sensitive_trim"
    assert seed.note_card_rule == "any_mature_card"


def test_private_config_helpers_cover_edge_cases(addon_env) -> None:
    config = addon_env.import_module("config")
    errors: list[str] = []

    assert config.addon_module_name() == "anki_mature_words_export"
    assert config._clean_string(None, "fallback") == "fallback"
    assert config._clean_string(12) == "12"
    assert config._coerce_positive_int(None, 21, "field", errors) == 21
    assert config._coerce_positive_int("5", 21, "field", errors) == 5
    assert config._coerce_positive_int("bad", 21, "field", errors) == 21
    assert config._coerce_bool(True, False, "flag", errors) is True
    assert config._coerce_bool("false", True, "flag", errors) is False
    assert config._coerce_bool("yes", False, "flag", errors) is True
    assert config._coerce_bool("bad", False, "flag", errors) is False
    assert "field must be a positive integer." in errors
    assert "flag must be a boolean." in errors
