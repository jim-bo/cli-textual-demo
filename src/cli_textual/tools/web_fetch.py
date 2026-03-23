import ipaddress
import socket
from urllib.parse import urljoin, urlparse

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


_MAX_REDIRECTS = 5


async def _safe_get(url: str) -> httpx.Response:
    """GET *url* with SSRF checks on every redirect hop.

    Each hop resolves DNS, validates the target, and pins the connection
    to the resolved IP with the correct ``sni_hostname`` for TLS.
    """
    for _ in range(_MAX_REDIRECTS):
        err, safe_ip = _check_url(url)
        if err:
            raise _SSRFBlocked(err)

        parsed = urlparse(url)
        original_host = parsed.hostname

        # Build a URL that connects to the pinned IP but preserves scheme/path/query
        pinned_url = parsed._replace(netloc=f"{safe_ip}:{parsed.port}" if parsed.port else safe_ip).geturl()

        # sni_hostname tells httpcore to use the original hostname for TLS SNI
        # and certificate verification instead of the pinned IP.
        extensions = {"sni_hostname": original_host} if parsed.scheme == "https" else {}

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                pinned_url,
                headers={"Host": original_host},
                extensions=extensions,
                follow_redirects=False,
            )

        if response.is_redirect:
            location = response.headers.get("location", "")
            if not location:
                break
            # Resolve relative redirects against the current URL
            url = urljoin(url, location)
            continue
        return response

    raise _SSRFBlocked("Error: too many redirects")


class _SSRFBlocked(Exception):
    pass


async def web_fetch(url: str) -> ToolResult:
    """Fetch a URL via HTTP GET and return the response body.

    Response body is capped at 8 KB.  Private/internal URLs are blocked.
    DNS is resolved and pinned per hop to prevent rebinding attacks.
    """
    try:
        response = await _safe_get(url)
        body = response.text
        truncated = ""
        if len(body) > MAX_CHARS:
            body = body[:MAX_CHARS]
            truncated = "\n[truncated]"
        return ToolResult(output=f"HTTP {response.status_code}\n{body}{truncated}")
    except _SSRFBlocked as exc:
        return ToolResult(output=str(exc), is_error=True)
    except Exception as exc:
        return ToolResult(output=f"Error fetching URL: {exc}", is_error=True)
