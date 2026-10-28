"""Safe, minimal Agent tool namespace for the standalone local application.

Import the local MCP adapter explicitly via ``agent.tools.mcp_client``.
The original optional web-search and chart-generation tools are intentionally
not distributed here.  Eagerly importing them from this package initializer
would break even the safe, read-only Agent -> MCP boundary check.
"""

__all__ = []
