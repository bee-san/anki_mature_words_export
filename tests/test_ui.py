from __future__ import annotations

from pathlib import Path
import types

from conftest import FakeCard, FakeCollection, FakeToolbar


def build_word_collection(
    known_words, include_note_without_field: bool = False
) -> FakeCollection:
    query = 'deck:"Deck" -is:suspended prop:ivl>=21'
    notes = {10: {"Expression": "One\nTwo"}}
    cards = {1: FakeCard(10)}
    results = {query: [1]}
    if include_note_without_field:
        notes[11] = {}
        cards[2] = FakeCard(11)
        results[query] = [1, 2]
    return FakeCollection(
        search_results=results, cards=cards, notes=notes, deck_names=["Deck"]
    )


def test_first_run_wizard_validation_and_success(addon_env) -> None:
    ui = addon_env.import_module("ui")
    config_mod = addon_env.import_module("config")
    seed = config_mod.AddonConfig(
        deck_name="Deck", http_port=9999, include_suspended=True
    )
    wizard = ui.FirstRunWizard(None, seed, [])
    wizard._finish()
    assert "At least one deck is required" in addon_env.state.warnings[-1][0]

    wizard = ui.FirstRunWizard(None, seed, ["Deck"])
    wizard._field_input.setText(" ")
    wizard._finish()
    assert addon_env.state.warnings[-1][0] == "Field name is required."

    wizard = ui.FirstRunWizard(None, seed, ["Deck"])
    wizard._go_next()
    wizard._go_back()
    wizard._go_next()
    wizard._go_next()
    wizard._finish()
    assert wizard.saved_config.http_port == 9999
    assert addon_env.state.write_config_calls[-1][1]["includeSuspended"] is True


def test_exporter_dialog_clipboard_and_generate(addon_env, tmp_binary_file) -> None:
    config_mod = addon_env.import_module("config")
    known_words = addon_env.import_module("known_words")
    ui = addon_env.import_module("ui")
    addon_env.state.mw.col = build_word_collection(known_words)
    addon_env.state.save_file_path = tmp_binary_file
    config = config_mod.AddonConfig(deck_name="Deck")
    dialog = ui.ExporterDialog(None, config)

    dialog._on_clipboard_clicked()
    assert ui.QApplication.clipboard().text == "One\nTwo"
    assert addon_env.state.tooltips[-1][0] == "Copied 2 words to clipboard."

    dialog._on_generate_clicked()
    assert Path(tmp_binary_file).exists()
    assert "Saved. Import this ZIP into Yomitan." in addon_env.state.tooltips[-1][0]
    assert "Words: 2" in dialog._footer.text()


def test_exporter_dialog_misc_paths(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    ui = addon_env.import_module("ui")
    config = config_mod.AddonConfig(deck_name="Deck Name")
    dialog = ui.ExporterDialog(None, config)

    addon_env.state.save_file_path = None
    dialog._on_dictionary_ready(
        (
            ["One"],
            {"includedNoteCount": 1, "wordCount": 1},
            types.SimpleNamespace(zip_bytes=b"x"),
        )
    )
    assert dialog._default_dictionary_name() == "bee-known-words-Deck_Name.zip"
    weird_dialog = ui.ExporterDialog(None, config_mod.AddonConfig(deck_name="!!!"))
    assert weird_dialog._default_dictionary_name() == "bee-known-words-deck.zip"
    dialog._set_busy(True)
    assert dialog._generate_button.enabled is False
    dialog._set_busy(False)
    assert dialog._clipboard_button.enabled is True

    dialog._on_failure(config_mod.ConfigValidationError(["bad config"]))
    dialog._on_failure(RuntimeError("boom"))
    assert addon_env.state.warnings[-2][0] == "bad config"
    assert addon_env.state.warnings[-1][0] == "Bee's Anki Exporter failed.\n\nboom"


def test_exporter_dialog_generate_aborts_when_server_unavailable(
    addon_env, tmp_path, monkeypatch
) -> None:
    config_mod = addon_env.import_module("config")
    ui = addon_env.import_module("ui")
    config = config_mod.AddonConfig(deck_name="Deck")
    dialog = ui.ExporterDialog(None, config)
    target = tmp_path / "should-not-exist.zip"
    addon_env.state.save_file_path = str(target)

    monkeypatch.setattr(ui.server_manager, "apply_config", lambda cfg: False)
    dialog._on_dictionary_ready(
        (
            ["One"],
            {"includedNoteCount": 1, "wordCount": 1},
            types.SimpleNamespace(zip_bytes=b"x"),
        )
    )
    assert target.exists() is False
    assert addon_env.state.save_file_calls == []


def test_exporter_dialog_generate_save_error(
    addon_env, monkeypatch, tmp_binary_file
) -> None:
    config_mod = addon_env.import_module("config")
    ui = addon_env.import_module("ui")
    config = config_mod.AddonConfig(deck_name="Deck")
    dialog = ui.ExporterDialog(None, config)
    addon_env.state.save_file_path = tmp_binary_file

    monkeypatch.setattr(
        ui.Path,
        "write_bytes",
        lambda self, data: (_ for _ in ()).throw(OSError("disk full")),
    )
    dialog._on_dictionary_ready(
        (
            ["One"],
            {"includedNoteCount": 1, "wordCount": 1},
            types.SimpleNamespace(zip_bytes=b"x"),
        )
    )
    assert (
        addon_env.state.warnings[-1][0]
        == "Could not save the dictionary ZIP.\n\ndisk full"
    )


def test_register_toolbar_and_add_link(addon_env) -> None:
    ui = addon_env.import_module("ui")
    ui.register_toolbar_link()
    ui.register_toolbar_link()
    assert (
        len(__import__("sys").modules["aqt"].gui_hooks.top_toolbar_did_init_links) == 1
    )
    toolbar = FakeToolbar()
    links: list[str] = []
    ui._add_toolbar_link(links, toolbar)
    assert links == ["<a>Bee's Anki Exporter</a>"]
    assert toolbar.created_links[0][0] == "bees_anki_exporter"


def test_open_main_dialog_and_ensure_configured(addon_env, monkeypatch) -> None:
    ui = addon_env.import_module("ui")
    config_mod = addon_env.import_module("config")
    original_ensure_configured = ui._ensure_configured

    addon_env.state.mw.col = None
    ui.open_main_dialog()
    assert "Open a profile and collection" in addon_env.state.warnings[-1][0]

    addon_env.state.mw.col = FakeCollection(deck_names=["Deck"])
    monkeypatch.setattr(ui, "_ensure_configured", lambda: None)
    ui.open_main_dialog()

    opened: list[object] = []

    class FakeDialog:
        def __init__(self, parent, config) -> None:
            opened.append((parent, config))

        def exec(self) -> None:
            opened.append("exec")

    config = config_mod.AddonConfig(deck_name="Deck")
    monkeypatch.setattr(ui, "_ensure_configured", lambda: config)
    monkeypatch.setattr(ui, "ExporterDialog", FakeDialog)
    ui.open_main_dialog()
    assert opened[-1] == "exec"

    monkeypatch.setattr(ui, "load_config", lambda col: config)
    assert original_ensure_configured() == config

    class AcceptWizard:
        def __init__(self, parent, seed_config, deck_names) -> None:
            self.saved_config = config

        def exec(self) -> int:
            return ui.QDialog.DialogCode.Accepted

    class RejectWizard(AcceptWizard):
        def exec(self) -> int:
            return ui.QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        ui,
        "load_config",
        lambda col: (_ for _ in ()).throw(config_mod.ConfigValidationError(["bad"])),
    )
    monkeypatch.setattr(ui, "FirstRunWizard", AcceptWizard)
    assert original_ensure_configured() == config
    monkeypatch.setattr(ui, "FirstRunWizard", RejectWizard)
    assert original_ensure_configured() is None
