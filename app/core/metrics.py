from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from threading import Lock


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percentile), len(ordered) - 1)
    return round(ordered[index], 2)


@dataclass(slots=True)
class MetricsRegistry:
    """In-process demo metrics. Use OpenTelemetry/Prometheus in a multi-worker deployment."""

    counters: Counter[str] = field(default_factory=Counter)
    latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=2000))
    _lock: Lock = field(default_factory=Lock, repr=False)

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self.counters[name] += amount

    def observe_latency(self, milliseconds: float) -> None:
        with self._lock:
            self.latencies_ms.append(milliseconds)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            latencies = list(self.latencies_ms)
            return {
                "counters": dict(self.counters),
                "latency_ms": {
                    "samples": len(latencies),
                    "p50": _percentile(latencies, 0.50),
                    "p95": _percentile(latencies, 0.95),
                    "max": round(max(latencies), 2) if latencies else 0.0,
                },
            }
