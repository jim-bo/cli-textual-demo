import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from cli_textual.tools.base import ToolResult

MAX_CHARS = 8192

_BLOCKED_HOSTS = {"metadata.google.internal", "metadata.goog"}


def _is_url_safe(url: str) -> str | None:
    """Return an error message if *url* targets a private/internal address, else ``None``."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Error: unsupported scheme '{parsed.scheme}'"
    hostname = parsed.hostname
    if not hostname:
        return "Error: no hostname in URL"
    if hostname in _BLOCKED_HOSTS:
        return f"Error: access denied — blocked host '{hostname}'"
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return "Error: access denied — private/internal IP"
    except socket.gaierror:
        return f"Error: cannot resolve hostname '{hostname}'"
    return None


async def web_fetch(url: str) -> ToolResult:
    """Fetch a URL via HTTP GET and return the response body.

    Response body is capped at 8 KB.  Private/internal URLs are blocked.
    """
    safety_err = _is_url_safe(url)
    if safety_err:
        return ToolResult(output=safety_err, is_error=True)
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
