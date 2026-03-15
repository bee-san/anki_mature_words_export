from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from aqt import mw

DEFAULT_MATURE_DAYS = 21
DEFAULT_FIELD_NAME = "Expression"
DEFAULT_HTTP_PORT = 8766
DEFAULT_INCLUDE_SUSPENDED = False
DEFAULT_DEDUPE_STRATEGY = "case_sensitive_trim"
DEFAULT_NOTE_CARD_RULE = "any_mature_card"

VALID_DEDUPE_STRATEGIES = {DEFAULT_DEDUPE_STRATEGY}
VALID_NOTE_CARD_RULES = {"any_mature_card", "all_cards_mature"}


class ConfigValidationError(ValueError):
    def __init__(self, messages: list[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = messages


@dataclass(frozen=True)
class AddonConfig:
    deck_name: str
    mature_days: int = DEFAULT_MATURE_DAYS
    field_name: str = DEFAULT_FIELD_NAME
    http_port: int = DEFAULT_HTTP_PORT
    include_suspended: bool = DEFAULT_INCLUDE_SUSPENDED
    dedupe_strategy: str = DEFAULT_DEDUPE_STRATEGY
    note_card_rule: str = DEFAULT_NOTE_CARD_RULE

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {
            "deckName": data["deck_name"],
            "matureDays": data["mature_days"],
            "fieldName": data["field_name"],
            "httpPort": data["http_port"],
            "includeSuspended": data["include_suspended"],
            "dedupeStrategy": data["dedupe_strategy"],
            "noteCardRule": data["note_card_rule"],
        }


def addon_module_name() -> str:
    return __name__.split(".")[0]


def load_raw_config() -> dict[str, Any]:
    raw = mw.addonManager.getConfig(addon_module_name())
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def save_config(config: AddonConfig) -> None:
    mw.addonManager.writeConfig(addon_module_name(), config.to_dict())


def config_summary(config: AddonConfig) -> str:
    return (
        f"Deck: {config.deck_name} | "
        f"Mature: >={config.mature_days}d | "
        f"Field: {config.field_name}"
    )


def list_deck_names(col: Any) -> list[str]:
    names = [entry.name for entry in col.decks.all_names_and_ids()]
    return sorted(names, key=str.casefold)


def load_config(col: Any | None = None) -> AddonConfig:
    raw = load_raw_config()
    config = parse_config(raw)
    if col is not None and config.deck_name not in set(list_deck_names(col)):
        raise ConfigValidationError(
            [f'Deck "{config.deck_name}" does not exist in the current collection.']
        )
    return config


def parse_config(raw: Mapping[str, Any] | None) -> AddonConfig:
    raw = raw or {}
    errors: list[str] = []

    deck_name = _clean_string(raw.get("deckName"))
    if not deck_name:
        errors.append("deckName must be a non-empty string.")

    field_name = _clean_string(raw.get("fieldName"), DEFAULT_FIELD_NAME)
    if not field_name:
        errors.append("fieldName must be a non-empty string.")

    mature_days = _coerce_positive_int(
        raw.get("matureDays"), DEFAULT_MATURE_DAYS, "matureDays", errors
    )
    http_port = _coerce_positive_int(
        raw.get("httpPort"), DEFAULT_HTTP_PORT, "httpPort", errors
    )
    if http_port is not None and http_port > 65535:
        errors.append("httpPort must be between 1 and 65535.")

    include_suspended = _coerce_bool(
        raw.get("includeSuspended"),
        DEFAULT_INCLUDE_SUSPENDED,
        "includeSuspended",
        errors,
    )

    dedupe_strategy = _clean_string(raw.get("dedupeStrategy"), DEFAULT_DEDUPE_STRATEGY)
    if dedupe_strategy not in VALID_DEDUPE_STRATEGIES:
        errors.append(
            f"dedupeStrategy must be one of: {', '.join(sorted(VALID_DEDUPE_STRATEGIES))}."
        )

    note_card_rule = _clean_string(raw.get("noteCardRule"), DEFAULT_NOTE_CARD_RULE)
    if note_card_rule not in VALID_NOTE_CARD_RULES:
        errors.append(
            f"noteCardRule must be one of: {', '.join(sorted(VALID_NOTE_CARD_RULES))}."
        )

    if errors:
        raise ConfigValidationError(errors)

    return AddonConfig(
        deck_name=deck_name,
        mature_days=mature_days,
        field_name=field_name,
        http_port=http_port,
        include_suspended=include_suspended,
        dedupe_strategy=dedupe_strategy,
        note_card_rule=note_card_rule,
    )


def build_wizard_seed_config(col: Any) -> AddonConfig:
    raw = load_raw_config()
    deck_names = list_deck_names(col)
    default_deck = deck_names[0] if deck_names else ""
    deck_name = _clean_string(raw.get("deckName"), default_deck)
    if deck_name not in deck_names:
        deck_name = default_deck

    mature_days_errors: list[str] = []
    mature_days = _coerce_positive_int(
        raw.get("matureDays"), DEFAULT_MATURE_DAYS, "matureDays", mature_days_errors
    )
    field_name = _clean_string(raw.get("fieldName"), DEFAULT_FIELD_NAME)
    http_port_errors: list[str] = []
    http_port = _coerce_positive_int(
        raw.get("httpPort"), DEFAULT_HTTP_PORT, "httpPort", http_port_errors
    )
    if http_port > 65535:
        http_port = DEFAULT_HTTP_PORT
    include_suspended_errors: list[str] = []
    include_suspended = _coerce_bool(
        raw.get("includeSuspended"),
        DEFAULT_INCLUDE_SUSPENDED,
        "includeSuspended",
        include_suspended_errors,
    )
    dedupe_strategy = _clean_string(raw.get("dedupeStrategy"), DEFAULT_DEDUPE_STRATEGY)
    if dedupe_strategy not in VALID_DEDUPE_STRATEGIES:
        dedupe_strategy = DEFAULT_DEDUPE_STRATEGY
    note_card_rule = _clean_string(raw.get("noteCardRule"), DEFAULT_NOTE_CARD_RULE)
    if note_card_rule not in VALID_NOTE_CARD_RULES:
        note_card_rule = DEFAULT_NOTE_CARD_RULE

    return AddonConfig(
        deck_name=deck_name,
        mature_days=mature_days if not mature_days_errors else DEFAULT_MATURE_DAYS,
        field_name=field_name or DEFAULT_FIELD_NAME,
        http_port=http_port,
        include_suspended=include_suspended
        if not include_suspended_errors
        else DEFAULT_INCLUDE_SUSPENDED,
        dedupe_strategy=dedupe_strategy,
        note_card_rule=note_card_rule,
    )


def _clean_string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coerce_positive_int(
    value: Any,
    default: int,
    field_name: str,
    errors: list[str],
) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors.append(f"{field_name} must be a positive integer.")
        return default
    if parsed <= 0:
        errors.append(f"{field_name} must be a positive integer.")
        return default
    return parsed


def _coerce_bool(
    value: Any,
    default: bool,
    field_name: str,
    errors: list[str],
) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    errors.append(f"{field_name} must be a boolean.")
    return default
