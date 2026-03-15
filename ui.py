from __future__ import annotations

from pathlib import Path
from typing import Any

from aqt import gui_hooks, mw
from aqt.operations import QueryOp
from aqt.qt import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
)
from aqt.toolbar import Toolbar
from aqt.utils import getSaveFile, showWarning, tooltip

from .config import (
    AddonConfig,
    ConfigValidationError,
    build_wizard_seed_config,
    config_summary,
    list_deck_names,
    load_config,
    save_config,
)
from .known_words import KnownWordBuildError, build_known_word_list
from .server import server_manager
from .yomitan_dict import DictionaryArtifacts, build_dictionary_artifacts

TOOLBAR_COMMAND = "bees_anki_exporter"


class FirstRunWizard(QDialog):
    def __init__(
        self, parent: Any, seed_config: AddonConfig, deck_names: list[str]
    ) -> None:
        super().__init__(parent)
        self._deck_names = deck_names
        self._seed_config = seed_config
        self._saved_config: AddonConfig | None = None
        self._steps = QStackedWidget(self)
        self._back_button = QPushButton("Back", self)
        self._next_button = QPushButton("Next", self)
        self._finish_button = QPushButton("Finish", self)

        self.setWindowTitle("Bee's Anki Exporter Setup")
        self.setModal(True)
        self.resize(460, 240)

        self._deck_input = QComboBox(self)
        self._deck_input.addItems(deck_names)
        if seed_config.deck_name in deck_names:
            self._deck_input.setCurrentText(seed_config.deck_name)

        self._mature_input = QSpinBox(self)
        self._mature_input.setRange(1, 36500)
        self._mature_input.setValue(seed_config.mature_days)

        self._field_input = QLineEdit(seed_config.field_name, self)

        self._steps.addWidget(
            self._build_step(
                "Choose a deck",
                "Select the deck whose mature cards define the known-word list.",
                self._deck_input,
            )
        )
        self._steps.addWidget(
            self._build_step(
                "Set the mature threshold",
                "Cards with an interval at or above this many days count as mature.",
                self._mature_input,
            )
        )
        self._steps.addWidget(
            self._build_step(
                "Choose the source field",
                "The selected field will be stripped of HTML and split on line breaks.",
                self._field_input,
            )
        )

        self._back_button.clicked.connect(self._go_back)
        self._next_button.clicked.connect(self._go_next)
        self._finish_button.clicked.connect(self._finish)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._back_button)
        button_row.addWidget(self._next_button)
        button_row.addWidget(self._finish_button)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Bee's Anki Exporter needs a few settings before it can generate the shared known-word list.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self._steps)
        layout.addLayout(button_row)

        self._update_buttons()

    @property
    def saved_config(self) -> AddonConfig | None:
        return self._saved_config

    def _build_step(self, title: str, description: str, control: Any) -> QFrame:
        frame = QFrame(self)
        layout = QVBoxLayout(frame)

        title_label = QLabel(title, frame)
        title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        description_label = QLabel(description, frame)
        description_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addSpacing(8)
        layout.addWidget(control)
        layout.addStretch(1)
        return frame

    def _go_back(self) -> None:
        self._steps.setCurrentIndex(max(0, self._steps.currentIndex() - 1))
        self._update_buttons()

    def _go_next(self) -> None:
        self._steps.setCurrentIndex(
            min(self._steps.count() - 1, self._steps.currentIndex() + 1)
        )
        self._update_buttons()

    def _finish(self) -> None:
        field_name = self._field_input.text().strip()
        if not self._deck_names:
            showWarning(
                "At least one deck is required before Bee's Anki Exporter can be configured.",
                parent=self,
            )
            return
        if not field_name:
            showWarning("Field name is required.", parent=self)
            return

        self._saved_config = AddonConfig(
            deck_name=self._deck_input.currentText().strip(),
            mature_days=int(self._mature_input.value()),
            field_name=field_name,
            http_port=self._seed_config.http_port,
            include_suspended=self._seed_config.include_suspended,
            dedupe_strategy=self._seed_config.dedupe_strategy,
            note_card_rule=self._seed_config.note_card_rule,
        )
        save_config(self._saved_config)
        server_manager.apply_config(self._saved_config)
        self.accept()

    def _update_buttons(self) -> None:
        current_index = self._steps.currentIndex()
        last_index = self._steps.count() - 1
        self._back_button.setEnabled(current_index > 0)
        self._next_button.setVisible(current_index < last_index)
        self._finish_button.setVisible(current_index == last_index)


class ExporterDialog(QDialog):
    def __init__(self, parent: Any, config: AddonConfig) -> None:
        super().__init__(parent)
        self._config = config
        self._clipboard_button = QPushButton("Export known words to Clipboard", self)
        self._generate_button = QPushButton(
            "Generate Auto-Updating Yomitan Frequency Dictionary",
            self,
        )
        self._footer = QLabel(config_summary(config), self)

        self.setWindowTitle("Bee's Anki Exporter")
        self.setModal(True)
        self.resize(520, 260)

        self._generate_button.setMinimumHeight(64)
        self._clipboard_button.setMinimumHeight(64)
        self._generate_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._clipboard_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        self._generate_button.clicked.connect(self._on_generate_clicked)
        self._clipboard_button.clicked.connect(self._on_clipboard_clicked)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Build the shared known-word list once, then export it either to Yomitan or directly to the clipboard.",
            self,
        )
        description.setWordWrap(True)
        self._footer.setWordWrap(True)
        self._footer.setStyleSheet("color: #666;")

        layout.addWidget(description)
        layout.addSpacing(12)
        layout.addWidget(self._generate_button)
        layout.addWidget(self._clipboard_button)
        layout.addStretch(1)
        layout.addWidget(self._footer)

    def _on_clipboard_clicked(self) -> None:
        self._set_busy(True)
        QueryOp(
            parent=self,
            op=lambda col: build_known_word_list(col, self._config),
            success=self._on_clipboard_ready,
        ).with_progress("Building known-word list...").failure(
            self._on_failure
        ).run_in_background()

    def _on_generate_clicked(self) -> None:
        self._set_busy(True)
        QueryOp(
            parent=self,
            op=lambda col: self._build_dictionary_export(col),
            success=self._on_dictionary_ready,
        ).with_progress("Building Yomitan dictionary...").failure(
            self._on_failure
        ).run_in_background()

    def _build_dictionary_export(
        self, col: Any
    ) -> tuple[list[str], dict[str, int | str], DictionaryArtifacts]:
        words, stats = build_known_word_list(col, self._config)
        artifacts = build_dictionary_artifacts(words, self._config)
        return words, stats, artifacts

    def _on_clipboard_ready(
        self, result: tuple[list[str], dict[str, int | str]]
    ) -> None:
        words, stats = result
        QApplication.clipboard().setText("\n".join(words))
        tooltip(f"Copied {len(words)} words to clipboard.")
        self._set_busy(False)
        self._update_footer(stats)

    def _on_dictionary_ready(
        self, result: tuple[list[str], dict[str, int | str], DictionaryArtifacts]
    ) -> None:
        words, stats, artifacts = result
        if not server_manager.apply_config(self._config):
            self._set_busy(False)
            self._update_footer(stats)
            return
        path = getSaveFile(
            parent=self,
            title="Save Bee's Yomitan Dictionary",
            dir_description="bee-yomitan-dictionary",
            key="bees_anki_exporter_dictionary",
            ext=".zip",
            fname=self._default_dictionary_name(),
        )
        if path:
            try:
                Path(path).write_bytes(artifacts.zip_bytes)
            except OSError as error:
                showWarning(
                    f"Could not save the dictionary ZIP.\n\n{error}", parent=self
                )
                self._set_busy(False)
                return
            tooltip(
                "Saved. Import this ZIP into Yomitan. For updates: use Yomitan's dictionary update button while Anki is open.",
                period=5000,
            )

        self._set_busy(False)
        self._update_footer(stats)

    def _default_dictionary_name(self) -> str:
        safe_deck = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in self._config.deck_name
        ).strip("_")
        if not safe_deck:
            safe_deck = "deck"
        return f"bee-known-words-{safe_deck}.zip"

    def _set_busy(self, busy: bool) -> None:
        self._generate_button.setEnabled(not busy)
        self._clipboard_button.setEnabled(not busy)

    def _update_footer(self, stats: dict[str, int | str]) -> None:
        self._footer.setText(
            f"{config_summary(self._config)} | Notes: {stats['includedNoteCount']} | Words: {stats['wordCount']}"
        )

    def _on_failure(self, error: Exception) -> None:
        self._set_busy(False)
        if isinstance(error, (ConfigValidationError, KnownWordBuildError)):
            showWarning(str(error), parent=self)
            return
        showWarning(f"Bee's Anki Exporter failed.\n\n{error}", parent=self)


def register_toolbar_link() -> None:
    _replace_hook_callback(gui_hooks.top_toolbar_did_init_links, _add_toolbar_link)


def open_main_dialog() -> None:
    if not getattr(mw, "col", None):
        showWarning("Open a profile and collection before using Bee's Anki Exporter.")
        return

    config = _ensure_configured()
    if config is None:
        return

    server_manager.apply_config(config)
    dialog = ExporterDialog(mw, config)
    dialog.exec()


def _add_toolbar_link(links: list[str], toolbar: Toolbar) -> None:
    links.append(
        toolbar.create_link(
            TOOLBAR_COMMAND,
            "Bee's Anki Exporter",
            open_main_dialog,
            tip="Open Bee's Anki Exporter",
        )
    )


def _ensure_configured() -> AddonConfig | None:
    try:
        return load_config(mw.col)
    except ConfigValidationError:
        deck_names = list_deck_names(mw.col)
        wizard = FirstRunWizard(mw, build_wizard_seed_config(mw.col), deck_names)
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return None
        return wizard.saved_config


def _replace_hook_callback(hook: list[Any], callback: Any) -> None:
    callback_key = _callback_key(callback)
    hook[:] = [existing for existing in hook if _callback_key(existing) != callback_key]
    hook.append(callback)


def _callback_key(callback: Any) -> tuple[str | None, str | None]:
    return (
        getattr(callback, "__module__", None),
        getattr(callback, "__qualname__", getattr(callback, "__name__", None)),
    )
