# cluster-dashboard

Python FastAPI app that shows cards linking to applications on the skynet homelab cluster.

## DevPod (skynet)

From M5:

```bash
devpod up github.com/Invertedlight/cluster-dashboard --ide cursor
```

Inside the workspace:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- App: port `8000` (forwarded by the devcontainer)
- Shared scratch PVC: `/scratch` (32TB DevStorage)

## Local (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
