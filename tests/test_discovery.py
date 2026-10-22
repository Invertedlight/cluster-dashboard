from types import SimpleNamespace as NS

from sqlalchemy import select

from app import discovery
from app.models import Application, BlockedIdentity

P = "dashboard.jameshomelab.org/"


def ing(uid, ns, k8s, hosts, **ann):
    a = {P + "enable": "true"} | {P + k: v for k, v in ann.items()}
    return NS(
        metadata=NS(uid=uid, namespace=ns, name=k8s, annotations=a),
        spec=NS(rules=[NS(host=h) for h in hosts]),
    )


def session():
    from app.db import get_session_factory

    return get_session_factory()()


def by_host(db, host):
    return db.scalars(select(Application).where(Application.hostname == host)).all()


def test_new_ingress_added(client):
    db = session()
    stats = discovery.reconcile(
        db, [ing("u1", "foo", "foo", ["foo.jameshomelab.org"], name="Foo", description="d", icon="https://i/x.png")]
    )
    assert stats["added"] == 1
    [app] = by_host(db, "foo.jameshomelab.org")
    assert (app.name, app.source, app.cluster_uid, app.url, app.icon_url) == (
        "Foo", "ingress", "u1", "https://foo.jameshomelab.org", "https://i/x.png")
    assert app.last_seen_at is not None
    # idempotent second pass
    assert discovery.reconcile(db, [ing("u1", "foo", "foo", ["foo.jameshomelab.org"], name="Foo")])["updated"] == 1
    assert len(by_host(db, "foo.jameshomelab.org")) == 1


def test_disabled_or_foreign_host_ignored(client):
    db = session()
    i = ing("u2", "a", "a", ["a.jameshomelab.org"])
    i.metadata.annotations[P + "enable"] = "false"
    discovery.reconcile(db, [i, ing("u3", "b", "b", ["b.example.com"])])
    assert not by_host(db, "a.jameshomelab.org") and not by_host(db, "b.example.com")


def test_adopts_manual_row_and_keeps_user_fields(client):
    db = session()
    db.add(Application(slug="manual-x", name="Old", url="https://x.jameshomelab.org",
                       hostname="x.jameshomelab.org", source="manual", sort_order=7,
                       icon_url="https://mine/icon.webp", hidden=False))
    db.commit()
    stats = discovery.reconcile(db, [ing("ux", "x", "x", ["x.jameshomelab.org"], name="New X", icon="https://ann/i.png")])
    assert stats["adopted"] == 1 and stats["added"] == 0
    [app] = by_host(db, "x.jameshomelab.org")
    assert app.cluster_uid == "ux" and app.source == "ingress" and app.name == "New X"
    assert app.sort_order == 7 and app.icon_url == "https://mine/icon.webp"


def test_blocked_skipped(client):
    db = session()
    db.add(BlockedIdentity(namespace="bl", k8s_name="bl"))
    db.commit()
    assert discovery.reconcile(db, [ing("ub", "bl", "bl", ["bl.jameshomelab.org"])])["blocked"] == 1
    assert not by_host(db, "bl.jameshomelab.org")


def test_multi_host(client):
    db = session()
    discovery.reconcile(db, [ing("um", "m", "m", ["m1.jameshomelab.org", "m2.jameshomelab.org"])])
    assert by_host(db, "m1.jameshomelab.org")[0].cluster_uid == "um:m1.jameshomelab.org"
    assert by_host(db, "m2.jameshomelab.org")[0].cluster_uid == "um:m2.jameshomelab.org"


def test_hide_blocks_and_unhide_unblocks(client):
    db = session()
    discovery.reconcile(db, [ing("uh", "h", "h", ["h.jameshomelab.org"])])
    [app] = by_host(db, "h.jameshomelab.org")
    client.post(f"/apps/{app.id}/hide", follow_redirects=False)
    db.expire_all()
    assert db.scalars(select(BlockedIdentity)).all()[0].cluster_uid == "uh"
    assert discovery.reconcile(db, [ing("uh", "h", "h", ["h.jameshomelab.org"])])["blocked"] == 1
    client.post(f"/apps/{app.id}/unhide", follow_redirects=False)
    db.expire_all()
    assert db.scalars(select(BlockedIdentity)).all() == []


def test_disabled_outside_cluster(monkeypatch):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    assert discovery.discovery_enabled() is False
    monkeypatch.setenv("DISCOVERY_ENABLED", "false")
    assert discovery.discovery_enabled() is False
