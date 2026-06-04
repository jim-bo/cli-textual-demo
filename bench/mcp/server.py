"""A fixed, hermetic MCP server for the smoke-bench.

Exposes a handful of deterministic tools with checkable outputs so the bench can
score whether the agent (a) discovered and called the right MCP tool and (b)
used its result. Run directly (`python server.py`) it speaks MCP over stdio.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("smoke-bench")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Return the product of two integers."""
    return a * b


@mcp.tool()
def reverse_text(text: str) -> str:
    """Return the input string reversed."""
    return text[::-1]


@mcp.tool()
def count_words(text: str) -> int:
    """Return the number of whitespace-separated words in the text."""
    return len(text.split())


@mcp.tool()
def secret_word() -> str:
    """Return the secret word (not knowable without calling this tool)."""
    return "marmoset"


if __name__ == "__main__":
    mcp.run()
