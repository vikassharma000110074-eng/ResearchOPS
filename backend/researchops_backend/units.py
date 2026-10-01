"""Bounded units: one model call or at most two parallel searches."""
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from researchops_backend.orchestrator import ResearchOrchestrator
from researchops_backend.storage.repository import Repository,LeaseLost,JobCancelled

# Must pass through the base engine's optional-expansion Exception handler.
class UnitComplete(BaseException):pass

class UnitOrchestrator(ResearchOrchestrator):
    def __init__(self,repo):
        super().__init__(repo)
        self.progress=repo.progress

    def _stage(self,rid,stage,progress):
        if progress>self.progress:
            super()._stage(rid,stage,progress)
            self.progress=progress

    def _cached(self,rid,key,action):
        value=self.repo.load_checkpoint(rid,key)
        if value is not None:return value
        value=action()
        self.repo.save_checkpoint(rid,key,value)
        raise UnitComplete()

    def _search_jobs(self,rid,jobs,search,profile):
        records=[];missing=[]
        for tid,query in jobs:
            key='search:'+hashlib.sha256((tid+':'+query).encode()).hexdigest()[:24]
            rows=self.repo.load_checkpoint(rid,key)
            if rows is None:missing.append((tid,query,key))
            else:records.append((tid,query,rows,None,key,True))
        if missing:
            def fetch(item):
                tid,query,key=item
                rows,error=search.search(query,profile['results_per_query'])
                return key,rows,error
            failure=None
            with ThreadPoolExecutor(max_workers=2) as pool:
                for key,rows,error in pool.map(fetch,missing[:2]):
                    if error:failure=error
                    else:self.repo.save_checkpoint(rid,key,rows)
            if failure:raise RuntimeError('Search provider failed: '+failure)
            cp=self.repo.checkpoints
            rows=[value for key,value in cp.items() if key.startswith('search:')]
            self.repo.update(rid,metrics_json=json.dumps({'search_queries_completed':len(rows),
                'unique_sources_discovered':len({x.get('url') for batch in rows for x in batch if x.get('url')})}))
            raise UnitComplete()
        return records

def process_unit(rid,generation,repo=None):
    repo=repo or Repository()
    existing=repo.get(rid,checkpoints=False)
    if not existing or existing['workflow_generation']!=generation:return 'stale'
    if existing['status'] in {'completed','failed','cancelled'}:return existing['status']
    owner=str(uuid.uuid4())
    job=repo.claim_unit(rid,generation,owner)
    if not job:return 'busy'
    try:
        UnitOrchestrator(repo.bound(rid,owner,job)).run(rid,job['request'])
        return 'completed'
    except UnitComplete:
        repo.release_unit(rid,owner,error=None)
        return 'running'
    except (LeaseLost,JobCancelled):return 'stale'
    except Exception:
        try:repo.release_unit(rid,owner)
        except (LeaseLost,JobCancelled):pass
        raise
