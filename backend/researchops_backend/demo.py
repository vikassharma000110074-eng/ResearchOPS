"""Explicit offline demonstration. Never presented as live or verified research."""
import json
import time

class DemoRunner:
    def __init__(self,repo):self.repo=repo
    def run(self,rid,req):
        stages=[('Demo: save the brief',6),('Demo: load offline fixture',22),
                ('Demo: demonstrate checkpoint recovery',40),('Demo: show evidence limitations',66),
                ('Demo: build illustrative report',89)]
        for i,(stage,progress) in enumerate(stages):
            if self.repo.load_checkpoint(rid,f'demo:{i}') is None:
                self.repo.update(rid,status='running',stage=stage,progress=progress)
                time.sleep(1.5)
                self.repo.save_checkpoint(rid,f'demo:{i}',{'done':True})
        result={'research_id':rid,'question':req['question'],'demo':True,
            'request_options':{'forecast_years':req.get('forecast_years',5),'research_mode':req.get('research_mode','Deep')},
            'plan':{'tasks':[{'task_id':'T1','topic':'Offline demonstration','purpose':'Verify job lifecycle; no web research','research_query':req['question']}]},
            'metrics':{'tasks':1,'sources_retrieved':0,'sources_analyzed':0,'verified_findings':0,'claims_extracted':0},
            'research_sweep':{'mode':'Demo','queries_executed':0,'unique_sources':0,'unique_domains':0,'stop_reason':'offline-demonstration'},
            'research_coverage':{'tasks':[],'coverage_percent':0},'evidence_conflicts':[],
            'research_quality':{'readiness_score':0,'band':'Demo','verification_rate':0,'unique_domains':0,'note':'Offline demonstration only.'},
            'mapreduce':{'engine':'demo','summary':{}},'verified_findings':[],'source_catalog':[],
            'synthesis':{'executive_summary':'DEMO ONLY: no internet searches or AI API calls were made. This report demonstrates saved jobs, progress, history, downloads and recovery.',
                'key_findings':[],'opportunities':[],'risks':[],'decision_questions':[],
                'limitations':['This is not research evidence and cannot support a business decision.']},
            'forecast':{'method':'insufficient-evidence','available':False,'message':'Demo mode does not predict business outcomes.'},
            'risk_assessment':{'risks':[],'overall_score':None,'band':'Not assessed'},
            'decision_suggestion':{'enabled':False},
            'report_markdown':f'# ResearchOps — Offline Demo\n\n**Problem:** {req["question"]}\n\nNo searches or AI calls were made. This is a workflow demonstration, not an evidence report.\n\nSaved jobs, progress, history and report downloads are available.',
            'verification_note':'Offline demonstration. No verified claims.'}
        self.repo.update(rid,status='completed',stage='Demo complete — no live research performed',progress=100,result_json=json.dumps(result))
