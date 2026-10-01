"""Independent worker process. The HTTP server never starts worker threads."""
import argparse
import json
import logging
import os
import sys
import threading
import time
import uuid
from researchops_backend.core.config import get_settings
from researchops_backend.storage.repository import Repository, LeaseLost, JobCancelled
from researchops_backend.security import safe_error

log = logging.getLogger('researchops.worker')


def retryable(exc):
    message = str(exc).lower()
    # Invalid credentials, model IDs, exhausted quotas and schema errors need
    # user action. Retrying them automatically wastes provider credits.
    if any(x in message for x in ['quota','rate limit','authentication','api key','not available','denied','validation']):
        return False
    return any(x in message for x in ['timeout','timed out','connection','503','502','500','unavailable','temporarily'])


def run_claimed(repo, job, runner_factory=None):
    rid, owner = job['id'], job['lease_owner']
    stop = threading.Event()
    def keep_lease():
        while not stop.wait(max(5, repo.s.lease_seconds // 3)):
            try:
                if not repo.heartbeat(rid, owner): break
                repo.worker_alive(owner)
            except Exception as exc:
                log.warning('Heartbeat failed: %s', safe_error(exc))
    thread = threading.Thread(target=keep_lease, daemon=True)
    thread.start()
    try:
        bound = repo.bound(rid, owner)
        if runner_factory is None:
            if get_settings().demo_mode:
                from researchops_backend.demo import DemoRunner
                runner_factory = DemoRunner
            else:
                from researchops_backend.orchestrator import ResearchOrchestrator
                runner_factory = ResearchOrchestrator
        runner_factory(bound).run(rid, job['request'])
        return False
    except (LeaseLost, JobCancelled):
        log.info('Job %s stopped: lease replaced or cancelled', rid)
        return False
    except Exception as exc:
        error = safe_error(exc)
        retry = retryable(exc) and job['attempts'] < repo.s.job_max_attempts
        try:
            repo.worker_update(rid, owner, status='queued' if retry else 'failed',
                stage='Temporary provider error; retry queued' if retry else 'Research stopped; retry available',
                error=error, lease_owner=None, lease_until=None)
        except (LeaseLost, JobCancelled):
            retry = False
        log.error('Job %s: %s', rid, error)
        return retry
    finally:
        stop.set()
        thread.join(timeout=2)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--job-id', default=os.getenv('RESEARCH_JOB_ID'))
    parser.add_argument('--once', action='store_true')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    s=get_settings()
    if s.validate_runtime():
        missing=', '.join(s.validate_runtime())
        log.error('Worker configuration required: %s', missing)
        if args.job_id:
            try:Repository().dispatch_failed(args.job_id, 'Worker configuration required: '+missing)
            except Exception:pass
        return 2
    if s.execution_mode!='local-worker':
        log.error('This worker is for local development. Vercel uses native Workflows.')
        return 2
    repo=Repository(); worker_id=str(uuid.uuid4())
    log.info('Independent ResearchOps worker ready (%s)', s.execution_mode)
    wait_deadline=time.time()+s.lease_seconds+10
    while True:
        repo.worker_alive(worker_id)
        repo.recover_exhausted()
        job=repo.claim(args.job_id, worker_id)
        if job:
            log.info('Research %s claimed, attempt %s', job['id'], job['attempts'])
            needs_retry=run_claimed(repo, job)
            if args.job_id:
                # Local retries use the same job ID. Successful
                # stage checkpoints survive the container and are reused.
                return 1 if needs_retry else 0
            if args.once:return 0
            if needs_retry:time.sleep(3)
        elif args.job_id:
            existing=repo.get(args.job_id)
            if not existing or existing['status'] in ['completed','failed','cancelled']:return 0
            if time.time()>wait_deadline:
                # Another live worker owns this delivery. Duplicate dispatches
                # do not run the research twice.
                return 0
            time.sleep(3)
        elif args.once:return 0
        else:time.sleep(2)


if __name__=='__main__':sys.exit(main())
