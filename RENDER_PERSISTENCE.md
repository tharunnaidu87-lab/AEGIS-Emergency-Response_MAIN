# Render PostgreSQL persistence

AEGIS uses `DATABASE_URL` when it is present and otherwise uses project-local
SQLite for development. On Render, `DATABASE_URL` is mandatory: startup fails
instead of writing reports to the service's ephemeral filesystem.

## Render configuration

1. Create a Render Postgres database in the **same region and workspace** as the
   backend web service.
2. In the backend service's **Environment** page, add `DATABASE_URL` with the
   database's **Internal Database URL**. Do not paste it into source code or a
   committed `.env` file.
3. Optionally set `AEGIS_DB_POOL_SIZE=5`. The application clamps this value to
   1-10 connections.
4. Redeploy the backend. `/health` must return
   `"database_backend": "postgresql"`.

The application creates and additively upgrades its tables at startup. Reports,
tracking tokens, assignments, audit events, fusion groups, distress records,
intake previews, and report media are stored in PostgreSQL.

If a recoverable SQLite file contains data, migrate it from a trusted machine
using the Render database's **External Database URL** with `sslmode=require`:

```powershell
$env:DATABASE_URL = '<external URL ending in ?sslmode=require>'
backend/.venv/Scripts/python.exe scripts/migrate_sqlite_to_postgres.py --sqlite data/aegis.db
```

The migration does not change the SQLite source and aborts on conflicting IDs.
The report mentioned in the incident report cannot be reconstructed if its
ephemeral SQLite file has already been destroyed.

## Restart/redeploy proof

Create an inert zero-person persistence report:

```powershell
backend/.venv/Scripts/python.exe scripts/verify_render_persistence.py create --url https://YOUR-BACKEND.onrender.com
```

Restart or redeploy the backend from Render, wait for `/health`, then run:

```powershell
backend/.venv/Scripts/python.exe scripts/verify_render_persistence.py verify
```

Only the second command proves that the report survived a real restart.

Render's Free Postgres tier survives web-service restarts but currently expires
after 30 days, has a 1 GB limit, and provides no backups. It is appropriate for
a temporary demo. Long-term production retention requires a paid Render
Postgres plan or another maintained PostgreSQL service with backups.

