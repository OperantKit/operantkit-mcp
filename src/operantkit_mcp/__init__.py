"""MCP server exposing OperantKit schedule tools over stdio."""

from __future__ import annotations

try:
    from operantkit_mcp._version import __version__
except ImportError:
    __version__ = "0.0.0+unknown"
__all__ = ["__version__"]
