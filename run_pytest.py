from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


def main() -> int:
    tests_conftest = Path(__file__).parent / "tests" / "conftest.py"
    spec = importlib.util.spec_from_file_location("_pytest_stubs", tests_conftest)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load test bootstrap.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.StubEnvironment().install()
    return pytest.main(["-q", "tests"])


if __name__ == "__main__":
    raise SystemExit(main())
