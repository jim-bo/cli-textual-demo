import httpx
from cli_textual.tools.base import ToolResult

MAX_CHARS = 8192


async def web_fetch(url: str) -> ToolResult:
    """Fetch a URL via HTTP GET and return the response body.

    Response body is capped at 8 KB.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            response = await client.get(url)
        body = response.text
        truncated = ""
        if len(body) > MAX_CHARS:
            body = body[:MAX_CHARS]
            truncated = "\n[truncated]"
        return ToolResult(output=f"HTTP {response.status_code}\n{body}{truncated}")
    except Exception as exc:
        return ToolResult(output=f"Error fetching URL: {exc}", is_error=True)
