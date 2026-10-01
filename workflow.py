"""Vercel discovers this registry from [[tool.vercel.workflows]]."""
from vercel.workflow import Workflows,RetryableError,sleep

wf=Workflows(namespace='researchops')

def _backend_path():
    # Replay imports this module inside the deterministic sandbox. Filesystem
    # access and path setup belong in steps, never at registry import time.
    import sys
    from pathlib import Path
    path=str(Path(__file__).resolve().parent/'backend')
    if path not in sys.path:sys.path.insert(0,path)

@wf.step(max_retries=2)
async def run_research_unit(rid:str,generation:int)->str:
    _backend_path()
    import anyio
    from researchops_backend.units import process_unit
    from researchops_backend.storage.repository import Repository
    from researchops_backend.security import safe_error
    from researchops_backend.worker import retryable
    try:return await anyio.to_thread.run_sync(process_unit,rid,generation)
    except Exception as exc:
        error=safe_error(exc)
        if retryable(exc):raise RetryableError(error,retry_after='5s') from None
        Repository().fail_generation(rid,generation,error)
        return 'failed'

@wf.step(max_retries=2)
async def record_failure(rid:str,generation:int,error:str)->None:
    _backend_path()
    from researchops_backend.storage.repository import Repository
    Repository().fail_generation(rid,generation,error[:1500])

@wf.workflow
async def research_job(rid:str,generation:int)->str:
    # Only identifiers/statuses enter workflow storage. Long-lived research
    # excerpts, checkpoints and History remain in PostgreSQL.
    try:
        for _ in range(256):
            status=await run_research_unit(rid,generation)
            if status not in {'running','busy'}:return status
            if status=='busy':await sleep('10s')
        await record_failure(rid,generation,'Research step limit reached; retry saved stages after reviewing the brief.')
    except Exception:
        await record_failure(rid,generation,'Vercel workflow step failed or exhausted retries. Check Workflows logs and provider quotas, then retry saved stages.')
    return 'failed'
