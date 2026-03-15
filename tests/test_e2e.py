from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import socket
import time
from urllib.request import urlopen
from zipfile import ZipFile

from conftest import FakeCard, FakeCollection, FakeToolbar


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_collection(
    known_words_module,
    *,
    deck_name: str,
    field_name: str = "Expression",
    mature_days: int = 21,
    include_suspended: bool = False,
) -> FakeCollection:
    config = __import__(
        "anki_mature_words_export.config", fromlist=["AddonConfig"]
    ).AddonConfig(
        deck_name=deck_name,
        field_name=field_name,
        mature_days=mature_days,
        include_suspended=include_suspended,
    )
    mature_query = known_words_module.build_mature_query(config)
    return FakeCollection(
        search_results={mature_query: [1, 2]},
        cards={1: FakeCard(10), 2: FakeCard(11)},
        notes={
            10: {field_name: "<div>猫</div>\n犬"},
            11: {field_name: "鳥"},
        },
        deck_names=[deck_name],
    )


def _wait_for_url(url: str) -> bytes:
    deadline = time.monotonic() + 5.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                return response.read()
        except Exception as error:  # pragma: no cover - timing dependent
            last_error = error
            time.sleep(0.05)
    assert last_error is not None
    raise last_error


def _configure_live_server(
    server_module, addon_env, base_config: dict[str, object]
) -> int:
    for _ in range(10):
        port = _find_free_port()
        addon_env.state.config_data = {**base_config, "httpPort": port}
        server_module.server_manager.stop()
        if server_module.server_manager.apply_config(
            __import__(
                "anki_mature_words_export.config", fromlist=["AddonConfig"]
            ).AddonConfig(
                deck_name=str(base_config["deckName"]),
                mature_days=int(base_config["matureDays"]),
                field_name=str(base_config["fieldName"]),
                http_port=port,
                include_suspended=bool(base_config["includeSuspended"]),
                dedupe_strategy=str(base_config["dedupeStrategy"]),
                note_card_rule=str(base_config["noteCardRule"]),
            )
        ):
            return port
    raise AssertionError(
        "Could not start the live test server after multiple port attempts."
    )


def test_e2e_first_run_toolbar_click_exports_clipboard(addon_env, monkeypatch) -> None:
    package = addon_env.import_package()
    del package
    ui = addon_env.import_module("ui")
    known_words = addon_env.import_module("known_words")
    addon_env.state.mw.col = _build_collection(known_words, deck_name="Japanese")
    addon_env.state.config_data = {}

    apply_calls: list[object] = []
    monkeypatch.setattr(
        ui.server_manager,
        "apply_config",
        lambda config: apply_calls.append(config) or True,
    )

    def wizard_exec(self) -> int:
        self._deck_input.setCurrentText("Japanese")
        self._mature_input.setValue(21)
        self._field_input.setText("Expression")
        self._go_next()
        self._go_next()
        self._finish()
        return self.DialogCode.Accepted

    def dialog_exec(self) -> int:
        self._on_clipboard_clicked()
        return self.DialogCode.Accepted

    monkeypatch.setattr(ui.FirstRunWizard, "exec", wizard_exec)
    monkeypatch.setattr(ui.ExporterDialog, "exec", dialog_exec)

    toolbar = FakeToolbar()
    links: list[str] = []
    __import__("sys").modules["aqt"].gui_hooks.top_toolbar_did_init_links[0](
        links, toolbar
    )
    assert links == ["<a>Bee's Anki Exporter</a>"]

    toolbar.created_links[0][2]()

    assert ui.QApplication.clipboard().text == "犬\n猫\n鳥"
    assert addon_env.state.write_config_calls[-1][1]["deckName"] == "Japanese"
    assert apply_calls
    assert all(call.deck_name == "Japanese" for call in apply_calls)
    assert addon_env.state.tooltips[-1][0] == "Copied 3 words to clipboard."


def test_e2e_profile_start_generate_zip_and_serve_live_endpoints(
    addon_env,
    monkeypatch,
    tmp_path: Path,
) -> None:
    base_config = {
        "deckName": "Japanese",
        "matureDays": 21,
        "fieldName": "Expression",
        "includeSuspended": False,
        "dedupeStrategy": "case_sensitive_trim",
        "noteCardRule": "any_mature_card",
    }

    package = addon_env.import_package()
    del package
    ui = addon_env.import_module("ui")
    server = addon_env.import_module("server")
    known_words = addon_env.import_module("known_words")
    addon_env.state.mw.col = _build_collection(known_words, deck_name="Japanese")
    addon_env.state.save_file_path = str(tmp_path / "bee-known-words-japanese.zip")

    def dialog_exec(self) -> int:
        self._on_generate_clicked()
        return self.DialogCode.Accepted

    monkeypatch.setattr(ui.ExporterDialog, "exec", dialog_exec)

    try:
        port = _configure_live_server(server, addon_env, base_config)

        toolbar = FakeToolbar()
        links: list[str] = []
        __import__("sys").modules["aqt"].gui_hooks.top_toolbar_did_init_links[0](
            links, toolbar
        )
        toolbar.created_links[0][2]()

        saved_path = Path(addon_env.state.save_file_path)
        assert saved_path.exists()
        with ZipFile(saved_path) as saved_zip:
            assert sorted(saved_zip.namelist()) == [
                "index.json",
                "term_meta_bank_1.json",
            ]
            assert json.loads(
                saved_zip.read("term_meta_bank_1.json").decode("utf-8")
            ) == [
                ["犬", "freq", 1],
                ["猫", "freq", 1],
                ["鳥", "freq", 1],
            ]

        index_bytes = _wait_for_url(
            f"http://127.0.0.1:{port}/bees-yomitan-known/index.json"
        )
        index_data = json.loads(index_bytes.decode("utf-8"))
        assert (
            index_data["downloadUrl"]
            == f"http://127.0.0.1:{port}/bees-yomitan-known/dictionary.zip"
        )
        assert index_data["isUpdatable"] is True

        live_zip_bytes = _wait_for_url(
            f"http://127.0.0.1:{port}/bees-yomitan-known/dictionary.zip"
        )

        with (
            ZipFile(saved_path) as saved_zip,
            ZipFile(BytesIO(live_zip_bytes)) as live_zip,
        ):
            assert saved_zip.namelist() == live_zip.namelist()
            assert json.loads(
                saved_zip.read("index.json").decode("utf-8")
            ) == json.loads(live_zip.read("index.json").decode("utf-8"))
            assert json.loads(
                saved_zip.read("term_meta_bank_1.json").decode("utf-8")
            ) == json.loads(live_zip.read("term_meta_bank_1.json").decode("utf-8"))
            assert (
                json.loads(live_zip.read("index.json").decode("utf-8"))["revision"]
                == index_data["revision"]
            )

        server.server_manager.stop()
        assert server.server_manager._server is None
        assert server.server_manager._thread is None
    finally:
        server.server_manager.stop()
