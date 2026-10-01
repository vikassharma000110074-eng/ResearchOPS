from collections import Counter, defaultdict
from researchops_backend.utils.text import tokenize, RISK_TERMS, OPPORTUNITY_TERMS

def map_document(doc):
    topic=doc.get('topic') or 'General'
    tokens=tokenize(doc.get('content',''))
    term_counts=Counter(tokens)
    rows=[]
    rows.append((f'{topic}\t__documents__',1))
    rows.append((f'{topic}\t__tokens__',len(tokens)))
    rows.append((f'{topic}\t__risk_terms__',sum(term_counts[t] for t in RISK_TERMS)))
    rows.append((f'{topic}\t__opportunity_terms__',sum(term_counts[t] for t in OPPORTUNITY_TERMS)))
    for term,count in term_counts.most_common(80): rows.append((f'{topic}\tterm:{term}',count))
    if doc.get('domain'): rows.append((f'{topic}\tdomain:{doc["domain"]}',1))
    return rows

def reduce_rows(rows):
    agg=defaultdict(int)
    for k,v in rows: agg[k]+=int(v)
    topics=defaultdict(lambda:{'documents':0,'tokens':0,'risk_terms':0,'opportunity_terms':0,'terms':{},'domains':{}})
    for key,val in agg.items():
        topic,metric=key.split('\t',1); t=topics[topic]
        if metric=='__documents__': t['documents']=val
        elif metric=='__tokens__': t['tokens']=val
        elif metric=='__risk_terms__': t['risk_terms']=val
        elif metric=='__opportunity_terms__': t['opportunity_terms']=val
        elif metric.startswith('term:'): t['terms'][metric[5:]]=val
        elif metric.startswith('domain:'): t['domains'][metric[7:]]=val
    for t in topics.values():
        t['top_terms']=sorted(t.pop('terms').items(), key=lambda x:x[1], reverse=True)[:20]
        t['top_domains']=sorted(t.pop('domains').items(), key=lambda x:x[1], reverse=True)[:12]
    return dict(topics)
