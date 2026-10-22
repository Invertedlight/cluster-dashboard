import io
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import inspect, select

from app import discovery, icons
from app.icons import IconError, fetch_icon
from app.models import Application
from tests.test_discovery import by_host, ing, session

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(icons.socket, "getaddrinfo",
                        lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _app(db, slug="ico", **kw):
    a = Application(slug=slug, name="Ico", url=f"https://{slug}.jameshomelab.org",
                    hostname=f"{slug}.jameshomelab.org", source="manual", **kw)
    db.add(a)
    db.commit()
    return a


def test_migration_adds_icon_columns(client):
    from app.db import get_engine

    cols = {c["name"] for c in inspect(get_engine()).get_columns("application")}
    assert {"icon_data", "icon_mime", "icon_updated_at"} <= cols


def test_fetch_success_follows_redirect():
    def h(req):
        if req.url.path == "/old.png":
            return httpx.Response(302, headers={"location": "/new.png"})
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    data, mime = fetch_icon("https://icons.example/old.png", client=_client(h))
    assert data == PNG and mime == "image/png"


def test_fetch_too_big():
    big = PNG + b"\x00" * (512 * 1024)
    h = lambda req: httpx.Response(200, content=big, headers={"content-type": "image/png"})
    with pytest.raises(IconError, match="too big"):
        fetch_icon("https://icons.example/x.png", client=_client(h))


def test_fetch_wrong_type():
    h = lambda req: httpx.Response(200, content=b"<html>nope</html>", headers={"content-type": "text/html"})
    with pytest.raises(IconError, match="supported image"):
        fetch_icon("https://icons.example/x.png", client=_client(h))


def test_fetch_content_type_mismatch():
    h = lambda req: httpx.Response(200, content=PNG, headers={"content-type": "image/gif"})
    with pytest.raises(IconError, match="contents look like image/png"):
        fetch_icon("https://icons.example/x.gif", client=_client(h))


@pytest.mark.parametrize("ip", ["127.0.0.1", "169.254.169.254", "::1", "fe80::1"])
def test_fetch_blocks_loopback_and_link_local(monkeypatch, ip):
    monkeypatch.setattr(icons.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (ip, 80))])
    with pytest.raises(IconError, match="isn't allowed"):
        fetch_icon("http://sneaky.example/x.png", client=_client(lambda r: httpx.Response(200)))


def test_fetch_allows_lan(monkeypatch):
    monkeypatch.setattr(icons.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("192.168.68.10", 80))])
    h = lambda req: httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    assert fetch_icon("http://lan.example/x.png", client=_client(h))[1] == "image/png"


def test_fetch_route_stores_copy(client, monkeypatch):
    db = session()
    a = _app(db)
    monkeypatch.setattr("app.routes.apps.fetch_icon", lambda url: (PNG, "image/png"))
    r = client.post(f"/apps/{a.id}/icon/fetch", data={"icon_url": "https://icons.example/i.png"},
                    follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    a = db.get(Application, a.id)
    assert a.icon_data == PNG and a.icon_mime == "image/png" and a.icon_updated_at
    assert a.icon_url == "https://icons.example/i.png"


def test_fetch_route_shows_error(client, monkeypatch):
    db = session()
    a = _app(db)
    def boom(url):
        raise IconError("The image is too big (600 KB). The limit is 512 KB.")
    monkeypatch.setattr("app.routes.apps.fetch_icon", boom)
    r = client.post(f"/apps/{a.id}/icon/fetch", data={"icon_url": "https://x/i.png"})
    assert r.status_code == 400 and "too big" in r.text


def test_upload_and_remove(client):
    db = session()
    a = _app(db)
    r = client.post(f"/apps/{a.id}/icon/upload",
                    files={"icon_file": ("i.svg", io.BytesIO(SVG), "image/svg+xml")},
                    follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert db.get(Application, a.id).icon_mime == "image/svg+xml"
    bad = client.post(f"/apps/{a.id}/icon/upload",
                      files={"icon_file": ("x.png", io.BytesIO(b"not an image"), "image/png")})
    assert bad.status_code == 400 and "supported image" in bad.text
    assert client.post(f"/apps/{a.id}/icon/remove", follow_redirects=False).status_code == 303
    db.expire_all()
    a = db.get(Application, a.id)
    assert a.icon_data is None and a.icon_mime is None and a.icon_updated_at is None


def test_serve_icon_headers(client):
    db = session()
    _app(db, slug="svgapp", icon_data=SVG, icon_mime="image/svg+xml",
         icon_updated_at=datetime(2026, 10, 21, tzinfo=timezone.utc))
    r = client.get("/icons/svgapp")
    assert r.status_code == 200 and r.content == SVG
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    etag = r.headers["etag"]
    assert client.get("/icons/svgapp", headers={"If-None-Match": etag}).status_code == 304
    assert client.get("/icons/does-not-exist").status_code == 404
    _app(db, slug="noicon")
    assert client.get("/icons/noicon").status_code == 404


def test_home_precedence(client):
    db = session()
    ts = datetime(2026, 10, 21, tzinfo=timezone.utc)
    _app(db, slug="both", icon_url="https://ext/both.png", icon_data=PNG, icon_mime="image/png", icon_updated_at=ts)
    _app(db, slug="urlonly", icon_url="https://ext/urlonly.png")
    html = client.get("/").text
    assert f'/icons/both?v={int(ts.timestamp())}' in html
    assert "https://ext/both.png" not in html
    assert "https://ext/urlonly.png" in html


def test_discovery_leaves_icon_columns_alone(client):
    db = session()
    ts = datetime(2026, 10, 21, tzinfo=timezone.utc)
    _app(db, slug="disc", icon_data=PNG, icon_mime="image/png", icon_updated_at=ts)
    discovery.reconcile(db, [ing("ud", "d", "d", ["disc.jameshomelab.org"], name="D", icon="https://ann/i.png")])
    db.expire_all()
    [a] = by_host(db, "disc.jameshomelab.org")
    assert a.source == "ingress"
    assert (a.icon_data, a.icon_mime, a.icon_version) == (PNG, "image/png", int(ts.timestamp()))
