"""Dispatch only. Research never runs in the API request."""
from researchops_backend.core.config import get_settings

async def dispatch_job(research_id,generation=0):
    s=get_settings()
    if s.execution_mode=='local-worker':return 'database-queue'
    from vercel.workflow import start
    from workflow import research_job
    run=await start(research_job,research_id,generation)
    return run.run_id
