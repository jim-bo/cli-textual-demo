import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from cli_textual.tools.base import ToolResult

MAX_CHARS = 8192

_BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.goog",
    "169.254.169.254",      # AWS/Azure IMDS
    "fd00:ec2::254",        # AWS IPv6 IMDS
    "168.63.129.16",        # Azure Wireserver
}


def _check_url(url: str) -> tuple[str | None, str | None]:
    """Validate *url* and return ``(error, safe_ip)``.

    Returns an error string if the URL is unsafe, otherwise returns
    ``(None, resolved_ip)`` so the caller can pin the connection to the
    already-validated IP (prevents DNS-rebinding / TOCTOU attacks).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Error: unsupported scheme '{parsed.scheme}'", None
    hostname = parsed.hostname
    if not hostname:
        return "Error: no hostname in URL", None
    if hostname in _BLOCKED_HOSTS:
        return f"Error: access denied — blocked host '{hostname}'", None
    try:
        safe_ip = None
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return "Error: access denied — private/internal IP", None
            if safe_ip is None:
                safe_ip = str(addr)
        if safe_ip is None:
            return f"Error: cannot resolve hostname '{hostname}'", None
        return None, safe_ip
    except socket.gaierror:
        return f"Error: cannot resolve hostname '{hostname}'", None


# Keep the old name as an alias for tests that import it directly
def _is_url_safe(url: str) -> str | None:
    err, _ = _check_url(url)
    return err


class _SafeTransport(httpx.AsyncHTTPTransport):
    """Transport that pins connections to a pre-resolved IP."""

    def __init__(self, pinned_ip: str, **kwargs):
        super().__init__(**kwargs)
        self._pinned_ip = pinned_ip

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Replace the hostname with the pinned IP in the URL while keeping
        # the Host header intact (httpx sets it from the original URL).
        url = request.url.copy_with(host=self._pinned_ip)
        request = httpx.Request(
            method=request.method,
            url=url,
            headers=request.headers,
            stream=request.stream,
            extensions=request.extensions,
        )
        return await super().handle_async_request(request)


async def web_fetch(url: str) -> ToolResult:
    """Fetch a URL via HTTP GET and return the response body.

    Response body is capped at 8 KB.  Private/internal URLs are blocked.
    DNS is resolved once and pinned to prevent rebinding attacks.
    """
    safety_err, safe_ip = _check_url(url)
    if safety_err:
        return ToolResult(output=safety_err, is_error=True)
    try:
        transport = _SafeTransport(pinned_ip=safe_ip)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=30) as client:
            response = await client.get(url)
        body = response.text
        truncated = ""
        if len(body) > MAX_CHARS:
            body = body[:MAX_CHARS]
            truncated = "\n[truncated]"
        return ToolResult(output=f"HTTP {response.status_code}\n{body}{truncated}")
    except Exception as exc:
        return ToolResult(output=f"Error fetching URL: {exc}", is_error=True)
