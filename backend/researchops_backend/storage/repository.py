"""Persistent queue, history and checkpoints; PostgreSQL in production, SQLite locally."""
import json
import time
import uuid
import zlib
import base64
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from sqlalchemy import (create_engine, MetaData, Table, Column, String, Text, Integer,
                        Float, select, update, insert, and_, or_, inspect, text, func)
from sqlalchemy.exc import IntegrityError
from researchops_backend.core.config import get_settings

def now_iso():return datetime.now(timezone.utc).isoformat()
class LeaseLost(RuntimeError):pass
class JobCancelled(RuntimeError):pass

class Repository:
    def __init__(self, database_url=None):
        self.s=get_settings()
        url=database_url or self.s.database_url
        self.engine=create_engine(url,pool_pre_ping=True,
            connect_args={'check_same_thread':False,'timeout':30} if url.startswith('sqlite') else {})
        self.meta=MetaData()
        self.jobs=Table('jobs',self.meta,
            Column('id',String(64),primary_key=True),Column('question',Text,nullable=False),
            Column('status',String(32),nullable=False),Column('stage',Text,nullable=False),
            Column('progress',Integer,nullable=False),Column('error',Text),
            Column('request_json',Text),Column('result_json',Text),
            Column('created_at',String(64),nullable=False),Column('updated_at',String(64),nullable=False),
            Column('attempts',Integer,nullable=False,server_default='0'),
            Column('cancel_requested',Integer,nullable=False,server_default='0'),
            Column('archived',Integer,nullable=False,server_default='0'),
            Column('lease_owner',String(64)),Column('lease_until',Float),Column('heartbeat_at',String(64)),
            Column('checkpoints_json',Text),Column('metrics_json',Text),
            Column('idempotency_key',String(100),unique=True),Column('dispatch_operation',Text),
            Column('checkpoint_keys_json',Text),Column('result_summary_json',Text),
            Column('workflow_generation',Integer,nullable=False,server_default='0'))
        self.workers=Table('worker_health',self.meta,
            Column('id',String(64),primary_key=True),Column('heartbeat',Float,nullable=False))
        self.usage=Table('monthly_usage',self.meta,Column('period',String(7),primary_key=True),Column('runs',Integer,nullable=False))
        with self.engine.begin() as c:
            if self.engine.dialect.name=='postgresql':c.execute(text('SELECT pg_advisory_xact_lock(184002)'))
            self.meta.create_all(c)
        additions={'attempts':'INTEGER NOT NULL DEFAULT 0','cancel_requested':'INTEGER NOT NULL DEFAULT 0',
            'archived':'INTEGER NOT NULL DEFAULT 0','lease_owner':'VARCHAR(64)','lease_until':'FLOAT',
            'heartbeat_at':'VARCHAR(64)','checkpoints_json':'TEXT','metrics_json':'TEXT',
            'idempotency_key':'VARCHAR(100)','dispatch_operation':'TEXT',
            'checkpoint_keys_json':'TEXT','result_summary_json':'TEXT',
            'workflow_generation':'INTEGER NOT NULL DEFAULT 0'}
        with self.engine.begin() as c:
            if self.engine.dialect.name=='postgresql':c.execute(text('SELECT pg_advisory_xact_lock(184002)'))
            existing={column['name'] for column in inspect(c).get_columns('jobs')}
            for name,decl in additions.items():
                if name not in existing:c.execute(text(f'ALTER TABLE jobs ADD COLUMN {name} {decl}'))
            c.execute(text('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)'))
            c.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency ON jobs(idempotency_key)'))

    @staticmethod
    def _decode(row):
        if row is None:return None
        d=dict(row._mapping);d['research_id']=d['id']
        for field in ['request','result','checkpoints','metrics']:
            raw=d.pop(field+'_json',None) or 'null'
            if field=='checkpoints' and raw.startswith('z:'):raw=zlib.decompress(base64.b64decode(raw[2:])).decode()
            d[field]=json.loads(raw)
        d['checkpoint_stages']=json.loads(d.pop('checkpoint_keys_json',None) or 'null') or list((d['checkpoints'] or {}).keys())
        d.pop('result_summary_json',None)
        return d

    @staticmethod
    def _summary(raw):
        result=json.loads(raw or '{}')
        return json.dumps({key:result.get(key) for key in ['metrics','decision_suggestion','research_quality','risk_assessment']})

    def create(self,rid,question,request,idempotency_key=None):
        timestamp=now_iso()
        values=dict(id=rid,question=question,status='queued',stage='Waiting for worker',progress=0,
            request_json=json.dumps(request),created_at=timestamp,updated_at=timestamp,
            checkpoints_json='{}',metrics_json='{}',idempotency_key=idempotency_key)
        try:
            with self.engine.begin() as c:
                if self.engine.dialect.name=='postgresql':c.execute(text('SELECT pg_advisory_xact_lock(184001)'))
                else:c.exec_driver_sql('BEGIN IMMEDIATE')
                if idempotency_key:
                    row=c.execute(select(self.jobs).where(self.jobs.c.idempotency_key==idempotency_key)).first()
                    if row:return self._decode(row),False
                active=c.execute(select(func.count()).select_from(self.jobs).where(self.jobs.c.status.in_(['queued','running']))).scalar()
                if active>=self.s.max_active_jobs:raise ValueError('Too many active research jobs. Wait for a job to finish or cancel one.')
                self._check_storage(c)
                self._reserve_run(c)
                c.execute(insert(self.jobs).values(**values))
        except IntegrityError:
            if not idempotency_key:raise
            with self.engine.connect() as c:
                row=c.execute(select(self.jobs).where(self.jobs.c.idempotency_key==idempotency_key)).first()
                if not row:raise
                return self._decode(row),False
        return self.get(rid),True

    def get(self,rid,include_archived=False,checkpoints=True):
        with self.engine.connect() as c:
            columns=list(self.jobs.c) if checkpoints else [column for column in self.jobs.c if column.name!='checkpoints_json']
            q=select(*columns).where(self.jobs.c.id==rid)
            if not include_archived:q=q.where(self.jobs.c.archived==0)
            return self._decode(c.execute(q).first())

    def update(self,rid,**kwargs):
        allowed={'status','stage','progress','error','result_json','metrics_json','dispatch_operation'}
        data={k:v for k,v in kwargs.items() if k in allowed};data['updated_at']=now_iso()
        if 'result_json' in data:data['result_summary_json']=self._summary(data['result_json'])
        with self.engine.begin() as c:c.execute(update(self.jobs).where(self.jobs.c.id==rid).values(**data))

    def set_dispatch(self,rid,generation,operation):
        with self.engine.begin() as c:
            return bool(c.execute(update(self.jobs).where(and_(self.jobs.c.id==rid,
                self.jobs.c.workflow_generation==generation,self.jobs.c.status.in_(['queued','running']))).values(dispatch_operation=operation)).rowcount)

    def dispatch_failed(self,rid,error,generation=0):
        with self.engine.begin() as c:
            c.execute(update(self.jobs).where(and_(self.jobs.c.id==rid,self.jobs.c.workflow_generation==generation,self.jobs.c.status=='queued')).values(
                status='failed',stage='Could not start worker',error=error,updated_at=now_iso()))

    def claim(self,rid=None,owner=None):
        owner=owner or str(uuid.uuid4());timestamp=time.time()
        eligible=and_(self.jobs.c.cancel_requested==0,self.jobs.c.archived==0,
            self.jobs.c.attempts<self.s.job_max_attempts,
            or_(self.jobs.c.status=='queued',and_(self.jobs.c.status=='running',self.jobs.c.lease_until<timestamp)))
        with self.engine.begin() as c:
            q=select(self.jobs).where(eligible).order_by(self.jobs.c.created_at).limit(1)
            if rid:q=q.where(self.jobs.c.id==rid)
            if self.engine.dialect.name=='postgresql':q=q.with_for_update(skip_locked=True)
            row=c.execute(q).first()
            if not row:return None
            job=self._decode(row)
            change=c.execute(update(self.jobs).where(and_(self.jobs.c.id==job['id'],eligible)).values(
                status='running',stage='Worker connected; resuming saved stages' if job['checkpoints'] else 'Worker connected',
                attempts=self.jobs.c.attempts+1,lease_owner=owner,lease_until=timestamp+self.s.lease_seconds,
                heartbeat_at=now_iso(),updated_at=now_iso(),error=None))
            if change.rowcount!=1:return None
        return self.get(job['id'])

    def heartbeat(self,rid,owner):
        with self.engine.begin() as c:
            return bool(c.execute(update(self.jobs).where(and_(self.jobs.c.id==rid,
                self.jobs.c.lease_owner==owner,self.jobs.c.status=='running')).values(
                lease_until=time.time()+self.s.lease_seconds,heartbeat_at=now_iso())).rowcount)

    def worker_update(self,rid,owner,**values):
        if 'result_json' in values:values['result_summary_json']=self._summary(values['result_json'])
        with self.engine.begin() as c:
            condition=and_(self.jobs.c.id==rid,self.jobs.c.lease_owner==owner,
                self.jobs.c.status=='running',self.jobs.c.lease_until>time.time())
            row=c.execute(select(self.jobs.c.cancel_requested).where(condition)).first()
            if not row:raise LeaseLost('Worker lease replaced or expired.')
            if row[0] and values.get('status')!='cancelled':raise JobCancelled('Research cancelled.')
            if values.get('status')=='completed' and self.s.execution_mode=='vercel-workflow':
                values['checkpoints_json']='{}'
                values['checkpoint_keys_json']='[]'
                values['lease_owner']=None;values['lease_until']=None
            values['updated_at']=now_iso()
            if not c.execute(update(self.jobs).where(condition).values(**values)).rowcount:raise LeaseLost('Worker lease replaced.')

    def checkpoint(self,rid,owner,key,value,checkpoints=None):
        if checkpoints is None:checkpoints=self.get(rid)['checkpoints'] or {}
        checkpoints=deepcopy(checkpoints);checkpoints[key]=value
        raw=json.dumps(checkpoints,ensure_ascii=False)
        if len(raw.encode())>6_000_000:raise ValueError('Research checkpoint limit reached. Reduce the number of sources.')
        if self.s.execution_mode=='vercel-workflow':raw='z:'+base64.b64encode(zlib.compress(raw.encode(),6)).decode()
        self.worker_update(rid,owner,checkpoints_json=raw,checkpoint_keys_json=json.dumps(list(checkpoints)))

    def claim_unit(self,rid,generation,owner):
        with self.engine.begin() as c:
            eligible=and_(self.jobs.c.id==rid,self.jobs.c.workflow_generation==generation,
                self.jobs.c.status.in_(['queued','running']),self.jobs.c.cancel_requested==0,
                or_(self.jobs.c.lease_owner.is_(None),self.jobs.c.lease_until<time.time()))
            changed=c.execute(update(self.jobs).where(eligible).values(status='running',
                lease_owner=owner,lease_until=time.time()+150,heartbeat_at=now_iso(),updated_at=now_iso(),attempts=1)).rowcount
        return self.get(rid) if changed else None

    def release_unit(self,rid,owner,**values):
        self.worker_update(rid,owner,lease_owner=None,lease_until=None,heartbeat_at=now_iso(),**values)

    def fail_generation(self,rid,generation,error):
        with self.engine.begin() as c:
            c.execute(update(self.jobs).where(and_(self.jobs.c.id==rid,
                self.jobs.c.workflow_generation==generation,self.jobs.c.status.in_(['queued','running']))).values(
                status='failed',stage='Workflow stopped; retry saved stages',error=error,
                lease_owner=None,lease_until=None,updated_at=now_iso()))

    def bound(self,rid,owner,job=None):return WorkerRepository(self,rid,owner,job)

    def request_cancel(self,rid):
        with self.engine.begin() as c:
            return bool(c.execute(update(self.jobs).where(and_(self.jobs.c.id==rid,
                self.jobs.c.status.in_(['queued','running']))).values(cancel_requested=1,
                status='cancelled',stage='Cancelled',lease_owner=None,lease_until=None,updated_at=now_iso())).rowcount)

    def requeue(self,rid):
        with self.engine.begin() as c:
            if self.engine.dialect.name=='postgresql':c.execute(text('SELECT pg_advisory_xact_lock(184001)'))
            else:c.exec_driver_sql('BEGIN IMMEDIATE')
            condition=and_(self.jobs.c.id==rid,self.jobs.c.status.in_(['failed','cancelled']),self.jobs.c.archived==0)
            if not c.execute(select(self.jobs.c.id).where(condition)).first():return False
            active=c.execute(select(func.count()).select_from(self.jobs).where(self.jobs.c.status.in_(['queued','running']))).scalar()
            if active>=self.s.max_active_jobs:raise ValueError('Too many active research jobs. Wait for a job to finish or cancel one.')
            self._check_storage(c,check_count=False)
            self._reserve_run(c)
            return bool(c.execute(update(self.jobs).where(condition).values(
                status='queued',stage='Retry queued; saved stages retained',error=None,cancel_requested=0,
                lease_owner=None,lease_until=None,attempts=0,workflow_generation=self.jobs.c.workflow_generation+1,
                dispatch_operation=None,updated_at=now_iso())).rowcount)

    def import_completed(self,rid,question,request,result):
        timestamp=now_iso()
        try:
            with self.engine.begin() as c:
                if self.engine.dialect.name=='postgresql':c.execute(text('SELECT pg_advisory_xact_lock(184001)'))
                else:c.exec_driver_sql('BEGIN IMMEDIATE')
                if c.execute(select(self.jobs.c.id).where(self.jobs.c.id==rid)).first():return False
                self._check_storage(c)
                c.execute(insert(self.jobs).values(id=rid,question=question,status='completed',
                    stage='Imported report',progress=100,request_json=json.dumps(request),
                    result_json=json.dumps(result),created_at=timestamp,updated_at=timestamp,
                    result_summary_json=self._summary(json.dumps(result)),
                    checkpoints_json='{}',metrics_json='{}'))
            return True
        except IntegrityError:
            if self.get(rid,include_archived=True):return False
            raise

    def recover_exhausted(self):
        # Show a concrete failure if a misconfigured worker never
        # connects, or platform retries stop before reconnecting. Manual retry
        # keeps all checkpoints. Live heartbeats always prevent this timeout.
        from datetime import timedelta
        if self.s.execution_mode=='vercel-workflow':
            stale=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
            with self.engine.begin() as c:
                c.execute(update(self.jobs).where(and_(self.jobs.c.status.in_(['queued','running']),
                    self.jobs.c.updated_at<stale)).values(status='failed',stage='Workflow inactive; retry saved stages',
                    error='No saved workflow progress for two hours. Check Vercel Workflows and usage limits, then retry.',
                    lease_owner=None,lease_until=None,updated_at=now_iso()))
            return
        stale=(datetime.now(timezone.utc)-timedelta(seconds=max(900,self.s.lease_seconds*4))).isoformat()
        with self.engine.begin() as c:
            c.execute(update(self.jobs).where(and_(self.jobs.c.status.in_(['queued','running']),
                or_(and_(self.jobs.c.status=='queued',self.jobs.c.updated_at<stale),
                    and_(self.jobs.c.status=='running',self.jobs.c.heartbeat_at<stale)))).values(
                    status='failed',stage='Worker did not reconnect; retry available',
                    error='Worker connection expired. Check worker deployment and credentials, then retry saved stages.',
                    lease_owner=None,lease_until=None,updated_at=now_iso()))
        with self.engine.begin() as c:
            c.execute(update(self.jobs).where(and_(self.jobs.c.status.in_(['queued','running']),
                self.jobs.c.attempts>=self.s.job_max_attempts,
                or_(self.jobs.c.lease_until<time.time(),self.jobs.c.lease_until.is_(None)))).values(
                status='failed',stage='Worker stopped; retry available',
                error='The worker stopped repeatedly. Saved stages are retained. Retry after checking deployment logs.',updated_at=now_iso()))

    def delete(self,rid):
        with self.engine.begin() as c:
            return bool(c.execute(update(self.jobs).where(and_(self.jobs.c.id==rid,
                self.jobs.c.status.in_(['completed','failed','cancelled']))).values(archived=1)).rowcount)

    def restore(self,rid):
        with self.engine.begin() as c:return bool(c.execute(update(self.jobs).where(self.jobs.c.id==rid).values(archived=0)).rowcount)

    def permanent_delete(self,rid):
        from sqlalchemy import delete
        with self.engine.begin() as c:
            return bool(c.execute(delete(self.jobs).where(and_(self.jobs.c.id==rid,self.jobs.c.archived==1,
                self.jobs.c.status.in_(['completed','failed','cancelled'])))).rowcount)

    def _check_storage(self,c,check_count=True):
        if check_count and c.execute(select(func.count()).select_from(self.jobs)).scalar()>=self.s.max_saved_jobs:
            raise ValueError('Saved report limit reached. Export and permanently delete an archived report to make space.')
        if self._storage_bytes(c)>=self.s.storage_budget_mb*1024*1024:
            raise ValueError('Database storage budget reached. Export and permanently delete archived reports, or adjust your database plan.')

    def _storage_bytes(self,c):
        if self.engine.dialect.name=='postgresql':return int(c.execute(text('SELECT pg_database_size(current_database())')).scalar())
        path=Path(self.engine.url.database)
        return sum(p.stat().st_size for p in [path,Path(str(path)+'-wal')] if p.exists())

    def _reserve_run(self,c):
        period=now_iso()[:7]
        row=c.execute(select(self.usage.c.runs).where(self.usage.c.period==period)).first()
        used=row[0] if row else 0
        if used>=self.s.max_monthly_runs:raise ValueError('Monthly research budget reached. Wait for the next month or adjust MAX_MONTHLY_RUNS after checking provider/Vercel quotas.')
        if row:c.execute(update(self.usage).where(self.usage.c.period==period).values(runs=used+1))
        else:c.execute(insert(self.usage).values(period=period,runs=1))

    def storage_summary(self):
        with self.engine.connect() as c:
            usage=c.execute(select(self.usage.c.runs).where(self.usage.c.period==now_iso()[:7])).scalar() or 0
            return {'database_bytes':self._storage_bytes(c),'budget_mb':self.s.storage_budget_mb,
                'saved_jobs':c.execute(select(func.count()).select_from(self.jobs)).scalar(),
                'max_saved_jobs':self.s.max_saved_jobs,'monthly_runs':usage,'max_monthly_runs':self.s.max_monthly_runs,
                'note':'Database size is an estimate; provider billing, compute and transfer quotas remain separate.'}

    def export_completed(self):
        with self.engine.connect() as c:
            rows=c.execute(select(self.jobs.c.id,self.jobs.c.question,self.jobs.c.request_json,self.jobs.c.result_json)
                .where(self.jobs.c.status=='completed').order_by(self.jobs.c.created_at)).all()
        return [{'research_id':r.id,'question':r.question,'status':'completed',
            'request':json.loads(r.request_json or '{}'),'result':json.loads(r.result_json or '{}')} for r in rows]

    def list_recent(self,limit=100,offset=0,status=None):
        columns=[column for column in self.jobs.c if column.name not in {'result_json','result_summary_json','checkpoints_json','lease_owner','lease_until','idempotency_key','dispatch_operation'}]
        # Older reports get their small summary populated once, on upgrade.
        with self.engine.begin() as c:
            old=c.execute(select(self.jobs.c.id,self.jobs.c.result_json).where(and_(self.jobs.c.result_json.is_not(None),self.jobs.c.result_summary_json.is_(None)))).all()
            for row in old:c.execute(update(self.jobs).where(self.jobs.c.id==row.id).values(result_summary_json=self._summary(row.result_json)))
        q=select(*columns,self.jobs.c.result_summary_json.label('result_json')).where(self.jobs.c.archived==int(status=='archived')).order_by(self.jobs.c.created_at.desc()).limit(min(limit,250)).offset(max(0,offset))
        if status and status not in {'all','archived'}:q=q.where(self.jobs.c.status==status)
        with self.engine.connect() as c:rows=c.execute(q).all()
        items=[]
        for row in rows:
            d=self._decode(row);req=d['request'] or {};result=d['result'] or {}
            decision=result.get('decision_suggestion') or {};quality=result.get('research_quality') or {}
            metrics=result.get('metrics') or {};risk=result.get('risk_assessment') or {}
            items.append({k:d[k] for k in ['research_id','question','status','stage','progress','error','created_at','updated_at','attempts','heartbeat_at']} | {
                'geography':req.get('geography'),'industry':req.get('industry'),
                'forecast_years':req.get('forecast_years',5),'research_mode':req.get('research_mode','Deep'),
                'decision_support':bool(req.get('include_decision_suggestion')),
                'decision_stance':decision.get('stance'),'decision_confidence':decision.get('confidence'),
                'readiness_score':quality.get('readiness_score'),'verified_findings':metrics.get('verified_findings'),
                'sources_retrieved':metrics.get('sources_retrieved'),'risk_score':risk.get('overall_score'),'archived':bool(d['archived']),
                'report_available':bool(result)})
        return items

    def count(self,status=None):
        q=select(func.count()).select_from(self.jobs).where(self.jobs.c.archived==int(status=='archived'))
        if status and status not in {'all','archived'}:q=q.where(self.jobs.c.status==status)
        with self.engine.connect() as c:return int(c.execute(q).scalar())

    def worker_alive(self,worker_id):
        with self.engine.begin() as c:
            changed=c.execute(update(self.workers).where(self.workers.c.id==worker_id).values(heartbeat=time.time())).rowcount
            if not changed:c.execute(insert(self.workers).values(id=worker_id,heartbeat=time.time()))

    def local_worker_online(self):
        with self.engine.connect() as c:
            return bool(c.execute(select(self.workers.c.id).where(self.workers.c.heartbeat>time.time()-60).limit(1)).first())

class WorkerRepository:
    def __init__(self,repo,rid,owner,job=None):
        self.repo,self.rid,self.owner=repo,rid,owner
        job=job or repo.get(rid)
        self.checkpoints=job['checkpoints'] or {}
        self.metrics=job['metrics'] or {}
        self.progress=job['progress']
    def update(self,rid,**values):
        if self.repo.s.execution_mode=='vercel-workflow' and 'metrics_json' in values:
            metrics=json.loads(values['metrics_json'])
            if metrics.get('search_queries_completed',0)<self.metrics.get('search_queries_completed',0):return
            if metrics==self.metrics:return
            self.metrics=metrics
        return self.repo.worker_update(rid,self.owner,**values)
    def load_checkpoint(self,rid,key):
        return deepcopy(self.checkpoints.get(key))
    def save_checkpoint(self,rid,key,value):
        self.repo.checkpoint(rid,self.owner,key,value,self.checkpoints)
        self.checkpoints[key]=deepcopy(value)
