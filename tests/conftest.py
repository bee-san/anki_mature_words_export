from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import io
from pathlib import Path
import re
import sys
import types
from typing import Any

import pytest

PACKAGE_NAME = "anki_mature_words_export"
REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeFuture:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def result(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._result


class FakeSignal:
    def __init__(self) -> None:
        self.callbacks: list[Any] = []

    def connect(self, callback: Any) -> None:
        self.callbacks.append(callback)

    def emit(self) -> None:
        for callback in self.callbacks:
            callback()


class FakeWidget:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.enabled = True
        self.visible = True
        self.word_wrap = False
        self.style_sheet = ""
        self.size_policy: tuple[Any, Any] | None = None
        self.minimum_height: int | None = None

    def setEnabled(self, value: bool) -> None:
        self.enabled = value

    def setVisible(self, value: bool) -> None:
        self.visible = value

    def setWordWrap(self, value: bool) -> None:
        self.word_wrap = value

    def setStyleSheet(self, value: str) -> None:
        self.style_sheet = value

    def setMinimumHeight(self, value: int) -> None:
        self.minimum_height = value

    def setSizePolicy(self, horizontal: Any, vertical: Any) -> None:
        self.size_policy = (horizontal, vertical)


class FakeClipboard:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, value: str) -> None:
        self.text = value


class QApplication:
    _clipboard = FakeClipboard()

    @staticmethod
    def clipboard() -> FakeClipboard:
        return QApplication._clipboard


class QComboBox(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.items: list[str] = []
        self.current_text = ""

    def addItems(self, items: list[str]) -> None:
        self.items.extend(items)
        if items and not self.current_text:
            self.current_text = items[0]

    def setCurrentText(self, value: str) -> None:
        self.current_text = value

    def currentText(self) -> str:
        return self.current_text


class QDialog(FakeWidget):
    class DialogCode:
        Rejected = 0
        Accepted = 1

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.window_title = ""
        self.modal = False
        self.size: tuple[int, int] | None = None
        self.accepted = False
        self.exec_calls = 0
        self.exec_result = self.DialogCode.Rejected

    def setWindowTitle(self, value: str) -> None:
        self.window_title = value

    def setModal(self, value: bool) -> None:
        self.modal = value

    def resize(self, width: int, height: int) -> None:
        self.size = (width, height)

    def accept(self) -> None:
        self.accepted = True
        self.exec_result = self.DialogCode.Accepted

    def exec(self) -> int:
        self.exec_calls += 1
        return self.exec_result


class QFrame(FakeWidget):
    pass


class QHBoxLayout:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.items: list[Any] = []

    def addStretch(self, value: int) -> None:
        self.items.append(("stretch", value))

    def addWidget(self, value: Any) -> None:
        self.items.append(("widget", value))

    def addLayout(self, value: Any) -> None:
        self.items.append(("layout", value))

    def addSpacing(self, value: int) -> None:
        self.items.append(("spacing", value))


class QVBoxLayout(QHBoxLayout):
    pass


class QLabel(FakeWidget):
    def __init__(self, text: str = "", *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._text = text

    def setText(self, value: str) -> None:
        self._text = value

    def text(self) -> str:
        return self._text


class QLineEdit(FakeWidget):
    def __init__(self, text: str = "", *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._text = text

    def text(self) -> str:
        return self._text

    def setText(self, value: str) -> None:
        self._text = value


class QPushButton(FakeWidget):
    def __init__(self, text: str = "", *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.text = text
        self.clicked = FakeSignal()


class QSizePolicy:
    class Policy:
        Expanding = "expanding"
        Fixed = "fixed"


class QSpinBox(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.range = (0, 0)
        self._value = 0

    def setRange(self, minimum: int, maximum: int) -> None:
        self.range = (minimum, maximum)

    def setValue(self, value: int) -> None:
        self._value = value

    def value(self) -> int:
        return self._value


class QStackedWidget(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.widgets: list[Any] = []
        self.index = 0

    def addWidget(self, widget: Any) -> None:
        self.widgets.append(widget)

    def setCurrentIndex(self, value: int) -> None:
        self.index = value

    def currentIndex(self) -> int:
        return self.index

    def count(self) -> int:
        return len(self.widgets)


class FakeToolbar:
    def __init__(self) -> None:
        self.created_links: list[tuple[str, str, Any, str]] = []

    def create_link(self, cmd: str, label: str, func: Any, tip: str = "") -> str:
        self.created_links.append((cmd, label, func, tip))
        return f"<a>{label}</a>"


class FakeAddonManager:
    def __init__(self, state: "StubState") -> None:
        self.state = state

    def getConfig(self, name: str) -> dict[str, Any] | None:
        self.state.get_config_calls.append(name)
        return self.state.config_data

    def writeConfig(self, name: str, value: dict[str, Any]) -> None:
        self.state.write_config_calls.append((name, value))
        self.state.config_data = dict(value)


class FakeTaskMan:
    def __init__(self, state: "StubState") -> None:
        self.state = state

    def run_in_background(
        self,
        task: Any,
        on_done: Any = None,
        uses_collection: bool = True,
    ) -> None:
        self.state.run_in_background_calls.append((task, on_done, uses_collection))
        try:
            result = task()
            future = FakeFuture(result=result)
        except Exception as error:  # pragma: no cover - exercised in tests
            future = FakeFuture(error=error)
        if on_done is not None:
            on_done(future)

    def run_on_main(self, callback: Any) -> None:
        self.state.run_on_main_calls.append(callback)
        callback()


class FakeQueryOp:
    def __init__(self, parent: Any, op: Any, success: Any = None) -> None:
        self.parent = parent
        self.op = op
        self.success = success
        self.failure_handler = None
        self.progress_label = None
        self.state = CURRENT_STATE
        self.state.query_ops.append(self)

    def with_progress(self, label: str | None = None) -> "FakeQueryOp":
        self.progress_label = label
        return self

    def failure(self, handler: Any) -> "FakeQueryOp":
        self.failure_handler = handler
        return self

    def run_in_background(self) -> "FakeQueryOp":
        try:
            result = self.op(sys.modules["aqt"].mw.col)
        except Exception as error:
            if self.failure_handler is not None:
                self.failure_handler(error)
            else:  # pragma: no cover - defensive
                raise
        else:
            if self.success is not None:
                self.success(result)
        return self


class FakeDeckManager:
    def __init__(self, names: list[str]) -> None:
        self.names = names

    def all_names_and_ids(self) -> list[Any]:
        return [types.SimpleNamespace(name=name) for name in self.names]


class FakeCard:
    def __init__(self, nid: int) -> None:
        self.nid = nid


class FakeCollection:
    def __init__(
        self,
        search_results: dict[str, list[int]] | None = None,
        cards: dict[int, FakeCard] | None = None,
        notes: dict[int, dict[str, str]] | None = None,
        deck_names: list[str] | None = None,
    ) -> None:
        self.search_results = search_results or {}
        self.cards = cards or {}
        self.notes = notes or {}
        self.decks = FakeDeckManager(deck_names or [])

    def find_cards(self, query: str) -> list[int]:
        return list(self.search_results.get(query, []))

    def get_card(self, card_id: int) -> FakeCard:
        return self.cards[card_id]

    def get_note(self, note_id: int) -> dict[str, str]:
        return self.notes[note_id]


@dataclass
class StubState:
    config_data: dict[str, Any] | None = None
    get_config_calls: list[str] = field(default_factory=list)
    write_config_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    warnings: list[tuple[str, Any]] = field(default_factory=list)
    tooltips: list[tuple[str, int | None]] = field(default_factory=list)
    save_file_path: str | None = None
    save_file_calls: list[dict[str, Any]] = field(default_factory=list)
    run_in_background_calls: list[tuple[Any, Any, bool]] = field(default_factory=list)
    run_on_main_calls: list[Any] = field(default_factory=list)
    query_ops: list[FakeQueryOp] = field(default_factory=list)
    mw: Any = None


CURRENT_STATE: StubState


class StubEnvironment:
    def __init__(self) -> None:
        self.state = StubState()

    def install(self) -> None:
        global CURRENT_STATE
        CURRENT_STATE = self.state
        self._purge_modules()
        QApplication._clipboard = FakeClipboard()
        if str(REPO_ROOT.parent) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT.parent))

        qt_module = types.ModuleType("aqt.qt")
        qt_module.QApplication = QApplication
        qt_module.QComboBox = QComboBox
        qt_module.QDialog = QDialog
        qt_module.QFrame = QFrame
        qt_module.QHBoxLayout = QHBoxLayout
        qt_module.QLabel = QLabel
        qt_module.QLineEdit = QLineEdit
        qt_module.QPushButton = QPushButton
        qt_module.QSizePolicy = QSizePolicy
        qt_module.QSpinBox = QSpinBox
        qt_module.QStackedWidget = QStackedWidget
        qt_module.QVBoxLayout = QVBoxLayout

        toolbar_module = types.ModuleType("aqt.toolbar")
        toolbar_module.Toolbar = FakeToolbar

        utils_module = types.ModuleType("aqt.utils")

        def get_save_file(**kwargs: Any) -> str | None:
            self.state.save_file_calls.append(kwargs)
            return self.state.save_file_path

        def show_warning(message: str, parent: Any = None) -> None:
            self.state.warnings.append((message, parent))

        def show_tooltip(message: str, period: int | None = None) -> None:
            self.state.tooltips.append((message, period))

        utils_module.getSaveFile = get_save_file
        utils_module.showWarning = show_warning
        utils_module.tooltip = show_tooltip

        operations_module = types.ModuleType("aqt.operations")
        operations_module.QueryOp = FakeQueryOp

        aqt_module = types.ModuleType("aqt")
        aqt_module.gui_hooks = types.SimpleNamespace(
            top_toolbar_did_init_links=[],
            profile_did_open=[],
            profile_will_close=[],
        )
        aqt_module.mw = types.SimpleNamespace(
            addonManager=FakeAddonManager(self.state),
            col=FakeCollection(deck_names=["Default"]),
            taskman=FakeTaskMan(self.state),
        )
        self.state.mw = aqt_module.mw

        anki_utils_module = types.ModuleType("anki.utils")

        def strip_html(value: str) -> str:
            return re.sub(r"<[^>]+>", "", value)

        anki_utils_module.strip_html = strip_html

        anki_module = types.ModuleType("anki")
        anki_module.utils = anki_utils_module

        sys.modules["aqt"] = aqt_module
        sys.modules["aqt.qt"] = qt_module
        sys.modules["aqt.toolbar"] = toolbar_module
        sys.modules["aqt.utils"] = utils_module
        sys.modules["aqt.operations"] = operations_module
        sys.modules["anki"] = anki_module
        sys.modules["anki.utils"] = anki_utils_module

    def import_module(self, module_name: str) -> Any:
        importlib.invalidate_caches()
        return importlib.import_module(f"{PACKAGE_NAME}.{module_name}")

    def import_package(self) -> Any:
        importlib.invalidate_caches()
        return importlib.import_module(PACKAGE_NAME)

    def _purge_modules(self) -> None:
        for name in list(sys.modules):
            if name == PACKAGE_NAME or name.startswith(f"{PACKAGE_NAME}."):
                sys.modules.pop(name, None)
        for name in [
            "aqt",
            "aqt.operations",
            "aqt.qt",
            "aqt.toolbar",
            "aqt.utils",
            "anki",
            "anki.utils",
        ]:
            sys.modules.pop(name, None)


@pytest.fixture
def addon_env() -> StubEnvironment:
    env = StubEnvironment()
    env.install()
    try:
        yield env
    finally:
        server_module = sys.modules.get(f"{PACKAGE_NAME}.server")
        if server_module is not None:
            try:
                server_module.server_manager.stop()
            except Exception:  # pragma: no cover - best-effort teardown
                pass
        env._purge_modules()


@pytest.fixture
def tmp_binary_file(tmp_path: Path) -> str:
    return str(tmp_path / "output.zip")
