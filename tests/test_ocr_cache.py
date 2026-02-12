from __future__ import annotations

import os
from pathlib import Path

from core.executor.computer_executor import ComputerExecutor, ExecutorConfig, Observation
from core.ocr.engine import OCRCache, OCRResult
from memory import store

ROOT = Path(__file__).resolve().parents[1]


class StubProvider:
    name = "stub"

    def __init__(self):
        self.calls = 0

    def extract(self, image_bytes: bytes, lang: str | None = None):
        self.calls += 1
        return OCRResult(text="hello")


def _prepare_store(tmp_path: Path):
    os.environ["ASTRA_DATA_DIR"] = str(tmp_path)
    store.reset_for_tests()
    store.init(tmp_path, ROOT / "memory" / "migrations")


def test_ocr_cache_avoids_duplicate_calls(tmp_path):
    _prepare_store(tmp_path)
    project = store.create_project("ocr", [], {})
    run = store.create_run(project["id"], "ocr", "execute_confirm")
    task = store.create_task(run["id"], "step-1", attempt=1)

    provider = StubProvider()
    cache = OCRCache()
    executor = ComputerExecutor(ROOT, ocr_provider=provider, ocr_cache=cache)
    cfg = ExecutorConfig(ocr_enabled=True)

    obs = Observation(hash="hash1", width=1, height=1, ts=0.0, image_bytes=b"img")

    first = executor._get_ocr_result(run["id"], "step-1", task["id"], obs, cfg)
    second = executor._get_ocr_result(run["id"], "step-1", task["id"], obs, cfg)

    assert first is not None
    assert second is not None
    assert provider.calls == 1
