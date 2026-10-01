import json
import sqlite3
from researchops_backend.storage.repository import Repository

def test_v16_database_migrates_without_losing_report(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY,question TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,progress INTEGER NOT NULL,error TEXT,request_json TEXT,result_json TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)')
        c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',('legacy','Old saved brief','completed','Completed',100,None,'{}','{"question":"Old saved brief"}','2026-09-30','2026-09-30'))
    repo=Repository(f'sqlite:///{path}')
    assert repo.get('legacy')['result']['question']=='Old saved brief'
    assert repo.get('legacy')['attempts']==0
    assert repo.list_recent()[0]['report_available']
    repo.engine.dispose()

def test_browser_report_import_is_idempotent(client):
    old={'research_id':'19cce0da-c633-4822-8443-04d0ed28d687','status':'completed',
        'question':'Old completed browser research','request':{'question':'Old completed browser research'},
        'result':{'research_id':'19cce0da-c633-4822-8443-04d0ed28d687','question':'Old completed browser research'}}
    assert client.post('/api/history/import',json={'jobs':[old]}).json()['imported']==1
    assert client.post('/api/history/import',json={'jobs':[old]}).json()['imported']==0

def test_import_validates_before_saving_and_ignores_unfinished(client,repo):
    old={'research_id':'19cce0da-c633-4822-8443-04d0ed28d687','status':'completed',
        'question':'Old completed browser research','result':{'question':'Old completed browser research'}}
    invalid={**old,'research_id':'not-an-id'}
    assert client.post('/api/history/import',json={'jobs':[old,invalid]}).status_code==422
    assert repo.count()==0
    assert client.post('/api/history/import',json={'jobs':[{'status':'running'}]}).json()['imported']==0

def test_completed_import_does_not_consume_research_capacity(client,repo):
    repo.s.max_active_jobs=1
    assert client.post('/api/research/run',json={'question':'One real active research job'}).status_code==202
    old={'research_id':'19cce0da-c633-4822-8443-04d0ed28d687','status':'completed',
        'question':'Old completed browser research','result':{'question':'Old completed browser research'}}
    assert client.post('/api/history/import',json={'jobs':[old]}).json()['imported']==1
