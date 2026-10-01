import asyncio
from types import SimpleNamespace
from researchops_backend.dispatch import dispatch_job

def test_local_dispatch(repo):
    assert asyncio.run(dispatch_job('fixture-id'))=='database-queue'

def test_workflow_dispatch_passes_only_identifiers(repo,monkeypatch):
    import vercel.workflow
    calls=[]
    async def start(workflow,*args):
        calls.append(args)
        return SimpleNamespace(run_id='wrun_fixture')
    monkeypatch.setattr(vercel.workflow,'start',start)
    repo.s.execution_mode='vercel-workflow'
    assert asyncio.run(dispatch_job('fixture-id',7))=='wrun_fixture'
    assert calls==[('fixture-id',7)]
