"""Virtual-subject simulation of a contingency-dsl schedule.

Assembles the same pipeline as the ``operant run`` command
(DSL -> runtime schedule -> SessionRunner -> experiment_io.drive against
Poisson virtual subjects) without importing that command-line package.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from contingency.bridge import from_dsl
from contingency.errors import ScheduleConfigError
from contingency.schedules.concurrent import Concurrent
from contingency_dsl import DslError
from experiment_core import ReinforcementCountExit, TimeLimitExit
from experiment_core.events import ReinforcerStartEvent, ResponseEvent, SessionEvent
from experiment_io import drive
from experiment_io.hw.backends.virtual import (
    ManualClock,
    MultiVirtualOperandum,
    MultiVirtualSubject,
    RecordingReinforcer,
    VirtualOperandum,
    VirtualSubject,
)
from session_recorder import OklSink
from session_runner import SessionConfig, SessionRunner, tee

from .dsl_tools import parse_source

_EVENT_NAMES = {
    "ResponseEvent": "response",
    "ReinforcerStartEvent": "reinforcer_start",
    "ReinforcerEndEvent": "reinforcer_end",
    "StateChangeEvent": "state_change",
    "ComponentChangeEvent": "component_change",
}


@dataclass(frozen=True)
class SimulationResult:
    """Summary of one simulated session."""

    session_seconds: float
    counts: dict[str, int]
    responses_per_operandum: list[int]
    reinforcers_per_operandum: list[int]
    response_rate_per_min: float
    reinforcement_rate_per_min: float
    okl_path: str | None = None


class _MemorySink:
    def __init__(self) -> None:
        self.events: list[SessionEvent] = []

    def emit(self, event: SessionEvent) -> None:
        self.events.append(event)


def _build_exit(exit_reinforcers: int | None, exit_time: float | None):
    if (exit_reinforcers is None) == (exit_time is None):
        raise ValueError("give exactly one of exit_reinforcers or exit_time")
    if exit_reinforcers is not None:
        if exit_reinforcers < 1:
            raise ValueError("exit_reinforcers must be >= 1")
        return ReinforcementCountExit(count=exit_reinforcers)
    if exit_time <= 0:
        raise ValueError("exit_time must be > 0")
    return TimeLimitExit(limit=exit_time)


def _build_operanda(schedule, rate_hz: float, seed: int, clock: ManualClock) -> list:
    """One independent Poisson responder per concurrent component, else one operandum."""
    if isinstance(schedule, Concurrent):
        n = len(schedule.components)
        subject = MultiVirtualSubject(rates_hz=[rate_hz] * n, seeds=[seed + i for i in range(n)])
        return MultiVirtualOperandum(subject, clock).split()
    return [VirtualOperandum(0, VirtualSubject(rate_hz=rate_hz, seed=seed), clock)]


def _per_operandum(events: list[SessionEvent], kind: type, n: int) -> list[int]:
    counts = [0] * n
    for e in events:
        if isinstance(e, kind):
            counts[e.operandum or 0] += 1
    return counts


def simulate(
    source: str,
    exit_reinforcers: int | None = None,
    exit_time: float | None = None,
    virtual_rate_hz: float = 1.0,
    seed: int = 0,
    reinforcer_duration: float = 0.5,
    output_path: str | None = None,
    max_steps: int = 200_000,
) -> SimulationResult:
    """Run the schedule against virtual Poisson subjects on a virtual clock.

    Give exactly one of ``exit_reinforcers`` or ``exit_time``. ``seed`` seeds
    the virtual subjects; seed VI/VR/VT values with ``@algorithm(seed=N)`` in
    the DSL. When ``output_path`` is given, an OKL v1 log is written there.
    """
    if virtual_rate_hz <= 0:
        raise ValueError("virtual_rate_hz must be > 0")
    try:
        schedule = from_dsl(parse_source(source))
    except (DslError, ScheduleConfigError) as exc:
        raise ValueError(f"{type(exc).__name__}: {exc}") from exc
    exit_condition = _build_exit(exit_reinforcers, exit_time)

    clock = ManualClock()
    operanda = _build_operanda(schedule, virtual_rate_hz, seed, clock)
    reinforcers = [RecordingReinforcer(operandum_index=i) for i in range(len(operanda))]
    memory = _MemorySink()
    sinks = [memory]
    okl_path = None
    if output_path is not None:
        okl = OklSink(Path(output_path))
        okl.write_header(
            session_name="operantkit-mcp",
            clock_type=type(clock).__name__,
            session_start=0.0,
            metadata={"dsl": source},
        )
        sinks.append(okl)
        okl_path = str(Path(output_path).resolve())

    runner = SessionRunner(
        SessionConfig(
            name="operantkit-mcp",
            schedule=schedule,
            exit_condition=exit_condition,
            metadata={"dsl": source},
        ),
        sink=tee(*sinks),
        clock=clock,
    )
    runner.start(start_time=clock())
    drive(
        runner,
        operanda=operanda,
        reinforcers=reinforcers,
        clock=clock,
        reinforcer_duration=reinforcer_duration,
        max_steps=max_steps,
    )

    events = memory.events
    seconds = float(clock())
    counts = Counter(_EVENT_NAMES.get(type(e).__name__, type(e).__name__) for e in events)
    n = len(operanda)
    responses = _per_operandum(events, ResponseEvent, n)
    deliveries = _per_operandum(events, ReinforcerStartEvent, n)
    minutes = seconds / 60.0 if seconds > 0 else 0.0
    return SimulationResult(
        session_seconds=seconds,
        counts=dict(sorted(counts.items())),
        responses_per_operandum=responses,
        reinforcers_per_operandum=deliveries,
        response_rate_per_min=sum(responses) / minutes if minutes else 0.0,
        reinforcement_rate_per_min=sum(deliveries) / minutes if minutes else 0.0,
        okl_path=okl_path,
    )
