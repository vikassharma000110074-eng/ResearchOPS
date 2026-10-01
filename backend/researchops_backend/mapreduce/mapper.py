#!/usr/bin/env python3
import json, re, sys
from collections import Counter
STOP=set('a an the and or but if then than to of in on for with from by at as is are was were be been being this that these those it its into about over under between through during after before can could should would may might will do does did have has had not no we you they their our your also more most less'.split())
RISK={'risk','decline','loss','threat','barrier','regulation','competition','cost','inflation','uncertainty','shortage','failure','volatility','downturn','delay','constraint'}
OPP={'growth','opportunity','demand','increase','expansion','adoption','potential','emerging','innovation','underserved','trend','investment'}
def tokens(text): return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text or '') if w.lower() not in STOP]
for line in sys.stdin:
    try:
        d=json.loads(line); topic=d.get('topic') or 'General'; c=Counter(tokens(d.get('content','')))
        print(f'{topic}|__documents__\t1'); print(f'{topic}|__tokens__\t{sum(c.values())}')
        print(f'{topic}|__risk_terms__\t{sum(c[x] for x in RISK)}'); print(f'{topic}|__opportunity_terms__\t{sum(c[x] for x in OPP)}')
        for term,count in c.most_common(80): print(f'{topic}|term:{term}\t{count}')
        if d.get('domain'): print(f'{topic}|domain:{d["domain"]}\t1')
    except Exception:
        continue
