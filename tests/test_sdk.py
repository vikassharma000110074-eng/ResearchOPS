import os
import subprocess
import sys
from pathlib import Path

def test_native_sdk_queue_and_replay(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env=os.environ|{'APP_ENV':'local','DEMO_MODE':'true','EXECUTION_MODE':'vercel-workflow',
        'DATA_DIR':str(tmp_path/'db'),'WORKFLOW_LOCAL_DATA_DIR':str(tmp_path/'workflow'),
        'WORKFLOW_TARGET_WORLD':'local','WORKSPACE_PASSWORD':'','SESSION_SECRET':''}
    env.pop('VERCEL_QUEUE_BASE_URL',None)
    result=subprocess.run([sys.executable,str(root/'tests/workflow_smoke.py')],cwd=root,env=env,text=True,capture_output=True,timeout=55)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert 'Native Workflow SDK smoke passed' in result.stdout
