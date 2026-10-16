"""MCP layer: tool registration, schemas, and a stdio round trip."""

from __future__ import annotations

import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

TOOLS = {
    "check_dsl",
    "simulate",
    "dsl_to_method",
    "method_to_dsl",
    "summarize_okl",
    "analyze_okl",
}
FI_OKL = str(Path(__file__).parent / "fixtures" / "fi30s.okl.txt")


async def _with_session(fn):
    params = StdioServerParameters(command=sys.executable, args=["-m", "operantkit_mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


@pytest.mark.integration
def test_lists_tools_with_output_schema():
    async def go(session):
        return (await session.list_tools()).tools

    tools = anyio.run(_with_session, go)
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.output_schema is not None, t.name
        assert t.input_schema["type"] == "object"


@pytest.mark.integration
def test_call_returns_structured_content():
    async def go(session):
        return (
            await session.call_tool("check_dsl", {"source": "FR 5"}),
            await session.call_tool("simulate", {"source": "FR3", "exit_reinforcers": 2}),
        )

    check, sim = anyio.run(_with_session, go)
    assert check.structured_content["canonical"] == "FR5"
    assert sim.structured_content["reinforcers_per_operandum"] == [2]
    assert not sim.is_error


@pytest.mark.integration
def test_bad_exit_is_tool_error():
    async def go(session):
        return await session.call_tool("simulate", {"source": "FR3"})

    r = anyio.run(_with_session, go)
    assert r.is_error


@pytest.mark.integration
def test_okl_tools_over_stdio(tmp_path):
    png = tmp_path / "fi.png"

    async def go(session):
        return (
            await session.call_tool("summarize_okl", {"path": FI_OKL}),
            await session.call_tool(
                "analyze_okl",
                {"path": FI_OKL, "analyses": ["prps", "irt"], "png_path": str(png)},
            ),
            await session.call_tool("analyze_okl", {"path": FI_OKL, "analyses": ["magic"]}),
        )

    summary, analysis, bad = anyio.run(_with_session, go)
    assert summary.structured_content["counts"]["response"] == 132
    assert analysis.structured_content["prps"]["n"] == 4
    assert analysis.structured_content["irt"]["n"] == 131
    assert analysis.structured_content["bouts"] is None
    assert png.is_file()
    assert bad.is_error
