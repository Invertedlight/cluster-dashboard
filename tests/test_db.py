from app.db import qualify_database_url


def test_qualify_appends_trailing_dot_to_cluster_local_host():
    url = (
        "postgresql+psycopg://dashboard:s3cret@"
        "homelab-postgres-rw.database.svc.cluster.local:5432/dashboard"
    )
    qualified = qualify_database_url(url)
    assert "@homelab-postgres-rw.database.svc.cluster.local.:5432/" in qualified
    assert "s3cret" in qualified


def test_qualify_leaves_sqlite_and_already_fqdn_urls_alone():
    sqlite = "sqlite:////tmp/dash.db"
    assert qualify_database_url(sqlite) == sqlite
    already = (
        "postgresql+psycopg://u:p@homelab-postgres-rw.database.svc.cluster.local.:5432/db"
    )
    assert qualify_database_url(already) == already
