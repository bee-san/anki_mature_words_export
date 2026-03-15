from __future__ import annotations

import types
import sys

import pytest

from conftest import FakeCollection


class FakeThread:
    def __init__(self, target=None, name=None, daemon=None) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.joined = False
        self.alive = True

    def start(self) -> None:
        self.started = True

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout=None) -> None:
        self.joined = True


class FakeHTTPServer:
    def __init__(self, manager, port) -> None:
        self.manager = manager
        self.server_address = ("127.0.0.1", port)
        self.shutdown_called = False
        self.closed = False

    def serve_forever(self) -> None:  # pragma: no cover - target only
        return

    def shutdown(self) -> None:
        self.shutdown_called = True

    def server_close(self) -> None:
        self.closed = True


def make_handler(server_mod, manager) -> tuple[object, dict[str, object]]:
    handler = server_mod.BeeRequestHandler.__new__(server_mod.BeeRequestHandler)
    recorded: dict[str, object] = {"headers": [], "errors": []}
    handler.server = types.SimpleNamespace(manager=manager)
    handler.wfile = __import__("io").BytesIO()
    handler.send_response = lambda code: recorded.setdefault("response", code)
    handler.send_header = lambda key, value: recorded["headers"].append((key, value))
    handler.end_headers = lambda: recorded.setdefault("ended", True)
    handler.send_error = lambda code, message: recorded["errors"].append(
        (code, message)
    )
    return handler, recorded


def test_register_server_hooks_and_init_registration(addon_env) -> None:
    addon_env.import_package()
    assert len(sys.modules["aqt"].gui_hooks.top_toolbar_did_init_links) == 1
    assert len(sys.modules["aqt"].gui_hooks.profile_did_open) == 1
    assert len(sys.modules["aqt"].gui_hooks.profile_will_close) == 1

    server = addon_env.import_module("server")
    manager = server.LocalUpdateServerManager()
    manager.register_hooks()
    manager.register_hooks()
    assert (
        manager.start_from_current_config
        in sys.modules["aqt"].gui_hooks.profile_did_open
    )
    assert (
        sys.modules["aqt"].gui_hooks.profile_did_open.count(
            manager.start_from_current_config
        )
        == 1
    )
    assert sys.modules["aqt"].gui_hooks.profile_will_close.count(manager.stop) == 1


def test_register_server_hooks_replaces_stale_reload_callbacks(addon_env) -> None:
    first_server = addon_env.import_module("server")
    first_server.register_server_hooks()
    first_open = sys.modules["aqt"].gui_hooks.profile_did_open[0]
    first_close = sys.modules["aqt"].gui_hooks.profile_will_close[0]

    for name in list(sys.modules):
        if name == "anki_mature_words_export" or name.startswith(
            "anki_mature_words_export."
        ):
            sys.modules.pop(name, None)

    second_server = addon_env.import_module("server")
    second_server.register_server_hooks()
    assert sys.modules["aqt"].gui_hooks.profile_did_open == [
        second_server.server_manager.start_from_current_config
    ]
    assert sys.modules["aqt"].gui_hooks.profile_will_close == [
        second_server.server_manager.stop
    ]
    assert sys.modules["aqt"].gui_hooks.profile_did_open[0] is not first_open
    assert sys.modules["aqt"].gui_hooks.profile_will_close[0] is not first_close


def test_server_callback_key_handles_plain_functions(addon_env) -> None:
    server = addon_env.import_module("server")

    def plain_callback() -> None:
        return

    assert server._callback_key(plain_callback) == (
        __name__,
        "test_server_callback_key_handles_plain_functions.<locals>.plain_callback",
        None,
    )


def test_start_from_current_config_branches(addon_env, monkeypatch) -> None:
    server = addon_env.import_module("server")
    manager = server.LocalUpdateServerManager()
    addon_env.state.mw.col = None
    manager.start_from_current_config()

    addon_env.state.config_data = {"deckName": ""}
    addon_env.state.mw.col = FakeCollection(deck_names=["Deck"])
    stop_calls: list[str] = []
    monkeypatch.setattr(manager, "stop", lambda *args: stop_calls.append("stopped"))
    manager.start_from_current_config()
    assert stop_calls == ["stopped"]

    applied: list[object] = []
    addon_env.state.config_data = {
        "deckName": "Deck",
        "matureDays": 21,
        "fieldName": "Expression",
        "httpPort": 8766,
        "includeSuspended": False,
        "dedupeStrategy": "case_sensitive_trim",
        "noteCardRule": "any_mature_card",
    }
    monkeypatch.setattr(manager, "apply_config", lambda config: applied.append(config))
    manager.start_from_current_config()
    assert applied and applied[0].deck_name == "Deck"


def test_apply_config_success_error_and_noop(addon_env, monkeypatch) -> None:
    config_mod = addon_env.import_module("config")
    server = addon_env.import_module("server")
    config = config_mod.AddonConfig(deck_name="Deck")
    manager = server.LocalUpdateServerManager()

    monkeypatch.setattr(server, "BeeHTTPServer", FakeHTTPServer)
    monkeypatch.setattr(server, "Thread", FakeThread)
    assert manager.apply_config(config) is True
    assert isinstance(manager._server, FakeHTTPServer)
    assert manager._thread.started is True

    previous_server = manager._server
    previous_thread = manager._thread
    assert manager.apply_config(config) is True
    assert manager._server is previous_server
    assert manager._thread is previous_thread

    manager._thread.alive = False
    assert manager.apply_config(config) is True
    assert manager._server is not previous_server
    assert manager._thread is not previous_thread

    monkeypatch.setattr(
        server,
        "BeeHTTPServer",
        lambda manager_obj, port: (_ for _ in ()).throw(OSError("busy")),
    )
    manager.stop()
    assert manager.apply_config(config) is False
    assert (
        "could not start the local update server"
        in addon_env.state.warnings[-1][0].lower()
    )


def test_stop_and_cached_artifact_helpers(addon_env, monkeypatch) -> None:
    config_mod = addon_env.import_module("config")
    server = addon_env.import_module("server")
    manager = server.LocalUpdateServerManager()
    config = config_mod.AddonConfig(deck_name="Deck")

    fake_server = FakeHTTPServer(manager, 8766)
    fake_thread = FakeThread()
    manager._server = fake_server
    manager._thread = fake_thread
    manager._config = config
    manager.stop()
    assert fake_server.shutdown_called is True
    assert fake_server.closed is True
    assert fake_thread.joined is True

    with pytest.raises(RuntimeError):
        manager._get_cached_artifacts()

    artifacts = types.SimpleNamespace(index_bytes=b"index", zip_bytes=b"zip")
    cache = server.CachedArtifacts(built_at=1.0, artifacts=artifacts)
    manager._config = config
    manager._cache = cache
    monkeypatch.setattr(server.time, "monotonic", lambda: 2.0)
    assert manager.get_index_bytes() == b"index"
    assert manager.get_zip_bytes() == b"zip"

    manager._cache = None
    monkeypatch.setattr(manager, "_run_collection_task_sync", lambda task: artifacts)
    assert manager._get_cached_artifacts().artifacts.zip_bytes == b"zip"


def test_build_artifacts_and_run_collection_task_sync(addon_env) -> None:
    config_mod = addon_env.import_module("config")
    server = addon_env.import_module("server")
    manager = server.LocalUpdateServerManager()
    config = config_mod.AddonConfig(deck_name="Deck")

    col = FakeCollection(deck_names=["Deck"])
    addon_env.state.mw.col = col
    original_known_words = server.build_known_word_list
    original_build_dictionary = server.build_dictionary_artifacts
    server.build_known_word_list = lambda passed_col, passed_config: (
        ["Word"],
        {"count": 1},
    )
    server.build_dictionary_artifacts = lambda words, passed_config: "artifacts"
    try:
        assert manager._build_artifacts(col, config) == "artifacts"
        assert manager._run_collection_task_sync(lambda passed_col: passed_col) is col
        with pytest.raises(ValueError):
            manager._run_collection_task_sync(
                lambda passed_col: (_ for _ in ()).throw(ValueError("boom"))
            )
        addon_env.state.mw.col = None
        with pytest.raises(RuntimeError, match="No collection is currently open."):
            manager._run_collection_task_sync(lambda passed_col: passed_col)
    finally:
        server.build_known_word_list = original_known_words
        server.build_dictionary_artifacts = original_build_dictionary


def test_request_handler_success_and_error_paths(addon_env) -> None:
    server = addon_env.import_module("server")
    manager = types.SimpleNamespace(
        get_index_bytes=lambda: b"{}",
        get_zip_bytes=lambda: b"zip",
    )
    handler, recorded = make_handler(server, manager)
    handler.path = server.INDEX_PATH
    handler.do_GET()
    assert recorded["response"] == 200
    assert handler.wfile.getvalue() == b"{}"
    handler.log_message("ignored")

    handler, recorded = make_handler(server, manager)
    handler.path = server.DOWNLOAD_PATH
    handler.do_GET()
    assert handler.wfile.getvalue() == b"zip"

    handler, recorded = make_handler(server, manager)
    handler.path = "/missing"
    handler.do_GET()
    assert recorded["errors"] == [(404, "Not found")]

    error_manager = types.SimpleNamespace(
        get_index_bytes=lambda: (_ for _ in ()).throw(RuntimeError("broken")),
        get_zip_bytes=lambda: b"",
    )
    handler, recorded = make_handler(server, error_manager)
    handler._serve_payload("application/json", error_manager.get_index_bytes)
    assert recorded["response"] == 500
    assert handler.wfile.getvalue() == b"broken"

    generic_error_manager = types.SimpleNamespace(
        get_index_bytes=lambda: (_ for _ in ()).throw(ValueError("unexpected")),
        get_zip_bytes=lambda: b"",
    )
    handler, recorded = make_handler(server, generic_error_manager)
    handler._serve_payload("application/json", generic_error_manager.get_index_bytes)
    assert recorded["response"] == 500
    assert handler.wfile.getvalue() == b"unexpected"
