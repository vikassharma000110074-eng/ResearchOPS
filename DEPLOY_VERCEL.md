# Deploy ResearchOps v1.9 through Vercel

Use a personal Vercel Hobby project for personal/noncommercial use. Vercel's Hobby terms restrict commercial use; business/team production may require another plan. This package is configured for the free-tier limits, but Vercel, Neon, Gemini and Tavily have independent allowances. Keep each service on its free plan and inspect usage before increasing the app budgets.

## 1. Upload the code to GitHub

1. Extract `ResearchOps_Vercel_V1_9.zip`.
2. Create a repository in your personal GitHub account.
3. Upload the **contents** of `ResearchOps_Vercel_V1_9`, so `app.py`, `workflow.py`, `pyproject.toml` and `vercel.json` are at the repository root. Upload the `backend` and `frontend` folders too.
4. Keep `.env`, databases, `.venv`, `node_modules`, and real keys out of GitHub. `.env.example` contains empty placeholders and can be included.

## 2. Create the Vercel project

1. Open [Vercel](https://vercel.com), choose **Add New → Project**, and import the repository.
2. Select your personal Hobby workspace.
3. Set **Framework Preset: FastAPI**. Set Root Directory to the directory containing `app.py` (normally the repository root).
4. Keep the framework's default Install Command, Build Command and Output Directory. Do not set `npm run build` or `frontend` as the Output Directory. Remove such overrides if reusing an older project.
5. Deploy once to create the project. Until its keys/database are configured, the app can show **Configuration required**. Research is disabled until setup is complete.

`pyproject.toml` declares the API as `app:app` and the workflow registry as `workflow:wf`. Vercel builds and subscribes the workflow function automatically; a separate process, cron job or external worker is unnecessary. `vercel.json` enables Fluid compute and requests a 300-second function duration. Individual provider operations are shorter than this limit.

## 3. Create the free database inside Vercel

1. Open the new project's **Storage** tab, choose **Create Database** (or Browse Marketplace), and select **Neon** PostgreSQL.
2. Choose the **Free** plan displayed by the integration. Review the displayed allowances; do not select a paid plan or an upgrade.
3. Choose a database region close to your Vercel function region and connect it to this project for **Production**. Use an isolated Preview database/branch if you enable Preview research.
4. Open **Settings → Environment Variables**. Confirm that a pooled PostgreSQL connection URL is available as `DATABASE_URL` or `POSTGRES_URL`—the app accepts either. If your integration uses a different variable prefix, copy its pooled connection value into `DATABASE_URL` privately in Vercel.

The database is provided by Neon through Vercel Marketplace. It is not Vercel's temporary function filesystem. You can manage the integration and browse the database from Vercel's dashboard. Tables are created automatically on the first configured startup; no manual SQL or Google Cloud Console setup is required.

Neon's September 2026 Free plan announcement lists **0.5 GB of database storage and 100 CU-hours per project**. The app's default 350 MB budget leaves margin for indexes, database overhead and temporary writes. Confirm the actual Marketplace plan when creating it; allowances can change.

## 4. Add environment variables

In **Project → Settings → Environment Variables**, add these for **Production**. Enable Preview only with appropriate separate keys/database. Values are strings.

| Name | Value |
| --- | --- |
| `DATABASE_URL` or `POSTGRES_URL` | Pooled Neon connection URL supplied by the integration; retain its SSL options |
| `GEMINI_API_KEY` | Your newly rotated Gemini Developer API key from Google AI Studio |
| `TAVILY_API_KEY` | Your newly rotated Tavily API key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite`, or a model available to your key and free quota |
| `WORKSPACE_PASSWORD` | A new random password, at least 16 characters |
| `SESSION_SECRET` | A separate random secret, at least 32 characters |
| `APP_ENV` | `production` |
| `EXECUTION_MODE` | `vercel-workflow` |
| `DEMO_MODE` | `false` |
| `HADOOP_MODE` | `local` |
| `VERCEL_FASTAPI_STATIC_CDN` | `1` (promotes public frontend assets to the CDN) |

Optional budgets already have these defaults:

| Name | Default |
| --- | ---: |
| `MAX_ACTIVE_JOBS` | `2` |
| `MAX_SAVED_JOBS` | `100` |
| `STORAGE_BUDGET_MB` | `350` |
| `MAX_MONTHLY_RUNS` | `30` |
| `ADAPTIVE_SOURCE_HARD_CAP` | `60` |
| `MAX_SOURCE_CHARS` | `6500` |
| `PROVIDER_TIMEOUT_SECONDS` | `60` |

Leave `GEMINI_FALLBACK_MODELS` empty. Workflow steps disable inline provider retries/fallbacks to remain bounded. Rotate keys exposed in earlier conversations; do not reuse them. You need Developer API keys, not Google Cloud service-account credentials.

To generate a password/secret locally, run `python scripts/generate-workspace-secrets.py` and paste each value privately into its corresponding Vercel variable. Alternatively generate equivalent values in a password manager. Do not paste secrets into chat or source code.

## 5. Redeploy and verify

1. Go to **Deployments**, open the latest deployment's menu, and choose **Redeploy**. New variables and database connections do not apply to an already running deployment.
2. Open `https://YOUR-PROJECT.vercel.app/api/health`. Expect `status: "ok"`, `execution_mode: "vercel-workflow"`, and `worker_status: "vercel-workflows"`.
3. Open the website, click **Connect**, and enter the workspace password. The workspace address is automatic.
4. Start one short **Standard / 3 tasks** research job. Confirm that progress advances and the job appears in History.
5. Refresh the browser while it runs, then reopen it from History. Confirm it finishes, reopens after another refresh, and downloads Markdown and PDF.
6. In Vercel's **Observability → Workflows**, inspect the run. Check Functions/Workflows usage and **Storage → Neon → Database** for persisted reports.
7. Export completed History as JSON before testing archive/permanent deletion. Archiving preserves data; deleting an archived report permanently removes it from this workspace. It does not immediately guarantee a smaller PostgreSQL file because deleted pages can be reused.

The UI's monthly budget counts new accepted starts and manual retries, including starts that fail after acceptance. Automated retries within a workflow do not count as new app starts. Month rollover uses UTC. There is no automatic deletion of completed reports.

## Free-tier boundaries and troubleshooting

- Vercel currently includes 50,000 Workflow events/month and 1 GB of Workflow data written on Hobby. Function compute, Queues, database compute/storage and provider credits are separate limits. This app keeps durable History in PostgreSQL; it does not depend on Hobby's short completed-workflow log retention.
- Check **Configuration required** details at `/api/health`; add the missing variable and redeploy.
- **Workflow dispatch failed:** check the deployment build, `[[tool.vercel.workflows]]`, Observability/Workflows and usage limits. The build should contain `_py_workflows/workflow__wf` with the `__researchops_wkf_workflow_*` queue trigger. Retry saved stages once the cause is fixed.
- **Gemini model unavailable / authentication / quota:** choose a model enabled for your AI Studio key, rotate the key, or wait for the provider quota reset. These failures remain visible in History.
- **Database connection:** confirm the integration is connected to this project's Production environment and that the pooled URL's SSL options remain intact.
- **Storage or saved-job limit:** export completed reports, archive finished jobs, and permanently delete those you no longer need. Use Neon/Vercel's database tooling to inspect space reclamation if the database size remains high. Keep the 350 MB margin rather than raising it near the plan limit.
- **No progress for two hours:** History marks the job as failed with Retry available. Check Workflows/Function logs and quotas before retrying. Retained checkpoints remain resumable.
- **UI assets served through the function:** verify `VERCEL_FASTAPI_STATIC_CDN=1`, keep `[tool.vercel.fastapi.static] cdn = true`, and redeploy. The same-origin frontend fallback still works if CDN collection is unavailable.

## Official references

Checked against current documentation on September 30, 2026:

- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
- [Vercel Workflows, including Python support](https://vercel.com/docs/workflows)
- [Workflow pricing and limits](https://vercel.com/docs/workflows/pricing)
- [Function limits](https://vercel.com/docs/functions/limitations)
- [Marketplace storage and database browser](https://vercel.com/docs/marketplace-storage)
- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)
- [Neon Free plan announcement](https://neon.com/blog/neon-backend-is-ga)
