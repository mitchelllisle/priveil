"""Tests for MCP server registration and tool schemas."""

import asyncio


def test_tools_registered():
    from priveil.mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {"detect", "anonymise", "assess"}


def test_detect_schema():
    from priveil.mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    by_name = {t.name: t for t in tools}
    props = by_name["detect"].inputSchema["properties"]
    assert "text" in props
    assert "mode" in props


def test_anonymise_schema():
    from priveil.mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    by_name = {t.name: t for t in tools}
    props = by_name["anonymise"].inputSchema["properties"]
    assert "text" in props
    assert "operator_overrides" in props


def test_assess_schema():
    from priveil.mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    by_name = {t.name: t for t in tools}
    props = by_name["assess"].inputSchema["properties"]
    assert "text" in props
    assert "context" in props


def test_no_private_state_in_tool_schemas():
    """Engine internals must not leak into the MCP-facing schemas."""
    from priveil.mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    for tool in tools:
        props = tool.inputSchema.get("properties", {})
        assert "ctx" not in props, f"{tool.name} exposes ctx in schema"
        assert "analyser" not in props
        assert "pseudonymiser" not in props
