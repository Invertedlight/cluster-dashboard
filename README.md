# Cluster dashboard

Phase 1 launcher for homelab apps on `*.jameshomelab.org`. FastAPI + Jinja2, PostgreSQL (CloudNativePG `homelab-postgres`), Traefik Ingress via the existing Cloudflare tunnel.

## What Phase 1 includes

- Home page cards for Linkding (`lds`), Mealie, Audiobookshelf (`abs`), and Grafana (`grs`)
- Add / edit / hide / delete
- Settings page to unhide apps
- Alembic migrations and seed on startup
- Kubernetes manifests under `gitops/` to copy into [homelab-cluster](https://github.com/Invertedlight/homelab-cluster)

Not in Phase 1: Ingress auto-discovery, block-list, health dots.

## Local run

PostgreSQL is required (no SQLite in the app).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export DATABASE_URL='postgresql+psycopg://dashboard:PASSWORD@127.0.0.1:5432/dashboard'
export SECRET_KEY='dev-secret'
uvicorn app.main:app --reload --port 8080
```

Open http://127.0.0.1:8080

Tests use a temporary SQLite file:

```bash
pytest
```

## Cluster deploy

1. Push this repo so GitHub Actions publishes `ghcr.io/invertedlight/cluster-dashboard`.
2. Follow `gitops/README.md`: copy overlays into `homelab-cluster`, add a CNPG `dashboard` role/database, SOPS-encrypt secrets, add `cluster-dashboard` to `apps/staging/kustomization.yaml`.
3. Ingress host: `https://home.jameshomelab.org` (wildcard tunnel already fronts Traefik).

Create the database role password once, then set both:

- `homelab-postgres-dashboard` (CNPG role password, namespace `database`)
- `cluster-dashboard-database` with `uri=postgresql+psycopg://dashboard:PASSWORD@homelab-postgres-rw.database.svc.cluster.local:5432/dashboard`
