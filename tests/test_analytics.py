import pytest
from researchops_backend.analytics.forecast import ForecastService
from researchops_backend.models.schemas import ResearchRequest
from researchops_backend.analytics.risk import RiskService
from researchops_backend.mapreduce.local_engine import LocalMapReduceEngine

@pytest.mark.parametrize('years',[1,2,3,4,5])
def test_forecast_horizons(years):
    result=ForecastService().build([{'claim':'Market CAGR is 12% through 2030','source_ids':['S1']}],[],100,years)
    assert result['method']=='evidence-based-scenario'
    assert len(result['scenarios']['base']['series'])==years+1

def test_nonannual_percentages_do_not_become_annual_growth():
    result=ForecastService().build([{'claim':'Growth in the quarter was 12%, with a profit margin of 20%.','source_ids':['S1']}])
    assert not result['available']

def test_ml_forecast_and_duplicate_years():
    history=[{'year':2021,'value':100},{'year':2022,'value':110},{'year':2023,'value':121},{'year':2024,'value':133.1}]
    result=ForecastService().build([],history,years=3)
    assert result['method']=='ridge-log-trend-ml' and len(result['forecast'])==3
    with pytest.raises(ValueError):ResearchRequest(question='Research this business.',historical_data=[history[0],history[0]])

def test_mapreduce_and_risk():
    summary=LocalMapReduceEngine().run([{'task_id':'T1','topic':'Market','domain':'example.org','content':'Growth opportunity and inflation risk'}],'test')
    assert summary
    result=RiskService().assess([{'text':'Demand risk','likelihood':4,'impact':5}])
    assert result['overall_score']==80
