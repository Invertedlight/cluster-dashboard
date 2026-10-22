from sqlalchemy import inspect, select

from app import discovery
from app.models import Application
from tests.test_discovery import by_host, ing, session


def _seed(db, host, **kw):
    db.add(Application(slug=host.split(".")[0], name="Panel name", url=f"https://{host}",
                       hostname=host, description="Panel desc", source="manual", **kw))
    db.commit()


def test_migration_adds_columns(client):
    from app.db import get_engine

    cols = {c["name"] for c in inspect(get_engine()).get_columns("application")}
    assert {"name_locked", "description_locked"} <= cols


def test_name_lock_only(client):
    db = session()
    _seed(db, "n.jameshomelab.org", name_locked=True)
    discovery.reconcile(db, [ing("un", "n", "n", ["n.jameshomelab.org"], name="Ann", description="Ann d")])
    [app] = by_host(db, "n.jameshomelab.org")
    assert app.name == "Panel name" and app.description == "Ann d"


def test_description_lock_only(client):
    db = session()
    _seed(db, "dd.jameshomelab.org", description_locked=True)
    discovery.reconcile(db, [ing("ud", "d", "d", ["dd.jameshomelab.org"], name="Ann", description="Ann d")])
    [app] = by_host(db, "dd.jameshomelab.org")
    assert app.name == "Ann" and app.description == "Panel desc"


def test_unlocked_overwritten(client):
    db = session()
    _seed(db, "u.jameshomelab.org")
    discovery.reconcile(db, [ing("uu", "u", "u", ["u.jameshomelab.org"], name="Ann", description="Ann d")])
    [app] = by_host(db, "u.jameshomelab.org")
    assert (app.name, app.description, app.name_locked) == ("Ann", "Ann d", False)


def test_form_round_trip(client):
    r = client.post("/apps", data={"name": "Lockme", "url": "https://lockme.jameshomelab.org",
                                   "name_locked": "true"}, follow_redirects=False)
    assert r.status_code == 303
    db = session()
    [app] = by_host(db, "lockme.jameshomelab.org")
    assert app.name_locked and not app.description_locked
    page = client.get(f"/apps/{app.id}/edit").text
    assert "Use panel values" in page and 'name="name_locked" value="true" checked' in page
    client.post(f"/apps/{app.id}", data={"name": "Lockme", "url": app.url,
                                         "description_locked": "true"}, follow_redirects=False)
    db.expire_all()
    app = db.get(Application, app.id)
    assert not app.name_locked and app.description_locked
    bad = client.post(f"/apps/{app.id}", data={"name": "X", "url": "ftp://bad",
                                               "name_locked": "true"})
    assert bad.status_code == 400 and 'name="name_locked" value="true" checked' in bad.text


def test_blank_description_shows_placeholder(client):
    from app.db import get_session_factory
    from app.models import Application
    db = get_session_factory()()
    db.add(Application(slug="blank", name="Blank Panel", url="https://blank.jameshomelab.org",
                       hostname="blank.jameshomelab.org", description=None, source="manual",
                       sort_order=1, hidden=False))
    db.commit()
    html = client.get("/").text
    assert "No description yet" in html
    db.refresh(db.query(Application).filter_by(slug="blank").one())
    assert db.query(Application).filter_by(slug="blank").one().description is None
