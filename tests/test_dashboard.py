import re


def test_home_shows_seed_apps(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "Linkding" in body
    assert "Mealie" in body
    assert "Audiobookshelf" in body
    assert "Grafana" in body
    assert "lds.jameshomelab.org" in body
    assert "grs.jameshomelab.org" in body


def test_healthz(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").json()["status"] == "ready"


def test_add_hide_unhide_delete(client):
    created = client.post(
        "/apps",
        data={
            "name": "Paperless",
            "url": "https://paperless.jameshomelab.org",
            "description": "Docs",
            "sort_order": "50",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    home = client.get("/")
    assert "Paperless" in home.text

    ids = re.findall(r"/apps/([0-9a-f-]{36})/edit", home.text)
    paperless_id = ids[-1]

    bad = client.post(
        "/apps",
        data={"name": "Nope", "url": "https://example.com"},
        follow_redirects=False,
    )
    assert bad.status_code == 400

    hidden = client.post(f"/apps/{paperless_id}/hide", follow_redirects=False)
    assert hidden.status_code == 303
    assert "Paperless" not in client.get("/").text
    assert "Paperless" in client.get("/settings").text

    client.post(f"/apps/{paperless_id}/unhide", follow_redirects=False)
    assert "Paperless" in client.get("/").text

    client.post(f"/apps/{paperless_id}/delete", follow_redirects=False)
    assert "Paperless" not in client.get("/").text
