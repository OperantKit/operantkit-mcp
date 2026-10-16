"""stdio MCP server exposing OperantKit tools."""

from __future__ import annotations

from mcp.server import MCPServer

from . import dsl_tools, okl_tools
from .simulate import SimulationResult
from .simulate import simulate as _simulate

INSTRUCTIONS = (
    "Tools for designing reinforcement schedules with contingency-dsl. "
    "Write the schedule as one DSL expression (e.g. 'FR 5', 'Conc(VI30s, VI60s, COD=2s)') "
    "and call check_dsl first; use its canonical form afterwards. "
    "simulate with output_path writes an OKL v1 log; read it with summarize_okl "
    "and analyze_okl."
)

mcp = MCPServer(name="operantkit", instructions=INSTRUCTIONS)


@mcp.tool()
def check_dsl(source: str) -> dsl_tools.CheckDslResult:
    """Parse and analyze a contingency-dsl schedule expression.

    Returns ok, the canonical DSL string, the AST, and warnings. Errors are
    returned in `error` (type, message) instead of failing the call.
    """
    return dsl_tools.check_dsl(source)


@mcp.tool()
def simulate(
    source: str,
    exit_reinforcers: int | None = None,
    exit_time: float | None = None,
    virtual_rate_hz: float = 1.0,
    seed: int = 0,
    reinforcer_duration: float = 0.5,
    output_path: str | None = None,
) -> SimulationResult:
    """Simulate the schedule against virtual Poisson subjects on a virtual clock.

    Give exactly one of exit_reinforcers or exit_time (seconds). Same seed gives
    the same result. A concurrent schedule gets one responder per component.
    When output_path is given, an OKL v1 event log is written there.
    """
    return _simulate(
        source,
        exit_reinforcers=exit_reinforcers,
        exit_time=exit_time,
        virtual_rate_hz=virtual_rate_hz,
        seed=seed,
        reinforcer_duration=reinforcer_duration,
        output_path=output_path,
    )


@mcp.tool()
def dsl_to_method(source: str, style: dsl_tools.MethodStyle = "jeab") -> dsl_tools.MethodResult:
    """Write a Method section (subjects, apparatus, procedure, references) from a DSL expression.

    style: "jeab" (English, JEAB) or "jaba" (Japanese, J-ABA).
    """
    return dsl_tools.dsl_to_method(source, style=style)


@mcp.tool()
def method_to_dsl(text: str) -> dsl_tools.MethodToDslResult:
    """Extract a DSL expression from Method-section prose with the rule-based extractor.

    No LLM is used. Read `unrecognized_fragments` yourself and fill gaps manually.
    """
    return dsl_tools.method_to_dsl(text)


@mcp.tool()
def summarize_okl(path: str) -> okl_tools.OklSummary:
    """Summarize an OKL v1 session log (the file simulate writes with output_path).

    Returns the session name, the DSL from the header, clock type, session
    length in seconds, counts per event type, responses and reinforcers per
    operandum, and phase markers.
    """
    return okl_tools.summarize_okl(path)


@mcp.tool()
def analyze_okl(
    path: str,
    analyses: list[okl_tools.Analysis] | None = None,
    png_path: str | None = None,
) -> okl_tools.OklAnalysis:
    """Analyze an OKL v1 session log.

    analyses: any of "prps" (post-reinforcement pauses), "irt" (inter-response
    times pooled over operanda), "bouts" (two-component log-normal bout
    analysis), "matching" (one-condition generalized matching for operanda 0
    and 1); default all. Analyses that cannot be computed are null and
    explained in notes. When png_path is given, the cumulative record is
    written there as PNG.
    """
    return okl_tools.analyze_okl(path, analyses=analyses, png_path=png_path)


def main() -> None:
    """Console-script entry point: serve over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
