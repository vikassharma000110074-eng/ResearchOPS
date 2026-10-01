import pytest
from researchops_backend.core.config import Settings
from researchops_backend.security import safe_error

def test_workspace_authentication(client,repo):
    repo.s.workspace_password='test-workspace-password-32-characters'
    repo.s.session_secret='test-signing-secret-64-characters-never-used-outside-tests'
    assert client.get('/api/research').status_code==401
    assert client.post('/api/auth/login',json={'password':'wrong'}).status_code==401
    token=client.post('/api/auth/login',json={'password':repo.s.workspace_password}).json()['token']
    assert client.get('/api/research',headers={'Authorization':'Bearer '+token}).status_code==200
    assert client.get('/api/research',headers={'Authorization':'Bearer '+token+'x'}).status_code==401

def test_production_rejects_ephemeral_history_and_demo(monkeypatch):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('DEMO_MODE','true')
    monkeypatch.setenv('DATABASE_URL','sqlite:///temp.db');monkeypatch.setenv('WORKSPACE_PASSWORD','')
    monkeypatch.setenv('SESSION_SECRET','');monkeypatch.setenv('EXECUTION_MODE','local-worker')
    missing=Settings().validate_runtime()
    assert 'DATABASE_URL (PostgreSQL)' in missing
    assert 'DEMO_MODE must be false in production' in missing
    assert 'EXECUTION_MODE=vercel-workflow' in missing

def test_errors_redact_provider_keys(repo):
    repo.s.gemini_api_key='test-private-provider-value'
    assert 'test-private-provider-value' not in safe_error(RuntimeError('Key test-private-provider-value failed'))
