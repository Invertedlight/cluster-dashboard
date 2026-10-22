# Cluster dashboard

Phase 1 launcher for homelab apps on `*.jameshomelab.org`. FastAPI + Jinja2, PostgreSQL (CloudNativePG `homelab-postgres`), Traefik Ingress via the existing Cloudflare tunnel.

## What Phase 1 includes

- Home page cards for Linkding (`lds`), Mealie, Audiobookshelf (`abs`), and Grafana (`grs`)
- Add / edit / hide / delete
- Settings page to unhide apps
- Alembic migrations and seed on startup
- Kubernetes manifests under `gitops/` to copy into [homelab-cluster](https://github.com/Invertedlight/homelab-cluster)

Not in Phase 1: Ingress auto-discovery, block-list, health dots (discovery and block-list arrive in Phase 2, below).

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
- `cluster-dashboard-database` with `uri=postgresql+psycopg://dashboard:PASSWORD@homelab-postgres-rw.database.svc.cluster.local.:5432/dashboard`

## Phase 2: Ingress auto-discovery (0.2.0)

Every `DISCOVERY_INTERVAL_SECONDS` (default 60) the app lists `networking.k8s.io/v1` Ingresses in all namespaces and creates or updates a panel for each annotated host under `BASE_DOMAIN`. It runs in a background thread after the database bootstrap. Set `DISCOVERY_ENABLED=false` to turn it off; outside a cluster (no service account) it logs once and stays off.

Ingress annotations:

| Annotation | Required | Meaning |
|---|---|---|
| `dashboard.jameshomelab.org/enable: "true"` | yes | opt the Ingress in |
| `dashboard.jameshomelab.org/name` | no | panel name (default: Ingress name) |
| `dashboard.jameshomelab.org/description` | no | panel description |
| `dashboard.jameshomelab.org/icon` | no | icon URL, used only if the panel has no icon yet |

Rules:
- Panels are keyed by Ingress `metadata.uid` (`uid:host` when one Ingress has several hosts).
- An existing panel with the same hostname (e.g. added by hand) is adopted, not duplicated.
- A name or description annotation, when present, overwrites the panel's text; when missing, the panel keeps its existing text (e.g. typed in the Add application form). Your sort order, hidden flag and any icon you set are always kept.
- **Use panel values**: the edit/add form has two checkboxes, *Name* and *Description*. When ticked, discovery never changes that field, even if the Ingress has an annotation, so wording changes are a dashboard edit only (no Git push).
- Panels are never deleted when an Ingress disappears.
- Hiding an auto-added panel block-lists its Ingress; restoring it removes the block.

Required RBAC: a ServiceAccount bound to a ClusterRole allowing `get`, `list`, `watch` on `ingresses` in API group `networking.k8s.io` (cluster-wide), and the Deployment using that ServiceAccount.

## Edit login (0.4.0)

The home page, `/icons/*`, `/static/*`, `/healthz` and `/readyz` are public. Everything that
changes data (and the Add, Edit and Settings pages) needs a sign-in: password + 6-digit
authenticator (TOTP) code. Session cookie is signed, `Secure`, `HttpOnly`, `SameSite=Lax`, 12 h.
Every form carries a CSRF token. 5 failed sign-ins in 15 min locks that IP out for 15 min
(in memory, resets on restart).

Env vars (from the `cluster-dashboard-auth` Secret): `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`,
`SESSION_SECRET`, `TOTP_SECRET`. If any is missing, editing is disabled and a warning is logged.
Optional: `SESSION_MAX_AGE` (43200), `SESSION_COOKIE_SECURE` (true),
`TRUSTED_PROXIES` (`10.42.0.0/16,127.0.0.1/32`; only these peers may set
`CF-Connecting-IP` / `X-Forwarded-For`).

Make the values on your Mac (zsh):

```zsh
cd ~/src/cluster-dashboard   # wherever the repo is
python3 -m venv /tmp/dash-auth && /tmp/dash-auth/bin/python -m pip install bcrypt pyotp qrcode
/tmp/dash-auth/bin/python scripts/make_auth_secret.py --user james --verify
rm -rf /tmp/dash-auth
```
