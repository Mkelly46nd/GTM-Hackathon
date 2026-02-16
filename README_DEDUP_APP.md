# Dedup App Shell

MVP web app for running the contact/company deduplication engines, reviewing matches and clusters, approving items, and exporting to CSV or webhooks (Clay, n8n).

## Run on Replit

1. **Import** the repo on [Replit](https://replit.com) (Import from GitHub).
2. Click **Run**. The first run will install backend and frontend dependencies, start the FastAPI API on port 5000, then start the Next.js app on Replit’s assigned port.
3. Open the **Webview** (or the URL Replit shows). You should see the app at `/runs`; upload a CSV and run dedup as usual.

No extra config is needed. The app uses relative `/api` URLs and Next.js proxies `/api` to the backend. Optional: add Secrets for `CLAY_WEBHOOK_URL` and `N8N_WEBHOOK_URL` if you use those exports.

## Local setup

### Backend (FastAPI + SQLite)

1. From the **repo root** (GTM-Hackathon):

   ```bash
   pip install -r server/requirements.txt
   ```

2. Optional: copy `server/.env.example` to `server/.env` and set:
   - `DATABASE_URL` (default: SQLite at `server/dedup.db`)
   - `CLAY_WEBHOOK_URL` (for "Send to Clay")
   - `N8N_WEBHOOK_URL` (for "Trigger n8n")

3. Start the API (must run from repo root so engines are importable):

   ```bash
   uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
   ```

   API base: `http://localhost:8000/api`

### Frontend (Next.js)

1. From the repo root:

   ```bash
   cd web
   npm install
   ```

2. For local dev, create `web/.env.local` with:

   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

   (If you omit this, the frontend uses relative `/api` URLs, which only work when the Next.js dev server is proxying to the backend, e.g. on Replit.)

3. Start the dev server:

   ```bash
   npm run dev
   ```

   Open http://localhost:3000 (home redirects to `/runs`).

## Flow

1. **Create a run**  
   On `/runs`, choose entity type (contact or company), upload a **CSV file** (the app reads CSV only; JSON is not accepted for run input), and click "Run dedup". The server runs the engine synchronously and persists entities, matches, and clusters.

2. **Review matches**  
   Open a run and go to "Review matches". Filter by score band (High/Medium/Low) and status (Unreviewed/Approved/Rejected). For each pair you see entity A vs B, score, top reasons, and recommended survivor. Use **Approve** or **Reject**.

3. **Clusters**  
   Under "Clusters", open a cluster to see all members, the recommended survivor, and pairwise matches. Use **Approve entire cluster** to mark all matches in that cluster as approved.

4. **Activation**  
   Under "Export and webhooks", export approved survivors:
   - **Export CSV**: download a CSV of approved survivor records.
   - **Send to Clay**: POST payload to `CLAY_WEBHOOK_URL` (if set).
   - **Trigger n8n**: POST payload to `N8N_WEBHOOK_URL` (if set).

Approved survivors are those that are the recommended survivor of at least one approved match (or the cluster recommended survivor when that cluster has at least one approved match).

## Sample CSV

For **contacts**, the engine expects columns such as: Record ID (or hs_object_id), First Name, Last Name, Email, Company Name, Job Title, etc. HubSpot CSV exports and the existing `contacts-for-clay.csv` in the repo are compatible.

For **companies**, use a CSV with company columns (e.g. Record ID, Company name, Company Domain Name, Website, etc.). See `company_deduplication_engine.py` for the default column mapping.

A minimal contact CSV to test duplicates:

```csv
Record ID,First Name,Last Name,Email,Company Name
1,Jane,Doe,jane@acme.com,Acme Inc
2,Jane,Doe,jane.doe@acme.com,Acme Inc
3,John,Smith,john@acme.com,Acme Inc
```

Rows 1 and 2 should be detected as a duplicate pair (same name + company, different email variants).

## Tech

- **Server**: FastAPI, SQLAlchemy (SQLite), existing Python dedup engines (contact_deduplication_engine.py, company_deduplication_engine.py).
- **Web**: Next.js 14 (App Router), TypeScript, Tailwind, Zod for API response validation.
- **Monorepo**: `server/` and `web/`; engines remain at repo root.
