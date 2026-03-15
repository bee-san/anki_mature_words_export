from __future__ import annotations

import pytest

from conftest import FakeCard, FakeCollection


def test_build_known_word_list_any_mature_card(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    known_words = addon_env.import_module("known_words")
    config = config_mod.AddonConfig(deck_name="Deck One", field_name="Expression")
    query = known_words.build_mature_query(config)
    col = FakeCollection(
        search_results={query: [1, 2, 3]},
        cards={1: FakeCard(10), 2: FakeCard(10), 3: FakeCard(11)},
        notes={
            10: {"Expression": "<b>Cat</b>\nDog\n Dog "},
            11: {},
        },
        deck_names=["Deck One"],
    )

    words, stats = known_words.build_known_word_list(col, config)
    assert words == ["Cat", "Dog"]
    assert stats["candidateMatureCardCount"] == 3
    assert stats["includedNoteCount"] == 2
    assert stats["missingFieldNoteCount"] == 1


def test_build_known_word_list_all_cards_mature(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    known_words = addon_env.import_module("known_words")
    config = config_mod.AddonConfig(
        deck_name="Deck One",
        field_name="Expression",
        note_card_rule="all_cards_mature",
        include_suspended=True,
    )
    mature_query = known_words.build_mature_query(config)
    scope_query = known_words.build_scope_query(config)
    col = FakeCollection(
        search_results={mature_query: [1, 2, 3], scope_query: [1, 2, 3, 4]},
        cards={
            1: FakeCard(10),
            2: FakeCard(10),
            3: FakeCard(11),
            4: FakeCard(11),
        },
        notes={
            10: {"Expression": "Alpha\nBeta"},
            11: {"Expression": "Gamma"},
        },
        deck_names=["Deck One"],
    )

    words, stats = known_words.build_known_word_list(col, config)
    assert words == ["Alpha", "Beta"]
    assert stats["scopedCardCount"] == 4
    assert stats["noteCardRule"] == "all_cards_mature"


def test_build_known_word_list_raises_when_field_missing_everywhere(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    known_words = addon_env.import_module("known_words")
    config = config_mod.AddonConfig(deck_name="Deck One", field_name="Expression")
    query = known_words.build_mature_query(config)
    col = FakeCollection(
        search_results={query: [1]},
        cards={1: FakeCard(99)},
        notes={99: {}},
        deck_names=["Deck One"],
    )

    with pytest.raises(known_words.KnownWordBuildError):
        known_words.build_known_word_list(col, config)


def test_query_helpers_and_note_helpers(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    known_words = addon_env.import_module("known_words")
    config = config_mod.AddonConfig(deck_name='Deck "One"', field_name="Expression")

    assert known_words.escape_search_term('Deck "One"') == 'Deck \\"One\\"'
    assert (
        known_words.build_scope_query(config) == 'deck:"Deck \\"One\\"" -is:suspended'
    )
    assert known_words._join_query_parts(["a", None, "b"]) == "a b"
