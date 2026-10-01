import json
import time
from sqlalchemy import select,update
from researchops_backend.units import process_unit
from researchops_backend.storage.repository import Repository,LeaseLost
from fixture_pipeline import patch_providers,FixtureLLM,FixtureSearch
import pytest

REQUEST={'question':'OFFLINE FIXTURE: should we launch a research platform?','max_tasks':3,'research_mode':'Standard',
    'forecast_years':5,'historical_data':[],'baseline_value':100,'include_decision_suggestion':True,'decision_style':'Balanced'}

def test_resumable_units_one_model_or_two_searches(repo,monkeypatch):
    patch_providers(monkeypatch);repo.s.execution_mode='vercel-workflow'
    searches=[];original=FixtureSearch.search
    def search(self,*args):searches.append(args);return original(self,*args)
    monkeypatch.setattr(FixtureSearch,'search',search)
    repo.create('bounded',REQUEST['question'],REQUEST)
    progress=0;units=0
    while units<80:
        # New repository instance on every delivery simulates isolated Functions.
        fresh=Repository(repo.s.database_url)
        before=len(FixtureLLM.calls);searched=len(searches)
        status=process_unit('bounded',0,fresh);units+=1
        assert len(FixtureLLM.calls)-before<=1
        assert len(searches)-searched<=2
        job=repo.get('bounded');assert job['progress']>=progress;progress=job['progress']
        fresh.engine.dispose()
        if status=='completed':break
        assert status=='running'
    assert status=='completed' and units>10
    assert job['result']['metrics']['verified_findings']==3
    assert job['checkpoints']=={} and job['progress']==100
    assert process_unit('bounded',0,repo)=='completed'
    assert len(FixtureLLM.calls)==10

def test_expansion_is_a_separate_unit(repo,monkeypatch):
    patch_providers(monkeypatch);repo.s.execution_mode='vercel-workflow'
    original=FixtureLLM.json
    def llm(self,instructions,prompt):
        if 'research-gap planner' in instructions:
            self.calls.append('expansion');return {'task_queries':{}}
        return original(self,instructions,prompt)
    monkeypatch.setattr(FixtureLLM,'json',llm)
    repo.create('deep',REQUEST['question'],REQUEST|{'research_mode':'Deep'})
    for _ in range(100):
        before=len(FixtureLLM.calls)
        status=process_unit('deep',0,repo)
        assert len(FixtureLLM.calls)-before<=1
        if status=='completed':break
    assert status=='completed' and 'expansion' in FixtureLLM.calls

def test_duplicate_delivery_and_retry_generation_fence(repo):
    repo.s.execution_mode='vercel-workflow';repo.create('fence',REQUEST['question'],REQUEST)
    first=repo.claim_unit('fence',0,'old')
    assert first and process_unit('fence',0,repo)=='busy'
    repo.bound('fence','old').save_checkpoint('fence','plan',{'tasks':[]})
    with repo.engine.connect() as c:
        assert c.execute(select(repo.jobs.c.checkpoints_json)).scalar().startswith('z:')
    assert repo.request_cancel('fence') and repo.requeue('fence')
    assert process_unit('fence',0,repo)=='stale'
    repo.dispatch_failed('fence','stale dispatch failure',0)
    assert repo.get('fence')['status']=='queued'
    assert not repo.set_dispatch('fence',0,'old-run')
    assert repo.claim_unit('fence',1,'new')
    with pytest.raises(LeaseLost):repo.bound('fence','old').update('fence',status='completed')

def test_monthly_limit_idempotency_and_retry(repo):
    repo.s.max_monthly_runs=1
    repo.create('quota',REQUEST['question'],REQUEST,'same')
    assert not repo.create('other',REQUEST['question'],REQUEST,'same')[1]
    repo.request_cancel('quota')
    with pytest.raises(ValueError,match='Monthly'):repo.requeue('quota')
    with pytest.raises(ValueError,match='Monthly'):repo.create('new',REQUEST['question'],REQUEST)
    assert repo.storage_summary()['monthly_runs']==1

def test_storage_export_and_archived_permanent_delete(client,repo):
    import uuid
    rid=str(uuid.uuid4())
    repo.import_completed(rid,REQUEST['question'],REQUEST,{'question':REQUEST['question'],'report_markdown':'Fixture'})
    exported=client.get('/api/history/export')
    assert exported.status_code==200 and len(exported.json()['jobs'])==1
    assert client.delete(f'/api/research/{rid}/permanent').status_code==409
    assert client.delete(f'/api/research/{rid}').status_code==200
    assert client.delete(f'/api/research/{rid}/permanent').json()['deleted']
    assert not repo.get(rid,include_archived=True)
    assert client.post('/api/history/import',json=exported.json()).status_code==200
    assert repo.get(rid)['result']['report_markdown']=='Fixture'
    assert client.get('/api/storage').json()['saved_jobs']==1
    repo.s.max_saved_jobs=1
    with pytest.raises(ValueError,match='Saved report limit'):repo.create('limit',REQUEST['question'],REQUEST)

def test_progress_does_not_read_large_checkpoints(repo):
    from sqlalchemy import event
    repo.create('light',REQUEST['question'],REQUEST)
    job=repo.claim_unit('light',0,'lease')
    repo.bound('light','lease').save_checkpoint('light','large',{'content':'fixture '*10000})
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):statements.append(statement)
    event.listen(repo.engine,'before_cursor_execute',capture)
    try:light=repo.get('light',checkpoints=False)
    finally:event.remove(repo.engine,'before_cursor_execute',capture)
    assert light['checkpoint_stages']==['large'] and light['checkpoints'] is None
    assert all('jobs.checkpoints_json' not in statement for statement in statements)

def test_storage_budget_rejects_start(client,repo,monkeypatch):
    monkeypatch.setattr(repo,'_storage_bytes',lambda c:350*1024*1024)
    response=client.post('/api/research/run',json=REQUEST)
    assert response.status_code==429 and 'storage budget' in response.json()['detail']
    assert repo.storage_summary()['monthly_runs']==0
