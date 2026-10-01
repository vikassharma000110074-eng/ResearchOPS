import random
import statistics
from researchops_backend.analytics.forecast import quantile

class RiskService:
    def assess(self, risks):
        normalized=[]
        for r in risks or []:
            try: l=max(1,min(5,int(r.get('likelihood',3)))); i=max(1,min(5,int(r.get('impact',3))))
            except Exception: l=i=3
            score=l*i
            x=dict(r); x['likelihood']=l; x['impact']=i; x['score']=score; x['score_percent']=round(score/25*100,1); normalized.append(x)
        if not normalized: return {'overall_score':None,'band':'Not assessed','risks':[],'monte_carlo':None}
        overall=statistics.mean(r['score_percent'] for r in normalized); band='Low' if overall<35 else 'Moderate' if overall<65 else 'High'
        rng=random.Random(42); samples=[]
        for _ in range(5000):
            loss=0.0
            for r in normalized:
                if rng.random() < r['likelihood']/5.0: loss += r['impact']/5.0
            samples.append(100*loss/max(1,len(normalized)))
        return {'overall_score':round(overall,1),'band':band,'risks':normalized,'monte_carlo':{'mean_impact_index':round(statistics.mean(samples),1),'p90_impact_index':round(quantile(samples,0.9),1),'simulation_runs':5000,'note':'Impact index combines stated likelihood/impact scores; it is a comparative decision aid, not an actuarial loss probability.'}}
