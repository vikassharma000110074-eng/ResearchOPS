# Keep and import your previous reports

Keep the original ZIP, project folder and database as backups. v1.9 contains no user reports or real API keys.

## Browser or exported History

If the new deployment uses the same exact website origin as the old browser-history version, open History in the original browser and choose **Import old browser reports**. Completed reports are copied to PostgreSQL; existing IDs are skipped and browser originals remain.

For another origin, export reports as JSON from the old version when available, then choose **Import history JSON** in v1.9. The accepted shape is an array of completed jobs or an object with a `jobs` array. Each job needs a UUID `research_id`, `status: "completed"`, its request and a result object. v1.9's **Export completed history** includes archived completed reports, but not temporary checkpoints or incomplete jobs.

Imports are additive and preserve completed result content. Imported reports appear in active History. New/reused briefs in this version support at most five tasks. Old completed briefs exceeding that limit should use a three-to-five-task request in the import file; the already completed result can retain its original findings.

Import files may contain sensitive briefs and evidence. Store them privately. The workspace password grants access to all imported reports.

## SQLite or existing PostgreSQL

The repository adds missing columns without dropping existing jobs. Back up a local database before opening it with a new version. To copy completed local reports into a destination database, configure `.env` for that destination and run:

```bash
python scripts/migrate-sqlite-history.py /absolute/path/to/old/researchops.db
```

The script reads the original SQLite database without changing it and skips existing IDs. PostgreSQL is required on Vercel; keep SQLite for local development.

If you reconnect an existing compatible PostgreSQL database, completed reports remain available after migration. Finish or cancel old in-progress worker jobs before switching deployments: v1.9's production executor is a native Vercel Workflow, and existing externally scheduled executions are not automatically transferred. Retain the old deployment/database backup until imports are verified.

## Archive, restore and delete

Finished research can be archived and restored. Choose **Archived** in History, then **Restore**. To remove a report permanently, export completed History first, archive the finished job, and choose **Delete permanently**. This also removes its remaining checkpoints. The UI asks for confirmation and the operation cannot be undone.
