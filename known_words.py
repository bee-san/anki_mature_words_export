from __future__ import annotations

from collections import Counter
from typing import Any

from anki.utils import strip_html

from .config import AddonConfig


class KnownWordBuildError(RuntimeError):
    pass


def build_known_word_list(
    col: Any, config: AddonConfig
) -> tuple[list[str], dict[str, int | str]]:
    mature_query = build_mature_query(config)
    mature_card_ids = list(col.find_cards(mature_query))

    if config.note_card_rule == "all_cards_mature":
        scope_query = build_scope_query(config)
        scope_card_ids = list(col.find_cards(scope_query))
        note_ids = _all_mature_note_ids(col, scope_card_ids, mature_card_ids)
        scoped_card_count = len(scope_card_ids)
    else:
        note_ids = sorted(_note_ids_for_cards(col, mature_card_ids))
        scoped_card_count = len(mature_card_ids)

    words, missing_field_notes, extracted_notes = _extract_words_from_notes(
        col, note_ids, config.field_name
    )

    if note_ids and extracted_notes == 0:
        raise KnownWordBuildError(
            f"Field '{config.field_name}' was not found on any included notes."
        )

    stats: dict[str, int | str] = {
        "deckName": config.deck_name,
        "matureDays": config.mature_days,
        "fieldName": config.field_name,
        "candidateMatureCardCount": len(mature_card_ids),
        "scopedCardCount": scoped_card_count,
        "includedNoteCount": len(note_ids),
        "missingFieldNoteCount": missing_field_notes,
        "wordCount": len(words),
        "noteCardRule": config.note_card_rule,
    }
    return words, stats


def build_scope_query(config: AddonConfig) -> str:
    return _join_query_parts(
        [
            f'deck:"{escape_search_term(config.deck_name)}"',
            None if config.include_suspended else "-is:suspended",
        ]
    )


def build_mature_query(config: AddonConfig) -> str:
    return _join_query_parts(
        [
            build_scope_query(config),
            f"prop:ivl>={config.mature_days}",
        ]
    )


def escape_search_term(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _all_mature_note_ids(
    col: Any, scope_card_ids: list[int], mature_card_ids: list[int]
) -> list[int]:
    total_counts = _note_id_counter(col, scope_card_ids)
    mature_counts = _note_id_counter(col, mature_card_ids)
    matching = [
        note_id
        for note_id, total in total_counts.items()
        if total > 0 and mature_counts.get(note_id, 0) == total
    ]
    return sorted(matching)


def _note_id_counter(col: Any, card_ids: list[int]) -> Counter[int]:
    counter: Counter[int] = Counter()
    for card_id in card_ids:
        counter[int(col.get_card(card_id).nid)] += 1
    return counter


def _note_ids_for_cards(col: Any, card_ids: list[int]) -> set[int]:
    return {int(col.get_card(card_id).nid) for card_id in card_ids}


def _extract_words_from_notes(
    col: Any, note_ids: list[int], field_name: str
) -> tuple[list[str], int, int]:
    seen: set[str] = set()
    words: list[str] = []
    missing_field_notes = 0
    extracted_notes = 0

    for note_id in note_ids:
        note = col.get_note(note_id)
        try:
            field_value = note[field_name]
        except KeyError:
            missing_field_notes += 1
            continue

        extracted_notes += 1
        cleaned_text = strip_html(field_value)
        for candidate in cleaned_text.splitlines():
            normalized = candidate.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            words.append(normalized)

    words.sort()
    return words, missing_field_notes, extracted_notes


def _join_query_parts(parts: list[str | None]) -> str:
    return " ".join(part for part in parts if part)
