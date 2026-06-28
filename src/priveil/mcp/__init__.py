"""priveil MCP server — optional extra.

Install with::

    pip install "priveil[mcp]"
"""

import priveil.mcp.tools as _tools  # noqa: F401 — triggers @mcp.tool() registration
from priveil.mcp.server import main, mcp

__all__ = ["mcp", "main"]
