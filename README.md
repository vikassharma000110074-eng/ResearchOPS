# ResearchOps v1.9 — Vercel hosting and database

This version runs the website, FastAPI API, and durable Python research workflow on Vercel. History, saved reports, and resumable checkpoints use Neon PostgreSQL created and connected through Vercel Marketplace. Google Cloud Console is not needed. Gemini Developer API and Tavily remain the research providers, with their own credentials and quotas.

**Start with [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md).** It contains the dashboard deployment steps and environment-variable table. No live deployment is included in this ZIP.

## What changed

- Native `vercel.workflow` steps replace the separately hosted worker in production. One step runs one model operation or at most two parallel searches. Provider calls have a 60-second timeout; retries belong to the workflow.
- A browser refresh, New Chat, or closed tab does not stop accepted research. History restores the job and its real saved progress. Cancel and Retry use leases and a workflow generation to fence stale deliveries.
- Starts use an idempotency key. Retrying failed or cancelled research resumes saved stages. Finished jobs alone show 100% progress.
- Completed jobs clear temporary excerpts/checkpoints. Final reports retain verified findings, quotes, citations, source metadata, forecast/risk outputs, and Markdown. PDFs with vector charts are generated on demand, rather than stored as duplicate files.
- Standard depth and three tasks are the defaults; a new run can use three to five tasks. A 60-source cap, two active jobs, 100 saved jobs, a 350 MB database budget and 30 monthly starts/retries bound app usage. These are app guardrails, not provider allowances or a guarantee of a zero bill.
- History shows storage and monthly usage, exports completed reports to JSON, and offers permanent deletion after archiving. Archiving alone does not free storage. PostgreSQL may reuse deleted space before its reported file size decreases.
- Progress requests omit large checkpoints; History reads compact report summaries. Its background refresh pauses in hidden tabs and refreshes once per minute while visible. Close idle workspaces to let database compute suspend.
- Password access protects the workspace. All members with that password share the same History; this is a single workspace, not separate user accounts. API keys stay on the server.

## Runtime and files

| File/component | Purpose |
| --- | --- |
| `app.py` | Same-origin API and frontend fallback |
| `workflow.py` | Native Python workflow registry, steps, retries and cancellation |
| `backend/researchops_backend/units.py` | Restartable, bounded research units |
| `pyproject.toml` | Python 3.12, pinned dependencies, Vercel app/workflow discovery |
| `vercel.json` | FastAPI preset, Fluid compute, function duration, response headers |
| `frontend/` | Existing Three.js interface, New Chat, History, research trail and exports |
| `DEPLOY_VERCEL.md` | Dashboard setup, variables, verification and troubleshooting |
| `QA_NOTES.md` | What was tested and what remains to verify live |

The forecast preserves one-feature Ridge regression using its closed-form solution. Risk simulations use Python's standard library. ReportLab draws the PDF charts. NumPy, scikit-learn and Matplotlib are unnecessary in the deployment bundle. The local Vercel builder produced an API function and a namespace-specific workflow queue function, each approximately 138 MiB before upload.

## Local development

Use **Python 3.12**. On Windows run `setup.bat`, edit `.env`, then run `run_local.bat`; open `http://localhost:3000`. `run_demo.bat` provides an explicitly labelled offline demonstration. On Linux/macOS run `bash setup.sh`, edit `.env`, then `bash run_local.sh`.

The local worker and SQLite are development tools. Production validates PostgreSQL, durable workflow execution, a password and a session secret. It does not use local SQLite for persistent Vercel storage.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
npm ci
npm run test:ui
```

Tests use offline provider fixtures. They exercise the real workflow SDK's local queue, deterministic replay, transient retry and failure handling. They do not spend provider credits or deploy to an account.

## Evidence boundaries

Model-assisted verification requires matching excerpt quotes and applies a domain/authority heuristic. Different domains do not establish independent reporting. Confidence/readiness scores are heuristic evidence indicators. Forecasts are extrapolations or illustrative scenarios; P10/P90 are not calibrated prediction intervals. The default MapReduce engine is local parallel Python; this Vercel package does not run a Hadoop cluster.

See [MIGRATION.md](MIGRATION.md) for importing completed reports from older versions. Keep backups before changing a production deployment.
