# Copy these files into Invertedlight/homelab-cluster, then encrypt secrets with sops.
#
# 1. Copy apps/base/cluster-dashboard and apps/staging/cluster-dashboard into the cluster repo.
# 2. Add `- cluster-dashboard` to apps/staging/kustomization.yaml resources.
# 3. Create CNPG role + database:
#    - Copy dashboard-database.yaml into apps/staging/database/
#    - Add it to apps/staging/database/kustomization.yaml resources
#    - Add a JSON6902 patch on homelab-postgres Cluster (see kustomization.database.example.yaml)
#    - Encrypt homelab-postgres-dashboard-secret.yaml and cluster-dashboard-database-secret.yaml
# 4. Build/push ghcr.io/invertedlight/cluster-dashboard:0.1.0 (GitHub Actions on main).
# 5. Flux path ./apps/staging already watches this overlay.
