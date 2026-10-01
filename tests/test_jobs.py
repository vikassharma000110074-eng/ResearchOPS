import json
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import update
from researchops_backend.storage.repository import Repository,LeaseLost
from researchops_backend.worker import run_claimed

REQUEST={'question':'Should we launch a new research product?','max_tasks':3,'forecast_years':5,'research_mode':'Standard'}

def create(repo,rid='job-1',key=None):return repo.create(rid,REQUEST['question'],REQUEST,key)

def test_acceptance_does_not_run_research(client,repo):
    started=time.monotonic()
    response=client.post('/api/research/run',json=REQUEST,headers={'Idempotency-Key':'once'})
    assert response.status_code==202
    assert time.monotonic()-started<1.5
    job=response.json();assert job['status']=='queued' and job['progress']==0 and job['result'] is None
    assert client.get('/api/research').json()['items'][0]['research_id']==job['research_id']
    again=client.post('/api/research/run',json=REQUEST,headers={'Idempotency-Key':'once'})
    assert again.json()['research_id']==job['research_id'] and repo.count()==1

def test_only_one_worker_claims(repo):
    create(repo)
    with ThreadPoolExecutor(max_workers=6) as pool:
        claimed=list(pool.map(lambda i:repo.claim('job-1',f'worker-{i}'),range(6)))
    assert sum(x is not None for x in claimed)==1

def test_restart_reuses_checkpoint_and_fences_old_worker(repo):
    create(repo);first=repo.claim('job-1','first')
    repo.bound('job-1','first').save_checkpoint('job-1','plan',{'tasks':[1,2,3]})
    with repo.engine.begin() as c:c.execute(update(repo.jobs).where(repo.jobs.c.id=='job-1').values(lease_until=time.time()-1))
    other=Repository(repo.s.database_url);second=other.claim('job-1','second')
    assert second['attempts']==2 and second['checkpoints']['plan']['tasks']==[1,2,3]
    with pytest.raises(LeaseLost):repo.bound('job-1','first').update('job-1',stage='Bad stale write')
    other.engine.dispose()

def test_retry_keeps_last_progress_and_completed_stage(repo):
    create(repo);calls=[]
    class Runner:
        def __init__(self,bound):self.repo=bound
        def run(self,rid,request):
            if self.repo.load_checkpoint(rid,'stage1') is None:
                calls.append('expensive');self.repo.save_checkpoint(rid,'stage1',{'complete':True})
            self.repo.update(rid,stage='Stage 1 complete',progress=40)
            if len(calls)==1 and not self.repo.load_checkpoint(rid,'first_failed'):
                self.repo.save_checkpoint(rid,'first_failed',True);raise TimeoutError('Provider temporarily timed out')
            self.repo.update(rid,status='completed',stage='Completed',progress=100,result_json=json.dumps({'ok':True}))
    assert run_claimed(repo,repo.claim('job-1','first'),Runner) is True
    assert repo.get('job-1')['progress']==40 and repo.get('job-1')['status']=='queued'
    assert run_claimed(repo,repo.claim('job-1','second'),Runner) is False
    assert calls==['expensive'] and repo.get('job-1')['status']=='completed'

def test_cancel_retry_archive_restore(client,repo):
    rid=client.post('/api/research/run',json=REQUEST).json()['research_id']
    job=repo.claim(rid,'worker')
    repo.bound(rid,'worker').save_checkpoint(rid,'plan',{'ok':True})
    assert client.post(f'/api/research/{rid}/cancel').json()['status']=='cancelled'
    with pytest.raises(LeaseLost):repo.bound(rid,'worker').update(rid,status='completed',result_json='{}')
    assert client.post(f'/api/research/{rid}/retry').json()['status']=='queued'
    assert repo.get(rid)['checkpoints']['plan']=={'ok':True}
    assert client.delete(f'/api/research/{rid}').status_code==409
    client.post(f'/api/research/{rid}/cancel')
    assert client.delete(f'/api/research/{rid}').json()['archived']
    assert client.get('/api/research?status=archived').json()['total']==1
    assert client.post(f'/api/research/{rid}/restore').json()['status']=='cancelled'

def test_dispatch_failure_visible_in_history(client,monkeypatch):
    import app
    monkeypatch.setattr(app,'dispatch_job',lambda rid,generation:(_ for _ in ()).throw(RuntimeError('Workflow unavailable')))
    response=client.post('/api/research/run',json=REQUEST)
    assert response.status_code==202 and response.json()['status']=='failed'
    assert 'dispatch failed' in response.json()['error'].lower()
    assert client.get('/api/research').json()['items'][0]['status']=='failed'

def test_exhausted_worker_becomes_failed(repo):
    create(repo);repo.claim('job-1','worker')
    with repo.engine.begin() as c:c.execute(update(repo.jobs).where(repo.jobs.c.id=='job-1').values(attempts=3,lease_until=time.time()-1))
    repo.recover_exhausted();assert repo.get('job-1')['status']=='failed'

def test_queue_limit_and_whitespace_input(client,repo):
    repo.s.max_active_jobs=1
    assert client.post('/api/research/run',json=REQUEST).status_code==202
    assert client.post('/api/research/run',json=REQUEST).status_code==429
    assert client.post('/api/research/run',json={'question':' '*10}).status_code==422

def test_retry_cannot_bypass_active_job_limit(client,repo):
    repo.s.max_active_jobs=1
    rid=client.post('/api/research/run',json=REQUEST).json()['research_id']
    client.post(f'/api/research/{rid}/cancel')
    assert client.post('/api/research/run',json=REQUEST).status_code==202
    assert client.post(f'/api/research/{rid}/retry').status_code==429
    assert repo.get(rid)['status']=='cancelled'

def test_abandoned_queued_job_has_recoverable_error(repo):
    create(repo)
    with repo.engine.begin() as c:c.execute(update(repo.jobs).where(repo.jobs.c.id=='job-1').values(updated_at='2020-01-01T00:00:00+00:00'))
    repo.recover_exhausted()
    assert repo.get('job-1')['status']=='failed'
    assert repo.requeue('job-1')
