"""Circuit breaker with sliding-window failure rate detection."""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any

from app.utils.logger import get_logger

_LOGGER = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker state machine states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Sliding-window circuit breaker for external service calls.

    State transitions:
      CLOSED → OPEN: failure_rate > threshold within window AND failure_count > min_failures
      OPEN → HALF_OPEN: after recovery_timeout seconds
      HALF_OPEN → CLOSED: probe request succeeds
      HALF_OPEN → OPEN: probe request fails
    """

    def __init__(
        self,
        name: str,
        window_seconds: float = 60.0,
        failure_threshold: float = 0.5,
        min_failures: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._name = name
        self._window_seconds = window_seconds
        self._failure_threshold = failure_threshold
        self._min_failures = min_failures
        self._recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._opened_at: float = 0.0
        self._records: list[tuple[float, bool]] = []
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self._recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN

    async def record_success(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._records.append((now, True))
            self._prune_old_records(now)
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                self._state = CircuitState.CLOSED
                _LOGGER.info("circuit_breaker=%s state=CLOSED (recovered)", self._name)

    async def record_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._records.append((now, False))
            self._prune_old_records(now)

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = now
                _LOGGER.warning("circuit_breaker=%s state=OPEN (half-open probe failed)", self._name)
                return

            if self._state == CircuitState.CLOSED:
                failures = sum(1 for _, ok in self._records if not ok)
                total = len(self._records)
                if total > 0 and failures >= self._min_failures:
                    rate = failures / total
                    if rate >= self._failure_threshold:
                        self._state = CircuitState.OPEN
                        self._opened_at = now
                        _LOGGER.warning(
                            "circuit_breaker=%s state=OPEN (rate=%.2f failures=%d/%d)",
                            self._name, rate, failures, total,
                        )

    async def force_open(self) -> None:
        async with self._lock:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            _LOGGER.warning("circuit_breaker=%s force_open", self._name)

    async def force_close(self) -> None:
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._records.clear()
            _LOGGER.info("circuit_breaker=%s force_close", self._name)

    def get_status(self) -> dict[str, Any]:
        now = time.monotonic()
        self._prune_old_records(now)
        failures = sum(1 for _, ok in self._records if not ok)
        total = len(self._records)
        return {
            "name": self._name,
            "state": self.state.value,
            "failure_rate": round(failures / total, 3) if total > 0 else 0.0,
            "total_in_window": total,
            "failures_in_window": failures,
        }

    def _prune_old_records(self, now: float) -> None:
        cutoff = now - self._window_seconds
        self._records = [(ts, ok) for ts, ok in self._records if ts >= cutoff]


class DegradationPolicy:
    """Centralized degradation matrix for the entire graph."""

    def __init__(self) -> None:
        self.llm_breaker = CircuitBreaker(name="llm", window_seconds=60, min_failures=5)
        self.coze_breaker = CircuitBreaker(name="coze", window_seconds=60, min_failures=3)
        self._force_degrade_llm = False
        self._force_degrade_coze = False

    @property
    def llm_available(self) -> bool:
        if self._force_degrade_llm:
            return False
        return self.llm_breaker.is_available

    @property
    def coze_available(self) -> bool:
        if self._force_degrade_coze:
            return False
        return self.coze_breaker.is_available

    def set_force_degrade(self, service: str, enabled: bool) -> None:
        if service == "llm":
            self._force_degrade_llm = enabled
        elif service == "coze":
            self._force_degrade_coze = enabled

    def get_status(self) -> dict[str, Any]:
        return {
            "llm": {
                **self.llm_breaker.get_status(),
                "force_degraded": self._force_degrade_llm,
                "available": self.llm_available,
            },
            "coze": {
                **self.coze_breaker.get_status(),
                "force_degraded": self._force_degrade_coze,
                "available": self.coze_available,
            },
        }


degradation_policy = DegradationPolicy()
