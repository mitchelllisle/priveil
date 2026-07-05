"""Entry point for the Priveil MCP server.

Run with::

    python -m priveil.mcp                   # stdio (default)
    MCP_TRANSPORT=sse uv run python -m priveil.mcp   # SSE over HTTP

Transport is controlled by the ``MCP_TRANSPORT`` environment variable:

* ``stdio`` (default) — standard MCP over stdin/stdout.
* ``sse`` — HTTP + Server-Sent Events; honour ``FASTMCP_HOST`` / ``FASTMCP_PORT``.
* ``streamable-http`` — MCP Streamable HTTP transport.

Requires the ``mcp`` optional extra::

    uv sync --extra mcp
"""

from __future__ import annotations

import logging


def main() -> None:
    """Start the Priveil MCP server.

    Transport is read from ``MCP_TRANSPORT`` (default: ``stdio``).
    For SSE/HTTP transports, FastMCP reads ``FASTMCP_HOST`` and ``FASTMCP_PORT``.

    Loads settings from the environment (``PRIVEIL_*`` prefix).
    Requires: ``uv sync --extra mcp``.
    """
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    # Import triggers @mcp.tool() registration via priveil.mcp.tools
    import priveil.mcp  # noqa: F401  — side-effect: registers MCP tools

    priveil.mcp.mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
