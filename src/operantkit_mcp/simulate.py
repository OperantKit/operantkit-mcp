"""Virtual-subject simulation of a contingency-dsl schedule.

Assembles the same pipeline as the ``operant run`` command
(DSL -> runtime schedule -> SessionRunner -> experiment_io.drive against
Poisson virtual subjects) without importing that command-line package.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from contingency.bridge import from_dsl
from contingency.errors import ScheduleConfigError
from contingency.schedules.concurrent import Concurrent
from contingency_dsl import DslError
from experiment_core import ReinforcementCountExit, TimeLimitExit
from experiment_core.events import ReinforcerStartEvent, ResponseEvent, SessionEvent
from experiment_io import drive
from experiment_io.hw import ResponseSample
from experiment_io.hw.backends.virtual import (
    ManualClock,
    MultiVirtualSubject,
    RecordingReinforcer,
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


class _PacedResponder:
    """Virtual subject whose responses wait for the clock to reach them.

    ``experiment_io``'s virtual operanda advance the clock by one IRT on
    every poll and always return a response, so ``drive`` never calls
    ``handle_tick`` between responses and time-based schedules (FT, VT,
    DRO, limited holds) only see time pass at a response. Here a poll
    returns nothing until the clock has reached the next response, so
    ``drive`` advances the clock by its ``poll_interval`` and ticks the
    session in between. A response is stamped with the clock time of the
    poll that returns it, so events stay in time order.

    ``next_event`` returns ``(operandum_index, seconds_after_previous)``
    on the subject's own timeline, which pauses during reinforcement.
    """

    def __init__(
        self,
        next_event: Callable[[], tuple[int, float]],
        subject: object,
        clock: ManualClock,
    ) -> None:
        self._next_event = next_event
        self._subject = subject
        self._clock = clock
        self._cursor = clock()
        self._queued: tuple[int, float] | None = None

    def operanda(self, n: int) -> list[_PacedOperandum]:
        return [_PacedOperandum(i, self) for i in range(n)]

    def poll_for(self, index: int) -> list[ResponseSample]:
        if self._queued is None:
            op, delta = self._next_event()
            self._cursor += delta
            self._queued = (op, self._cursor)
        op, due = self._queued
        if op != index or self._clock() < due:
            return []
        self._queued = None
        return [ResponseSample(operandum_index=index, timestamp=self._clock())]

    def freeze_for_reinforcer(self, duration: float) -> None:
        freeze = getattr(self._subject, "freeze_for_reinforcer", None)
        if callable(freeze):
            freeze(duration)
        self._cursor += duration
        if self._queued is not None:
            op, due = self._queued
            self._queued = (op, due + duration)


class _PacedOperandum:
    def __init__(self, index: int, parent: _PacedResponder) -> None:
        self.operandum_index = index
        self._parent = parent

    def poll(self) -> list[ResponseSample]:
        return self._parent.poll_for(self.operandum_index)

    def close(self) -> None:
        pass


def _build_operanda(schedule, rate_hz: float, seed: int, clock: ManualClock) -> list:
    """One independent Poisson responder per concurrent component, else one operandum."""
    if isinstance(schedule, Concurrent):
        n = len(schedule.components)
        multi = MultiVirtualSubject(rates_hz=[rate_hz] * n, seeds=[seed + i for i in range(n)])
        return _PacedResponder(multi.next_event, multi, clock).operanda(n)
    single = VirtualSubject(rate_hz=rate_hz, seed=seed)
    return _PacedResponder(lambda: (0, single.next_irt()), single, clock).operanda(1)


def _default_max_steps(exit_time: float | None, tick_seconds: float) -> int:
    """Enough loop steps for every tick of a timed session plus its responses."""
    if exit_time is not None:
        return int(exit_time / tick_seconds * 2) + 200_000
    return 2_000_000


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
    max_steps: int | None = None,
    tick_seconds: float = 0.01,
) -> SimulationResult:
    """Run the schedule against virtual Poisson subjects on a virtual clock.

    Give exactly one of ``exit_reinforcers`` or ``exit_time``. ``seed`` seeds
    the virtual subjects; seed VI/VR/VT values with ``@algorithm(seed=N)`` in
    the DSL. When ``output_path`` is given, an OKL v1 log is written there.
    Between responses the session is ticked every ``tick_seconds``, so
    time-based schedules (FT, VT, DRO, limited holds) run on that resolution.
    """
    if virtual_rate_hz <= 0:
        raise ValueError("virtual_rate_hz must be > 0")
    if tick_seconds <= 0:
        raise ValueError("tick_seconds must be > 0")
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
        max_steps=max_steps if max_steps is not None else _default_max_steps(exit_time, tick_seconds),
        poll_interval=tick_seconds,
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
