"""Read and analyze OKL v1 session logs.

``summarize_okl`` uses only ``session_recorder.read_log``. ``analyze_okl``
adds the descriptive analyses and the cumulative record from
``session_analyzer``.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from experiment_core.events import ReinforcerStartEvent, ResponseEvent
from session_analyzer import plot_cumulative_record
from session_analyzer.analytics import (
    BoutMetrics,
    PRPMetrics,
    analyze_bouts,
    analyze_prps,
    compute_prps,
    estimate_single_observation_gml,
)
from session_recorder import SessionLog, read_log

Analysis = Literal["prps", "irt", "bouts", "matching"]
ANALYSES: tuple[str, ...] = ("prps", "irt", "bouts", "matching")


@dataclass(frozen=True)
class OperandumSummary:
    """Responses and reinforcer deliveries on one operandum (None = unlabelled)."""

    operandum: int | None
    responses: int
    reinforcers: int


@dataclass(frozen=True)
class PhaseMarkerSummary:
    kind: str
    timestamp: float
    label: str
    context: dict[str, str]


@dataclass(frozen=True)
class OklSummary:
    """Header fields and event counts of one OKL v1 log."""

    path: str
    session_name: str
    dsl: str | None
    clock_type: str
    session_seconds: float
    counts: dict[str, int]
    operanda: list[OperandumSummary]
    phase_markers: list[PhaseMarkerSummary]


@dataclass(frozen=True)
class IrtSummary:
    """Inter-response times pooled over all operanda, in seconds."""

    n: int
    mean: float
    median: float
    std: float
    min: float
    max: float


@dataclass(frozen=True)
class MatchingSummary:
    """One-condition Generalized Matching Law estimate for operanda 0 and 1.

    sensitivity and bias come from the closed form that sets log b = 0
    (bias = 1.0); fit several conditions for a real bias estimate.
    """

    responses: list[int]
    reinforcers: list[int]
    response_proportion: float
    reinforcer_proportion: float
    log_response_ratio: float | None
    log_reinforcer_ratio: float | None
    sensitivity: float | None
    bias: float | None


@dataclass(frozen=True)
class OklAnalysis:
    """Results of the requested analyses. Analyses not requested or not computable are None."""

    path: str
    analyses: list[str]
    irt: IrtSummary | None = None
    prps: PRPMetrics | None = None
    prp_values: list[float] | None = None
    bouts: BoutMetrics | None = None
    matching: MatchingSummary | None = None
    png_path: str | None = None
    notes: list[str] = field(default_factory=list)


def _load(path: str) -> SessionLog:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"OKL file not found: {path}")
    return read_log(p)


def _times(log: SessionLog, kind: type) -> list[float]:
    return sorted(e.timestamp for e in log.events if isinstance(e, kind))


def _per_operandum(log: SessionLog) -> list[OperandumSummary]:
    responses: Counter[int | None] = Counter()
    reinforcers: Counter[int | None] = Counter()
    for e in log.events:
        if isinstance(e, ResponseEvent):
            responses[e.operandum] += 1
        elif isinstance(e, ReinforcerStartEvent):
            reinforcers[e.operandum] += 1
    keys = sorted(set(responses) | set(reinforcers), key=lambda k: -1 if k is None else k)
    return [OperandumSummary(k, responses[k], reinforcers[k]) for k in keys]


def summarize_okl(path: str) -> OklSummary:
    """Summarize an OKL v1 log: header, duration, counts per event type and operandum."""
    log = _load(path)
    meta = log.meta
    timestamps = [e.timestamp for e in log.events]
    seconds = float(max(timestamps) - meta.timestamp) if timestamps else 0.0
    dsl = meta.metadata.get("dsl") or meta.metadata.get("schedule.spec_dsl")
    return OklSummary(
        path=str(Path(path).resolve()),
        session_name=meta.session_name,
        dsl=str(dsl) if dsl is not None else None,
        clock_type=meta.clock_type,
        session_seconds=seconds,
        counts=dict(sorted(Counter(r.type for r in log.raw_records).items())),
        operanda=_per_operandum(log),
        phase_markers=[
            PhaseMarkerSummary(m.kind, m.timestamp, m.label, dict(m.context))
            for m in log.phase_markers
        ],
    )


def _irt_summary(irts: list[float]) -> IrtSummary | None:
    if not irts:
        return None
    return IrtSummary(
        n=len(irts),
        mean=statistics.fmean(irts),
        median=statistics.median(irts),
        std=statistics.pstdev(irts),
        min=min(irts),
        max=max(irts),
    )


def _matching(operanda: list[OperandumSummary]) -> MatchingSummary | None:
    by_index = {o.operandum: o for o in operanda}
    if set(by_index) != {0, 1}:
        return None
    b = [by_index[0].responses, by_index[1].responses]
    r = [by_index[0].reinforcers, by_index[1].reinforcers]
    gml = estimate_single_observation_gml(b[0], b[1], r[0], r[1])
    log_b = math.log10(b[0] / b[1]) if b[0] > 0 and b[1] > 0 else None
    log_r = math.log10(r[0] / r[1]) if r[0] > 0 and r[1] > 0 else None
    return MatchingSummary(
        responses=b,
        reinforcers=r,
        response_proportion=b[0] / sum(b) if sum(b) else 0.0,
        reinforcer_proportion=r[0] / sum(r) if sum(r) else 0.0,
        log_response_ratio=log_b,
        log_reinforcer_ratio=log_r,
        sensitivity=gml[0] if gml else None,
        bias=gml[1] if gml else None,
    )


def analyze_okl(
    path: str,
    analyses: list[str] | None = None,
    png_path: str | None = None,
) -> OklAnalysis:
    """Run descriptive analyses on an OKL v1 log and optionally plot its cumulative record.

    ``analyses`` is any subset of ``prps``, ``irt``, ``bouts``, ``matching``
    (default: all). IRTs are pooled over operanda. ``matching`` needs
    operanda 0 and 1. When ``png_path`` is given, the cumulative record is
    written there as PNG.
    """
    requested = list(ANALYSES) if analyses is None else list(analyses)
    unknown = [a for a in requested if a not in ANALYSES]
    if unknown:
        raise ValueError(f"unknown analyses {unknown}; choose from {list(ANALYSES)}")
    log = _load(path)
    responses = _times(log, ResponseEvent)
    reinforcers = _times(log, ReinforcerStartEvent)
    irts = [b - a for a, b in zip(responses, responses[1:], strict=False)]
    notes: list[str] = []
    result: dict[str, object] = {}

    if "irt" in requested:
        result["irt"] = _irt_summary(irts)
        if result["irt"] is None:
            notes.append("irt: fewer than 2 responses")
    if "prps" in requested:
        values = compute_prps(reinforcers, responses)
        result["prp_values"] = values
        result["prps"] = analyze_prps(values)
        if result["prps"] is None:
            notes.append("prps: no reinforcer followed by a response")
    if "bouts" in requested:
        result["bouts"] = analyze_bouts(irts)
        if result["bouts"] is None:
            notes.append("bouts: too few IRTs for the two-component fit")
    if "matching" in requested:
        result["matching"] = _matching(_per_operandum(log))
        if result["matching"] is None:
            notes.append("matching: needs responses on exactly operanda 0 and 1")

    out_png = None
    if png_path is not None:
        target = Path(png_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        plot_cumulative_record(Path(path), target)
        out_png = str(target.resolve())

    return OklAnalysis(
        path=str(Path(path).resolve()),
        analyses=requested,
        png_path=out_png,
        notes=notes,
        **result,  # type: ignore[arg-type]
    )
