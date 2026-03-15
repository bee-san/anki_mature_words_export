from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
import time
from typing import Any, Callable, TypeVar
from urllib.parse import urlparse

from aqt import gui_hooks, mw
from aqt.utils import showWarning

from .config import AddonConfig, ConfigValidationError, load_config
from .known_words import KnownWordBuildError, build_known_word_list
from .yomitan_dict import (
    DOWNLOAD_PATH,
    INDEX_PATH,
    DictionaryArtifacts,
    build_dictionary_artifacts,
)

CACHE_TTL_SECONDS = 120

T = TypeVar("T")


@dataclass(frozen=True)
class CachedArtifacts:
    built_at: float
    artifacts: DictionaryArtifacts


class BeeRequestHandler(BaseHTTPRequestHandler):
    server: "BeeHTTPServer"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == INDEX_PATH:
            self._serve_payload(
                "application/json; charset=utf-8",
                lambda: self.server.manager.get_index_bytes(),
            )
            return
        if parsed.path == DOWNLOAD_PATH:
            self._serve_payload(
                "application/zip", lambda: self.server.manager.get_zip_bytes()
            )
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _serve_payload(
        self, content_type: str, payload_factory: Callable[[], bytes]
    ) -> None:
        try:
            payload = payload_factory()
        except Exception as error:
            message = str(error).encode("utf-8")
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


class BeeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, manager: "LocalUpdateServerManager", port: int) -> None:
        self.manager = manager
        super().__init__(("127.0.0.1", port), BeeRequestHandler)


class LocalUpdateServerManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._cache: CachedArtifacts | None = None
        self._config: AddonConfig | None = None
        self._server: BeeHTTPServer | None = None
        self._thread: Thread | None = None

    def register_hooks(self) -> None:
        if self.start_from_current_config not in gui_hooks.profile_did_open:
            gui_hooks.profile_did_open.append(self.start_from_current_config)
        if (
            hasattr(gui_hooks, "profile_will_close")
            and self.stop not in gui_hooks.profile_will_close
        ):
            gui_hooks.profile_will_close.append(self.stop)

    def start_from_current_config(self, *args: Any) -> None:
        if not getattr(mw, "col", None):
            return
        try:
            config = load_config(mw.col)
        except ConfigValidationError:
            self.stop()
            return
        self.apply_config(config)

    def apply_config(self, config: AddonConfig) -> bool:
        with self._lock:
            existing_port = self._server.server_address[1] if self._server else None
            thread_is_alive = self._thread is not None and self._thread.is_alive()
            if (
                self._server
                and thread_is_alive
                and existing_port == config.http_port
                and self._config == config
            ):
                return True

        self.stop()
        try:
            server = BeeHTTPServer(self, config.http_port)
        except OSError as error:
            showWarning(
                f"Bee's Anki Exporter could not start the local update server on port {config.http_port}.\n\n{error}"
            )
            return False

        thread = Thread(
            target=server.serve_forever,
            name="BeesAnkiExporterServer",
            daemon=True,
        )
        thread.start()

        with self._lock:
            self._server = server
            self._thread = thread
            self._config = config
            self._cache = None
        return True

    def stop(self, *args: Any) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
            self._cache = None
            self._config = None

        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def get_index_bytes(self) -> bytes:
        return self._get_cached_artifacts().artifacts.index_bytes

    def get_zip_bytes(self) -> bytes:
        return self._get_cached_artifacts().artifacts.zip_bytes

    def _get_cached_artifacts(self) -> CachedArtifacts:
        with self._lock:
            cache = self._cache
            config = self._config

        if config is None:
            raise RuntimeError("The Bee local update server is not configured.")

        now = time.monotonic()
        if cache and now - cache.built_at <= CACHE_TTL_SECONDS:
            return cache

        artifacts = self._run_collection_task_sync(
            lambda col: self._build_artifacts(col, config)
        )
        cached = CachedArtifacts(built_at=now, artifacts=artifacts)

        with self._lock:
            self._cache = cached
        return cached

    def _build_artifacts(self, col: Any, config: AddonConfig) -> DictionaryArtifacts:
        words, _stats = build_known_word_list(col, config)
        return build_dictionary_artifacts(words, config)

    def _run_collection_task_sync(self, task: Callable[[Any], T]) -> T:
        result: Future[T] = Future()

        def schedule() -> None:
            col = mw.col
            if col is None:
                result.set_exception(RuntimeError("No collection is currently open."))
                return

            def background_task() -> T:
                return task(col)

            def on_done(background_future: Future[T]) -> None:
                try:
                    result.set_result(background_future.result())
                except Exception as error:
                    result.set_exception(error)

            mw.taskman.run_in_background(
                background_task,
                on_done=on_done,
                uses_collection=True,
            )

        mw.taskman.run_on_main(schedule)
        return result.result()


server_manager = LocalUpdateServerManager()


def register_server_hooks() -> None:
    server_manager.register_hooks()
