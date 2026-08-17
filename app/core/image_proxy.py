"""Fetch a remote image on the browser's behalf.

Publisher CDNs commonly refuse cross-origin image loads from another site, so
`<img src="https://cdn.publisher/...">` renders nothing in the dashboard even
though the file is public. The server has no such problem.

The URL always comes from a document in the index, never from the caller, but
that alone is not enough: anyone able to write a document could point it at
`http://192.168.8.104:9200` and use this as a window into the network. So the
host is resolved and private ranges are rejected.
"""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Response

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 15

# A day: publisher images rarely change, and signed CDN urls expire anyway.
CACHE_CONTROL = "public, max-age=86400"


def _is_public_host(host: str) -> bool:
    """False for anything resolving into a private, loopback or link-local range."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


async def fetch_image(url: str) -> Response:
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=404, detail="URL gambar tidak valid")
    if not _is_public_host(parsed.hostname):
        # Deliberately the same 404 as a missing image: a different message
        # here would confirm which internal hosts exist.
        raise HTTPException(status_code=404, detail="Gambar tidak tersedia")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            upstream = await client.get(url)
        upstream.raise_for_status()
    except Exception:
        raise HTTPException(status_code=404, detail="Gambar tidak bisa diambil")

    content_type = upstream.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Bukan gambar")
    if len(upstream.content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Gambar terlalu besar")

    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": CACHE_CONTROL},
    )
