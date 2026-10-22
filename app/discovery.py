"""Phase 2: ingress auto-discovery (reconcile loop).

Every DISCOVERY_INTERVAL_SECONDS the dashboard lists networking.k8s.io/v1
Ingresses cluster-wide and upserts an Application for each annotated host.
Rows are never deleted; hidden apps are block-listed and skipped.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, and_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Application, BlockedIdentity
from app.seed import slugify

log = logging.getLogger(__name__)

PREFIX = "dashboard.jameshomelab.org/"
SA_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"


@dataclass
class DiscoveredHost:
    cluster_uid: str
    namespace: str
    k8s_name: str
    hostname: str
    name: str  # annotation name, or the ingress name as a fallback for new panels
    name_annotated: bool
    description: str | None
    icon_url: str | None


def list_ingresses() -> list:
    """Return V1Ingress items from all namespaces (mocked in tests)."""
    from kubernetes import client, config

    config.load_incluster_config()
    return client.NetworkingV1Api().list_ingress_for_all_namespaces().items


def extract_hosts(ingresses: list, base_domain: str) -> list[DiscoveredHost]:
    found: list[DiscoveredHost] = []
    for ing in ingresses:
        meta = ing.metadata
        ann = meta.annotations or {}
        if ann.get(PREFIX + "enable", "").strip().lower() != "true":
            continue
        hosts: list[str] = []
        for rule in (ing.spec.rules or []) if ing.spec else []:
            h = (rule.host or "").strip().lower()
            if h and (h == base_domain or h.endswith("." + base_domain)) and h not in hosts:
                hosts.append(h)
        for host in hosts:
            uid = meta.uid if len(hosts) == 1 else f"{meta.uid}:{host}"
            found.append(
                DiscoveredHost(
                    cluster_uid=uid,
                    namespace=meta.namespace,
                    k8s_name=meta.name,
                    hostname=host,
                    name=(ann.get(PREFIX + "name") or "").strip() or meta.name,
                    name_annotated=bool((ann.get(PREFIX + "name") or "").strip()),
                    description=(ann.get(PREFIX + "description") or "").strip() or None,
                    icon_url=(ann.get(PREFIX + "icon") or "").strip() or None,
                )
            )
    return found


def _unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while db.scalar(select(Application.id).where(Application.slug == slug)) is not None:
        slug, n = f"{base}-{n}", n + 1
    return slug


def _is_blocked(db: Session, d: DiscoveredHost) -> bool:
    return db.scalar(
        select(BlockedIdentity.id).where(
            or_(
                BlockedIdentity.cluster_uid == d.cluster_uid,
                and_(
                    BlockedIdentity.namespace == d.namespace,
                    BlockedIdentity.k8s_name == d.k8s_name,
                ),
            )
        ).limit(1)
    ) is not None


def reconcile(db: Session, ingresses: list) -> dict[str, int]:
    """Idempotent upsert of discovered hosts. Returns counts for logging."""
    stats = {"added": 0, "updated": 0, "adopted": 0, "blocked": 0}
    now = datetime.now(UTC)
    for d in extract_hosts(ingresses, get_settings().base_domain):
        if _is_blocked(db, d):
            stats["blocked"] += 1
            continue
        app = db.scalar(select(Application).where(Application.cluster_uid == d.cluster_uid))
        if app is None:
            app = db.scalar(
                select(Application)
                .where(Application.hostname == d.hostname, Application.cluster_uid.is_(None))
                .limit(1)
            )
            if app is not None:
                stats["adopted"] += 1
        else:
            stats["updated"] += 1
        if app is None:
            app = Application(
                slug=_unique_slug(db, d.name), name=d.name, url=f"https://{d.hostname}",
                source="ingress", hidden=False, sort_order=100, open_in_new_tab=True,
            )
            db.add(app)
            stats["added"] += 1
        # An annotation wins when present; when missing, keep what the panel has
        # (e.g. text typed in the Add application form). User owns sort_order, hidden, icon.
        # "Use panel values" locks always win over annotations.
        if not app.name_locked and (d.name_annotated or not app.name):
            app.name = d.name
        if not app.description_locked and d.description is not None:
            app.description = d.description
        if d.icon_url and not app.icon_url:
            app.icon_url = d.icon_url
        app.url = f"https://{d.hostname}"
        app.hostname = d.hostname
        app.cluster_uid = d.cluster_uid
        app.namespace = d.namespace
        app.k8s_name = d.k8s_name
        app.source = "ingress"
        app.last_seen_at = now
        db.flush()
    db.commit()
    return stats


def discovery_enabled() -> bool:
    if os.environ.get("DISCOVERY_ENABLED", "true").strip().lower() in {"0", "false", "no"}:
        log.info("ingress discovery disabled by DISCOVERY_ENABLED")
        return False
    if not os.environ.get("KUBERNETES_SERVICE_HOST") or not os.path.exists(SA_TOKEN):
        log.info("ingress discovery disabled: not running in-cluster (no service account)")
        return False
    return True


def run_once() -> dict[str, int]:
    from app.db import get_session_factory

    db = get_session_factory()()
    try:
        return reconcile(db, list_ingresses())
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_loop(stop: threading.Event) -> None:
    """Blocking loop; run via asyncio.to_thread. Errors are logged, never fatal."""
    interval = max(5, int(os.environ.get("DISCOVERY_INTERVAL_SECONDS", "60")))
    log.info("ingress discovery started (every %ss)", interval)
    while not stop.is_set():
        try:
            stats = run_once()
            log.info("ingress discovery: %s", stats)
        except Exception:
            log.exception("ingress discovery pass failed")
        stop.wait(interval)
