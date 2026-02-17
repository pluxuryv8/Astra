from __future__ import annotations

import statistics
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import build_chat_system_prompt


def _avg_prompt_latency(user_message: str, runs: int = 3) -> float:
    samples: list[float] = []
    for _ in range(runs):
        start = perf_counter()
        build_chat_system_prompt(
            [],
            None,
            user_message=user_message,
            history=[],
            owner_direct_mode=True,
        )
        samples.append(perf_counter() - start)
    return statistics.mean(samples)


def test_prompt_latency_simple_under_5s():
    avg = _avg_prompt_latency("Дай формулу")
    assert avg < 5.0


def test_prompt_latency_frustrated_under_5s():
    avg = _avg_prompt_latency("Бля, я заебался, помоги быстро и по делу.")
    assert avg < 5.0

