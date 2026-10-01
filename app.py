"""ResearchOps v1.9 API: accept jobs quickly, read durable status and history."""
import json
import os
import sys
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'backend'))

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from researchops_backend.core.config import get_settings
from researchops_backend.storage.repository import Repository
from researchops_backend.models.schemas import ResearchRequest
from researchops_backend.security import require_access, issue_session, safe_error
from researchops_backend.dispatch import dispatch_job


@lru_cache
def get_repo():return Repository()


@asynccontextmanager
async def lifespan(app):
    # Initialize database before readiness, so missing DATABASE_URL is visible.
    if s.environment=='local' or s.database_url.startswith('postgresql+psycopg://'):get_repo()
    yield


app=FastAPI(title='ResearchOps',version='1.9.0',lifespan=lifespan)
s=get_settings()
if s.cors_origins:
    app.add_middleware(CORSMiddleware,allow_origins=s.cors_origins,
        allow_credentials=False,allow_methods=['GET','POST','DELETE'],
        allow_headers=['Authorization','Content-Type','Idempotency-Key'])


@app.middleware('http')
async def response_headers(request,call_next):
    length=request.headers.get('content-length','0')
    if length.isdigit() and int(length)>12_000_000:return Response('Request too large',status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response


@app.get('/api/health')
def health():
    missing=s.validate_runtime()
    try:
        repo=get_repo(); repo.recover_exhausted()
        worker='vercel-workflows' if s.execution_mode=='vercel-workflow' else ('online' if repo.local_worker_online() else 'offline')
    except Exception:
        missing.append('Database connection');worker='unknown'
    return {'status':'configuration_required' if missing else 'ok','missing':missing,
        'version':app.version,'authentication_required':bool(s.workspace_password) or s.environment=='production',
        'execution_mode':s.execution_mode,'worker_status':worker,
        'history':'persistent-database','mapreduce_engine':s.hadoop_mode+'-mapreduce',
        'demo_mode':s.demo_mode}


class Login(BaseModel):password:str=Field(min_length=1,max_length=300)


@app.post('/api/auth/login')
def login(body:Login):return {'token':issue_session(body.password),'expires_in':86400}


def public_job(job):
    if not job:raise HTTPException(404,'Research not found.')
    return {k:job[k] for k in ['research_id','question','status','stage','progress','error',
        'request','result','created_at','updated_at','attempts','heartbeat_at','checkpoint_stages','metrics','cancel_requested']}


async def dispatch(repo,rid):
    generation=repo.get(rid,checkpoints=False)['workflow_generation']
    try:
        operation=await dispatch_job(rid,generation)
        accepted=repo.set_dispatch(rid,generation,operation)
        if not accepted and s.execution_mode=='vercel-workflow':
            from vercel.workflow import get_run
            await get_run(operation).terminate()
    except Exception as exc:
        repo.dispatch_failed(rid,'Vercel Workflow dispatch failed. Check deployment, Workflow configuration and usage limits. '+safe_error(exc),generation)
        # The accepted job remains in history with a real failure, not a spinner.


@app.post('/api/research/run',status_code=202,dependencies=[Depends(require_access)])
async def start_research(req:ResearchRequest,idempotency_key:str|None=Header(default=None,alias='Idempotency-Key')):
    missing=s.validate_runtime()
    if missing:raise HTTPException(503,'Configuration required: '+', '.join(missing))
    if idempotency_key and len(idempotency_key)>100:raise HTTPException(422,'Idempotency-Key is too long.')
    repo=get_repo()
    try:
        job,created=repo.create(str(uuid.uuid4()),req.question,req.model_dump(),idempotency_key)
    except ValueError as exc:raise HTTPException(429,str(exc))
    if created:await dispatch(repo,job['research_id'])
    return public_job(repo.get(job['research_id'],checkpoints=False))


@app.get('/api/research',dependencies=[Depends(require_access)])
def history(status:str=Query(default='all',pattern='^(all|queued|running|completed|failed|cancelled|archived)$'),
            limit:int=Query(default=100,ge=1,le=250),offset:int=Query(default=0,ge=0)):
    repo=get_repo();repo.recover_exhausted()
    return {'items':repo.list_recent(limit,offset,status),'total':repo.count(status),'limit':limit,'offset':offset}


@app.get('/api/research/{rid}',dependencies=[Depends(require_access)])
def research(rid:str):
    repo=get_repo();repo.recover_exhausted()
    return public_job(repo.get(rid,checkpoints=False))


@app.post('/api/research/{rid}/cancel',dependencies=[Depends(require_access)])
async def cancel(rid:str):
    repo=get_repo()
    if not repo.request_cancel(rid):raise HTTPException(409,'Only queued or running research can be cancelled.')
    operation=repo.get(rid,checkpoints=False).get('dispatch_operation')
    if operation and s.execution_mode=='vercel-workflow':
        try:
            from vercel.workflow import get_run
            await get_run(operation).terminate()
        except Exception:pass # DB fencing prevents cancelled deliveries from saving.
    return public_job(repo.get(rid,checkpoints=False))


@app.post('/api/research/{rid}/retry',status_code=202,dependencies=[Depends(require_access)])
async def retry(rid:str):
    repo=get_repo()
    if s.validate_runtime():raise HTTPException(503,'Configuration required: '+', '.join(s.validate_runtime()))
    try:queued=repo.requeue(rid)
    except ValueError as exc:raise HTTPException(429,str(exc))
    if not queued:raise HTTPException(409,'Only failed or cancelled research can be retried.')
    await dispatch(repo,rid)
    return public_job(repo.get(rid,checkpoints=False))


@app.delete('/api/research/{rid}',dependencies=[Depends(require_access)])
def archive(rid:str):
    if not get_repo().delete(rid):raise HTTPException(409,'Only finished research can be archived.')
    return {'archived':True,'research_id':rid}


@app.post('/api/research/{rid}/restore',dependencies=[Depends(require_access)])
def restore(rid:str):
    if not get_repo().restore(rid):raise HTTPException(404,'Research not found.')
    return public_job(get_repo().get(rid,checkpoints=False))

@app.delete('/api/research/{rid}/permanent',dependencies=[Depends(require_access)])
def permanent_delete(rid:str):
    if not get_repo().permanent_delete(rid):raise HTTPException(409,'Archive a finished report before permanently deleting it.')
    return {'deleted':True,'research_id':rid}

@app.get('/api/storage',dependencies=[Depends(require_access)])
def storage():return get_repo().storage_summary()

@app.get('/api/history/export',dependencies=[Depends(require_access)])
def export_history():
    return Response(json.dumps({'version':'1.9','jobs':get_repo().export_completed()}),media_type='application/json',
        headers={'Content-Disposition':'attachment; filename="ResearchOps_History.json"'})


@app.get('/api/research/{rid}/report.pdf',dependencies=[Depends(require_access)])
def pdf(rid:str):
    job=get_repo().get(rid,checkpoints=False)
    if not job or not job.get('result'):raise HTTPException(409,'The report is not ready.')
    from researchops_backend.reporting.pdf_report import build_pdf_report
    try:data=build_pdf_report(job['result'])
    except Exception as exc:raise HTTPException(500,safe_error(exc))
    return Response(data,media_type='application/pdf',headers={
        'Content-Disposition':f'attachment; filename="ResearchOps_{rid[:8]}.pdf"'})


class ImportHistory(BaseModel):
    jobs:list[dict[str,Any]]=Field(max_length=50)


@app.post('/api/history/import',dependencies=[Depends(require_access)])
def import_history(payload:ImportHistory):
    repo=get_repo();imported=0;prepared=[]
    for index,old in enumerate(payload.jobs):
        # Import completed browser reports only; an in-flight browser request is
        # not a durable job and cannot be resumed from the old prototype.
        if old.get('status')!='completed' or not old.get('result'):continue
        try:
            result=old['result'];request=dict(old.get('request') or {})
            if not isinstance(result,dict):raise ValueError('Report must be an object.')
            request['question']=request.get('question') or result.get('question') or old.get('question') or 'Imported research'
            parsed=ResearchRequest.model_validate(request)
            rid=str(uuid.UUID(str(old['research_id'])))
        except (ValidationError,ValueError,KeyError,TypeError):
            raise HTTPException(422,f'Imported job {index+1} has an invalid ID, brief, or report.')
        prepared.append((rid,parsed,result))
    for rid,parsed,result in prepared:
        try:
            if repo.import_completed(rid,parsed.question,parsed.model_dump(),result):imported+=1
        except ValueError as exc:raise HTTPException(429,str(exc))
    return {'imported':imported}


app.mount('/',StaticFiles(directory=str(ROOT/'frontend'),html=True),name='frontend')
