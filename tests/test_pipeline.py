import json
from fixture_pipeline import patch_providers,FixtureLLM
from researchops_backend.orchestrator import ResearchOrchestrator
from researchops_backend.reporting.pdf_report import build_pdf_report

def test_full_pipeline_and_checkpoint_replay(repo,monkeypatch):
    patch_providers(monkeypatch)
    request={'question':'OFFLINE FIXTURE: should we launch a research platform?','max_tasks':3,'research_mode':'Standard',
        'forecast_years':5,'historical_data':[],'baseline_value':100,'include_decision_suggestion':True,'decision_style':'Balanced'}
    repo.create('fixture-job',request['question'],request)
    job=repo.claim('fixture-job','first')
    ResearchOrchestrator(repo.bound(job['id'],job['lease_owner'])).run(job['id'],request)
    result=repo.get(job['id'])['result']
    assert result['metrics']['verified_findings']==3
    assert result['decision_suggestion']['enabled'] and result['decision_suggestion']['action_plan']
    assert result['forecast']['method']=='evidence-based-scenario'
    assert result['source_catalog'] and result['verified_findings'][0]['supporting_quotes']
    assert 'Source Register' in result['report_markdown']
    pdf=build_pdf_report(result);assert pdf.startswith(b'%PDF') and len(pdf)>5000
    calls=len(FixtureLLM.calls)
    repo.update(job['id'],status='failed',stage='Simulated interrupted completion')
    assert repo.requeue(job['id'])
    second=repo.claim(job['id'],'second')
    ResearchOrchestrator(repo.bound(second['id'],'second')).run(second['id'],request)
    assert len(FixtureLLM.calls)==calls
    assert repo.get(job['id'])['status']=='completed'
