import math, re
import random
import statistics

def quantile(values, probability):
    ordered=sorted(values)
    position=(len(ordered)-1)*probability
    lo=int(position);hi=min(lo+1,len(ordered)-1)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(position-lo)

RATE_RE=re.compile(r'(?<!\d)(-?\d+(?:\.\d+)?)\s*%')
ANNUAL_CONTEXT=re.compile(r'cagr|compound annual|annual (?:growth|increase|decline|rate)|year-on-year|year over year|yoy',re.I)

class ForecastService:
    def build(self, findings, historical_data=None, baseline_value=None, years=5):
        if not 1<=int(years)<=5:raise ValueError('Forecast horizon must be 1–5 years.')
        history=sorted(historical_data or [], key=lambda x:x['year'])
        if len({x['year'] for x in history})!=len(history):raise ValueError('Use one historical value per year.')
        if any(not math.isfinite(float(x['value'])) or float(x['value'])<=0 for x in history):raise ValueError('Historical values must be positive finite numbers.')
        if len(history)>=4:
            return self._ml_forecast(history, years)
        rates=[]
        for f in findings:
            low=f['claim'].lower()
            if not ANNUAL_CONTEXT.search(low): continue
            for m in RATE_RE.finditer(f['claim']):
                neighborhood=low[max(0,m.start()-60):m.end()+60]
                if not ANNUAL_CONTEXT.search(neighborhood):continue
                if re.search(r'quarter(?:ly)?|month(?:ly)?|weekly|daily',neighborhood):continue
                v=float(m.group(1))/100.0
                if -0.8 <= v <= 2.0: rates.append((v,f['source_ids'],f['claim']))
        if not rates:
            return {'method':'insufficient-evidence','available':False,'message':'No defensible growth-rate evidence or historical series was found. Add at least four year/value observations for an ML forecast, or research sources containing explicit growth rates.'}
        vals=[x[0] for x in rates]
        base=statistics.median(vals); downside=quantile(vals,0.25); upside=quantile(vals,0.75)
        if len(set(vals))==1:
            spread=max(abs(base)*0.35,0.03); downside=base-spread; upside=base+spread
        downside=max(downside,-0.8); upside=min(upside,2.0)
        start=float(baseline_value or 100.0); indexed=baseline_value is None
        scenarios={}
        for name,rate in [('downside',downside),('base',base),('upside',upside)]:
            series=[]
            for y in range(0,years+1): series.append({'year':y,'value':round(start*((1+rate)**y),3)})
            scenarios[name]={'annual_rate':round(rate,4),'series':series}
        return {'method':'evidence-based-scenario','available':True,'indexed_baseline':indexed,'baseline':start,'scenarios':scenarios,'evidence':[{'rate':r,'source_ids':s,'claim':c} for r,s,c in rates[:8]],'warning':'Illustrative scenario projection using explicit annual rates from retrieved evidence. Source metrics may differ from your business or target metric; confirm scope before using these scenarios. Downside/upside are assumptions, not calibrated prediction intervals.'}

    def _ml_forecast(self, history, years):
        # Closed-form one-feature Ridge regression; the intercept is unpenalized.
        y0=min(p['year'] for p in history)
        xs=[p['year']-y0 for p in history]
        vals=[float(p['value']) for p in history];logy=[math.log(v) for v in vals]
        xm=statistics.mean(xs);ym=statistics.mean(logy)
        slope=sum((x-xm)*(y-ym) for x,y in zip(xs,logy))/(sum((x-xm)**2 for x in xs)+0.5)
        intercept=ym-slope*xm
        fitted=[math.exp(intercept+slope*x) for x in xs]
        sse=sum((v-p)**2 for v,p in zip(vals,fitted));sst=sum((v-statistics.mean(vals))**2 for v in vals)
        r2=1-sse/sst if sst else (1.0 if sse<1e-20 else 0.0)
        residual=statistics.pstdev(y-(intercept+slope*x) for x,y in zip(xs,logy))
        rng=random.Random(42);rows=[]
        for year in range(max(p['year'] for p in history)+1,max(p['year'] for p in history)+years+1):
            log_prediction=intercept+slope*(year-y0);prediction=math.exp(log_prediction)
            samples=[math.exp(log_prediction+rng.gauss(0,max(residual,0.03))) for _ in range(1500)]
            rows.append({'year':year,'predicted':round(prediction,3),'p10':round(quantile(samples,.1),3),'p90':round(quantile(samples,.9),3)})
        cagr=(math.exp(intercept+slope*(rows[-1]['year']-y0))/vals[-1])**(1/years)-1
        return {'method':'ridge-log-trend-ml','available':True,'training_points':len(history),'in_sample_r2':round(r2,4),'implied_annual_growth':round(cagr,4),'forecast':rows,'warning':'Ridge regression extrapolates user-supplied history. P10/P90 use an assumed residual spread, not calibrated prediction intervals; structural market changes can invalidate the trend.'}
