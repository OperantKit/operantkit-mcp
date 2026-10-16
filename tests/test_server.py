"""MCP layer: tool registration, schemas, and a stdio round trip."""

from __future__ import annotations

import sys

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

TOOLS = {"check_dsl", "simulate", "dsl_to_method", "method_to_dsl"}


async def _with_session(fn):
    params = StdioServerParameters(command=sys.executable, args=["-m", "operantkit_mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


@pytest.mark.integration
def test_lists_four_tools_with_output_schema():
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
