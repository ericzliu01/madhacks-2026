# Databricks App: demo dashboard + telemetry collector

Serves the planted-flaw "Taxi Ops" dashboard (v1 flawed, v2 fixed) and writes the SDK's events into the Volume that
`01b_bronze_load.sql` reads. This is the live piece: participants use the app, events flow to bronze -> silver -> gold.

## Status
- Collector logic: tested locally with a fake Files client (`python3 databricks/app/test/test_app.py`, 13 checks).
- **Not yet deployed or run on Databricks.** Untested there: the service-principal write, the app runtime start command,
  and whether the Plotly CDN script loads under the app's content-security policy.

## Build and deploy
```bash
./scripts/build-app.sh                       # copies the dashboard + SDK into databricks/app/static
```
1. Upload the `databricks/app/` folder to your workspace (Workspace -> Import, or the CLI).
2. Compute -> Apps -> Create app -> custom app, source = that workspace folder, then Deploy.
3. Give the app's **service principal** (shown on the app's page) access to the Volume, in the SQL editor:
   ```sql
   GRANT USE CATALOG ON CATALOG workspace TO `<service-principal-id>`;
   GRANT USE SCHEMA ON SCHEMA workspace.ux_telemetry TO `<service-principal-id>`;
   GRANT READ VOLUME ON VOLUME workspace.ux_telemetry.raw_events TO `<service-principal-id>`;
   GRANT WRITE VOLUME ON VOLUME workspace.ux_telemetry.raw_events TO `<service-principal-id>`;
   ```
   Use the **client_id** (a UUID) from the app's page or from `/status`'s `last_error`, not the display name. The Files API
   upload needs READ VOLUME as well as WRITE VOLUME (found on first deploy).
4. Open the app URL with study parameters: `?study=1&pid=P01&st=human&v=1` (or `v=2`).
   Participants need to be signed in to the workspace to open the app.
5. Re-run `01b_bronze_load.sql` (it skips files already in bronze), then `02`, `03`.
6. Debug: open `<app-url>/status` to see the sink, buffered/written counts, and the last upload error.

## Results page (`/results`)
Shows v1 vs v2 per task, the elements with rage/dead clicks, and the designer's proposals, read from the gold tables
through a SQL warehouse. Human and simulated rows are always shown separately and labeled. One-time setup:
1. App page -> Edit -> **App resources** -> Add resource -> **SQL warehouse**, pick your warehouse, permission
   **Can use**, resource key **`sql-warehouse`** (app.yaml reads it as `DATABRICKS_WAREHOUSE_ID`). Do this *before*
   deploying this version: app.yaml references the resource.
2. In the SQL editor (replace the UUID with your app's client_id):
   ```sql
   GRANT SELECT ON SCHEMA workspace.ux_telemetry TO `<client-id>`;
   ```
   (USE CATALOG and USE SCHEMA are already granted for the Volume.)
3. Redeploy and open `<app-url>/results`. Errors from the warehouse (e.g. PERMISSION_DENIED) are shown on the page.
   `/status` reports `"warehouse": true` once the resource is wired up.

Free Edition apps stop 24 hours after deploy: redeploy before demoing. Events buffer for `FLUSH_SECS` (3 s) before upload.

## Run locally (no Databricks)
```bash
./scripts/build-app.sh && python3 databricks/app/app.py     # http://127.0.0.1:8000/?study=1&pid=P01&st=human&v=1
```
Events go to `databricks/app/events/` as one JSONL file per flush. Set `EVENTS_VOLUME_PATH` to write to a Volume instead.
