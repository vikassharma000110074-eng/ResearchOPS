import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend'))

@pytest.fixture
def repo(tmp_path,monkeypatch):
    from researchops_backend.core.config import get_settings
    monkeypatch.setenv('APP_ENV','local');monkeypatch.setenv('DEMO_MODE','true')
    monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.setenv('DATABASE_URL',f'sqlite:///{tmp_path}/research.db')
    monkeypatch.setenv('WORKSPACE_PASSWORD','');monkeypatch.setenv('SESSION_SECRET','')
    monkeypatch.setenv('EXECUTION_MODE','local-worker')
    get_settings.cache_clear()
    from researchops_backend.storage.repository import Repository
    r=Repository()
    yield r
    r.engine.dispose();get_settings.cache_clear()

@pytest.fixture
def client(repo,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app,'s',repo.s)
    monkeypatch.setattr(app,'get_repo',lambda:repo)
    with TestClient(app.app) as c:yield c
