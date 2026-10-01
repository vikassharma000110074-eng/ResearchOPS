import re
from urllib.parse import urlparse

STOPWORDS=set('a an the and or but if then than to of in on for with from by at as is are was were be been being this that these those it its into about over under between through during after before can could should would may might will shall do does did have has had not no yes we you they their our your them us also more most less least much many such other any each per via using use used based report research market business information data source sources new current'.split())

RISK_TERMS={'risk','decline','loss','threat','barrier','regulation','competition','cost','inflation','uncertainty','shortage','failure','volatility','downturn','delay','constraint'}
OPPORTUNITY_TERMS={'growth','opportunity','demand','increase','expansion','adoption','potential','emerging','innovation','underserved','trend','investment'}

def domain_of(url:str)->str:
    try:
        d=urlparse(url).netloc.lower().split(':')[0]
        return d[4:] if d.startswith('www.') else d
    except Exception:
        return ''

def tokenize(text:str):
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text or '') if w.lower() not in STOPWORDS]

def source_quality(url:str, title:str='')->float:
    d=domain_of(url)
    score=0.52
    matches = lambda root: d == root or d.endswith('.' + root)
    if d.endswith('.gov') or any(d.endswith(x) for x in ('.gov.in','.gov.uk','.gov.au','.gov.sg','.gov.cn','.gc.ca','.gouv.fr')): score=0.95
    elif d.endswith('.edu') or d.endswith('.edu.in') or d.endswith('.ac.in'): score=0.9
    elif any(matches(k) for k in ('worldbank.org','oecd.org','imf.org','who.int','un.org','data.gov','sec.gov')): score=0.95
    elif any(matches(k) for k in ('reuters.com','apnews.com','bloomberg.com','ft.com','economist.com')): score=0.86
    elif any(matches(k) for k in ('statista.com','gartner.com','mckinsey.com','deloitte.com','pwc.com','ey.com','kpmg.com')): score=0.8
    elif any(k in title.lower() for k in ('annual report','official','government','regulator')): score=max(score,0.78)
    return round(score,3)
