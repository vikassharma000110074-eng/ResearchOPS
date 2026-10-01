from researchops_backend.agents.evidence import EvidenceAgent
from researchops_backend.utils.text import source_quality

class LLM:
    def __init__(self,quote):self.quote=quote
    def json(self,*args):return {'verification':[{'claim_id':'C1','status':'supported','supporting_source_ids':['S1'],
        'supporting_quotes':[{'source_id':'S1','quote':self.quote}],'reason':'Supported'}]}

def verify(quote):
    return EvidenceAgent(LLM(quote)).verify_claims([{'claim':'Annual growth was 10%.','source_ids':['S1'],'task_id':'T1'}],
        [{'source_id':'S1','title':'Official report','content':'The annual growth was 10% during the reporting year.'}])[0]

def test_fabricated_quote_cannot_pass_verification():
    assert verify('Annual growth was 80% and profits doubled.')['verification_status']=='uncertain'
    assert verify('annual growth was 10%')['verification_status']=='supported'

def test_lookalike_domains_do_not_get_primary_authority():
    assert source_quality('https://worldbank.org.evil.com/report')<.9
    assert source_quality('https://agency.gov.evil.com/report')<.9
    assert source_quality('https://data.worldbank.org/report')==.95
