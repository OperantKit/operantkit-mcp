"""DSL tools: syntax check, Method-section compilation, and extraction.

Each function is pure (no MCP dependency) and returns a dataclass so the
MCP layer can publish an output schema and structured content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from contingency_dsl import DslError, analyze, format_program, from_dict, parse, to_dict
from contingency_dsl.annotations.apparatus.extension import ApparatusExtension
from contingency_dsl.annotations.measurement.extension import MeasurementExtension
from contingency_dsl.annotations.stimulus.extension import StimulusExtension
from contingency_dsl.annotations.subjects.extension import SubjectsExtension
from contingency_dsl.annotations.temporal.extension import TemporalExtension
from contingency_dsl.extensions import ExtensionRegistry
from contingency_dsl2procedure import compile_method
from contingency_procedure2dsl import extract_all

ANNOTATIONS = ExtensionRegistry.build(
    ApparatusExtension(),
    MeasurementExtension(),
    StimulusExtension(),
    SubjectsExtension(),
    TemporalExtension(),
)

MethodStyle = Literal["jeab", "jaba"]


def parse_source(source: str):
    """Parse DSL source with the five standard annotation extensions."""
    return parse(source, extensions=ANNOTATIONS)


@dataclass(frozen=True)
class DslErrorInfo:
    """A parse or semantic error, reported as data rather than raised."""

    type: str
    message: str


@dataclass(frozen=True)
class CheckDslResult:
    """Outcome of :func:`check_dsl`."""

    ok: bool
    canonical: str | None = None
    ast: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    error: DslErrorInfo | None = None


def check_dsl(source: str) -> CheckDslResult:
    """Parse and analyze a contingency-dsl expression.

    Returns the canonical (normalized) DSL string and the AST on success.
    Syntax and semantic errors are returned in ``error`` instead of raised.
    """
    try:
        result = analyze(parse_source(source))
    except DslError as exc:
        return CheckDslResult(ok=False, error=DslErrorInfo(type(exc).__name__, str(exc)))
    return CheckDslResult(
        ok=True,
        canonical=format_program(result.program),
        ast=to_dict(result.program),
        warnings=list(result.warnings),
    )


@dataclass(frozen=True)
class ReferenceInfo:
    """One bibliography entry collected during Method compilation."""

    key: str
    text: str


@dataclass(frozen=True)
class MethodResult:
    """Outcome of :func:`dsl_to_method`."""

    subjects: str
    apparatus: str
    procedure: str
    references: list[ReferenceInfo]
    markdown: str


def dsl_to_method(source: str, style: MethodStyle = "jeab") -> MethodResult:
    """Compile a DSL expression into a Method section (JEAB English or J-ABA Japanese).

    Raises ``ValueError`` when the DSL does not parse.
    """
    try:
        ast = to_dict(parse_source(source))
    except DslError as exc:
        raise ValueError(f"{type(exc).__name__}: {exc}") from exc
    method = compile_method(ast, style=style)
    citation_format = method.style.citation_format
    return MethodResult(
        subjects=method.subjects,
        apparatus=method.apparatus,
        procedure=method.procedure,
        references=[ReferenceInfo(r.key, r.format(citation_format)) for r in method.references],
        markdown=method.to_text(),
    )


@dataclass(frozen=True)
class ExtractedSchedule:
    """One schedule recognized in Method-section text."""

    dsl: str | None
    confidence: float
    span: list[int]
    source_text: str


@dataclass(frozen=True)
class ExtractedParam:
    """One program-level parameter (e.g. COD, LH) recognized in the text."""

    name: str
    value: float | None
    unit: str | None


@dataclass(frozen=True)
class MethodToDslResult:
    """Outcome of :func:`method_to_dsl`."""

    dsl: str | None
    schedules: list[ExtractedSchedule]
    params: list[ExtractedParam]
    unrecognized_fragments: list[str]


def _schedule_to_dsl(schedule_ast: dict[str, Any]) -> str | None:
    program = {"type": "Program", "param_decls": [], "bindings": [], "schedule": schedule_ast}
    try:
        return format_program(from_dict(program))
    except (KeyError, TypeError, ValueError, DslError):
        return None


def method_to_dsl(text: str) -> MethodToDslResult:
    """Extract a DSL expression from Method-section prose (rule-based layer only).

    No LLM is called. Fragments the rules could not map are listed in
    ``unrecognized_fragments`` for the caller to read.
    """
    report = extract_all(text)
    program = report.to_program()
    dsl = format_program(from_dict(program)) if program["schedule"] else None
    return MethodToDslResult(
        dsl=dsl,
        schedules=[
            ExtractedSchedule(
                dsl=_schedule_to_dsl(s.ast),
                confidence=s.confidence,
                span=list(s.span),
                source_text=s.source_text,
            )
            for s in report.schedules
        ],
        params=[
            ExtractedParam(
                name=str(p.ast.get("name", "")),
                value=p.ast.get("value"),
                unit=p.ast.get("time_unit"),
            )
            for p in report.params
            if p.ast.get("type") == "ParamDecl"
        ],
        unrecognized_fragments=list(report.unrecognized_fragments),
    )
