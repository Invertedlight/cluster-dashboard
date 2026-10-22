"""Local icon copies: fetch/validate image bytes so panels don't depend on outside sites.

SSRF policy (homelab): URLs whose host resolves to a loopback (127/8, ::1),
link-local (169.254/16 incl. cloud metadata, fe80::/10) or unspecified address
are refused, on every redirect hop. LAN/private ranges are allowed on purpose
so icons can come from other homelab services. Known gap: DNS could change
between the check and the connect (rebinding); acceptable for a single-user homelab.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_ICON_BYTES = 512 * 1024
FETCH_TIMEOUT = 10.0
MAX_REDIRECTS = 5
ALLOWED_MIME = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml", "image/x-icon",
}
_MIME_ALIASES = {"image/jpg": "image/jpeg", "image/vnd.microsoft.icon": "image/x-icon",
                 "image/ico": "image/x-icon"}


class IconError(ValueError):
    """User-facing reason a local icon could not be stored."""


def sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") or head.startswith(b"<!--")) and b"<svg" in head:
        return "image/svg+xml"
    return None


def _norm(ct: str | None) -> str | None:
    if not ct:
        return None
    ct = ct.split(";")[0].strip().lower()
    return _MIME_ALIASES.get(ct, ct)


def validate_icon(data: bytes, content_type: str | None) -> str:
    """Return the canonical mime type, or raise IconError."""
    if not data:
        raise IconError("The file is empty.")
    if len(data) > MAX_ICON_BYTES:
        raise IconError(f"The image is too big ({len(data) // 1024} KB). The limit is 512 KB.")
    declared = _norm(content_type)
    sniffed = sniff_mime(data)
    if sniffed is None:
        raise IconError("That isn't a supported image. Use PNG, JPEG, WebP, GIF, SVG or ICO.")
    # Generic types (octet-stream, missing) fall back to the sniffed type; a specific
    # declared type must agree with the file contents.
    if declared and declared not in ("application/octet-stream", "binary/octet-stream"):
        if declared not in ALLOWED_MIME:
            raise IconError(f"The server says this is '{declared}', which isn't a supported image type.")
        if declared != sniffed:
            raise IconError(f"The file says it is {declared} but its contents look like {sniffed}.")
    return sniffed


def check_host_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise IconError("The Icon URL must start with http:// or https://.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise IconError(f"Couldn't find the host '{parsed.hostname}'.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            raise IconError("That address points at this server or a link-local address, which isn't allowed.")


def fetch_icon(url: str, client: httpx.Client | None = None) -> tuple[bytes, str]:
    """Download an icon; returns (bytes, mime). Raises IconError with a friendly message."""
    url = (url or "").strip()
    if not url:
        raise IconError("Enter an Icon URL first, then press Save a local copy.")
    own = client is None
    client = client or httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=False,
                                    headers={"User-Agent": "cluster-dashboard-icon-fetch"})
    try:
        for _ in range(MAX_REDIRECTS + 1):
            check_host_allowed(url)
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    url = urljoin(url, resp.headers.get("location", ""))
                    continue
                if resp.status_code != 200:
                    raise IconError(f"The icon site answered with HTTP {resp.status_code}.")
                declared_len = resp.headers.get("content-length")
                if declared_len and declared_len.isdigit() and int(declared_len) > MAX_ICON_BYTES:
                    raise IconError(f"The image is too big ({int(declared_len) // 1024} KB). The limit is 512 KB.")
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_ICON_BYTES:
                        raise IconError("The image is too big. The limit is 512 KB.")
                data = bytes(buf)
                return data, validate_icon(data, resp.headers.get("content-type"))
        raise IconError("Too many redirects while fetching the icon.")
    except httpx.TimeoutException:
        raise IconError("The icon site took longer than 10 seconds to answer.") from None
    except httpx.HTTPError as exc:
        raise IconError(f"Couldn't download the icon: {exc.__class__.__name__}.") from None
    finally:
        if own:
            client.close()
