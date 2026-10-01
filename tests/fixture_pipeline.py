"""Deterministic provider fixtures; these are NOT real research evidence."""
import hashlib
import json

QUOTE='The illustrative market CAGR is 10% annually.'

class FixtureLLM:
    calls=[]
    def json(self,instructions,prompt):
        self.calls.append(instructions[:40])
        if 'planning component' in instructions:
            return {'decision_frame':'Offline fixture only','tasks':[
                {'task_id':f'T{i}','topic':topic,'research_query':f'Fixture {topic}','purpose':'Offline integration test','priority':3}
                for i,topic in enumerate(['Demand','Customers','Regulation'],1)]}
        if 'Extract only factual' in instructions:
            docs=json.loads(prompt.split('\nSources: ',1)[1])
            return {'claims':[{'claim':QUOTE,'source_ids':[docs[0]['source_id']],'evidence_type':'metric','importance':3}]}
        if 'strict evidence verifier' in instructions:
            claims=json.loads(prompt.split('Claims: ',1)[1].split('\nSources: ',1)[0])
            docs=json.loads(prompt.split('\nSources: ',1)[1])
            return {'verification':[{'claim_id':x['claim_id'],'status':'supported','supporting_source_ids':[docs[0]['source_id']],
                'supporting_quotes':[{'source_id':docs[0]['source_id'],'quote':QUOTE}],'reason':'Exact offline fixture excerpt'} for x in claims]}
        if 'Compare the verified findings' in instructions:return {'conflicts':[]}
        if 'business research synthesis agent' in instructions:
            return {'executive_summary':'OFFLINE FIXTURE ONLY — not factual business research. This result verifies the full software pipeline.',
                'executive_source_ids':['S1'],'key_findings':[{'text':QUOTE,'finding_ids':['F1'],'source_ids':['S1']}],
                'opportunities':[],'risks':[{'text':'Illustrative scope uncertainty','finding_ids':['F1'],'source_ids':['S1'],'likelihood':3,'impact':4,'mitigation':'Use actual evidence.'}],
                'decision_questions':['Which metric is relevant?'],'evidence_gaps':[],'recommended_follow_up_research':[],'limitations':['All data is an offline test fixture.']}
        if 'decision-support agent' in instructions:
            return {'stance':'Proceed with conditions','summary':'OFFLINE FIXTURE — use real evidence before deciding.',
                'reasons':[{'text':'Pipeline demonstrator only.','source_ids':['S1']}],
                'conditions':['Replace fixture evidence.'],'action_plan':[{'priority':'Now','action':'Collect actual evidence','why':'Fixture data is not research','expected_effect':'A defensible decision','timeframe':'Before acting','source_ids':['S1']}],
                'success_metrics':['Coverage of all actual questions'],'reconsider_if':['Actual evidence disagrees'],'watchouts':['Fixture only']}
        raise AssertionError('Unexpected fixture request: '+instructions[:100])

class FixtureSearch:
    def search(self,query,max_results):
        key=hashlib.sha256(query.encode()).hexdigest()[:12]
        return [{'url':f'https://fixture.gov/{key}','title':'OFFLINE TEST FIXTURE — ₹100 illustrative index','domain':'fixture.gov',
            'content':QUOTE,'search_score':.9,'quality_score':.95,'authority_tier':'test-fixture'}],None

def patch_providers(monkeypatch):
    from researchops_backend.agents import planner,evidence,synthesizer,decision
    from researchops_backend import orchestrator
    for module in [planner,evidence,synthesizer,decision]:monkeypatch.setattr(module,'GeminiService',FixtureLLM)
    monkeypatch.setattr(orchestrator,'SearchService',FixtureSearch)
    FixtureLLM.calls=[]
