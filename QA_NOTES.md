# ResearchOps v1.9 verification

Verified on September 30, 2026 in Linux with Python 3.12.14 and Node 24.19.0. Tests use explicitly simulated research evidence and do not validate real business conclusions.

## Passed

- **38 Python tests**, including durable acceptance and idempotency, concurrent claims, stale lease/generation fencing, cancellation, retained-stage retry, archive/restore/permanent deletion, storage/monthly budgets, export/import and previous-schema migration.
- Resumable research delivered through a new repository instance for every unit. Each invocation performs no more than one model operation or two searches; saved progress does not move backwards. Completed Vercel jobs clear checkpoints.
- A **real native Workflow SDK** run using its embedded Queue service and deterministic replay sandbox. A simulated timeout retried successfully; a simulated authentication failure persisted as a failed job in History. These were SDK runs, not direct calls to a mocked workflow wrapper.
- Full planning → retrieval → local MapReduce → extraction → exact-quote verification → conflict audit → synthesis → forecast/risk → decision → report pipeline with offline fixtures. Existing completed checkpoints prevent repeated successful model calls.
- Access checks reject incorrect passwords and modified tokens. Production requires PostgreSQL, rotated provider keys, workspace/password secrets and `vercel-workflow` execution. Known secrets and database URLs are redacted from displayed errors.
- Lightweight progress queries omit the checkpoint payload; checkpoint-stage names remain visible. History uses report summaries. Export includes completed reports; imports are additive and idempotent. Permanent deletion requires an archived finished job.
- Evidence checks reject fabricated supporting quotes and lookalike authority domains. Forecast checks cover annual-rate filtering, one-to-five-year horizons and historical-data Ridge regression. Risk scoring and simulations remain deterministic.
- Frontend **DOM simulation** verifies real saved progress, New Chat during a pending start, History actions, report reopen/reuse/refresh, cancellation, storage display, confirmation before permanent deletion, unassessed risk, forecast warnings and safe links.
- Fresh pinned production dependencies installed separately and imported successfully. Scientific libraries are absent from requirements; their previous functionality is implemented in standard Python and ReportLab.
- Official **@vercel/python 17.0.2** builder completed locally without signing into or modifying a Vercel account. It discovered the FastAPI API and `_py_workflows/workflow__wf`, attached the `__researchops_wkf_workflow_*` Queue trigger, and emitted public frontend assets for CDN serving when enabled. Both function bundles were about **138 MiB**, below the documented 500 MB Python limit. This validates build output, not a live account deployment.
- Python/JavaScript syntax and POSIX launcher syntax checked. Windows launchers require Python 3.12.
- Scenario and Ridge forecast PDFs generated from offline fixtures, rendered with Poppler, and visually inspected. Unicode fonts, ₹, risk/quality charts, forecast lines/tables, source register and page numbering render correctly. PDFs are generated on demand.

## Live checks still required

No Vercel deployment, Neon account or provider key was used or changed. After following DEPLOY_VERCEL.md, verify one short Standard job against your own database and credentials, including refresh/reopen and downloads. Hosted OIDC/Queues, PostgreSQL SSL/permissions, dashboard provisioning, account quotas and actual bills require that live check.

The frontend DOM simulation does not render CSS or WebGL. Actual Windows launchers, desktop layout, Android narrow-screen/touch behavior, and Three.js rendering still need device/browser checks after deployment. The browser available in this session could not reach the local preview server. The optional Hadoop implementation remains available for separate environments, but was not tested or deployed on Vercel.

The app budgets limit starts and estimated database size; they cannot guarantee that every independently metered provider remains within its free allowance. Consult each dashboard before increasing them.
