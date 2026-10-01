"""Exercise the actual SDK's embedded queue, replay sandbox and steps offline."""
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'backend')]
import anyio
from unittest.mock import patch
from fixture_pipeline import FixtureLLM,FixtureSearch
from researchops_backend.core.config import get_settings
from researchops_backend.storage.repository import Repository
from researchops_backend.agents import planner,evidence,synthesizer,decision
from researchops_backend import orchestrator
from vercel.workflow._internal import world as worlds
from vercel.workflow._internal.worlds.local import LocalWorld

async def main():
    world=LocalWorld();worlds.set_world(world)
    from workflow import research_job
    from vercel.workflow import start
    request={'question':'OFFLINE SDK FIXTURE: should we launch a research platform?','max_tasks':3,'research_mode':'Standard',
        'forecast_years':3,'historical_data':[],'include_decision_suggestion':True}
    repo=Repository();repo.create('sdk-job',request['question'],request)
    patches=[patch.object(module,'GeminiService',FixtureLLM) for module in [planner,evidence,synthesizer,decision]]
    patches.append(patch.object(orchestrator,'SearchService',FixtureSearch))
    original=FixtureLLM.json
    attempts=[]
    def flaky(self,instructions,prompt):
        if 'planning component' in instructions:
            attempts.append('plan')
            if len(attempts)==1:raise TimeoutError('Provider temporarily timed out')
        return original(self,instructions,prompt)
    patches.append(patch.object(FixtureLLM,'json',flaky))
    for item in patches:item.start()
    try:
        run=await start(research_job,'sdk-job',0)
        with anyio.fail_after(45):
            value=await run.return_value()
        assert value=='completed',value
        job=repo.get('sdk-job')
        assert job['status']=='completed' and job['checkpoints']=={}
        assert len(attempts)==2
        repo.create('sdk-failure',request['question'],request)
        with patch.object(FixtureLLM,'json',side_effect=RuntimeError('Gemini authentication failed')):
            failure=await start(research_job,'sdk-failure',0)
            with anyio.fail_after(10):assert await failure.return_value()=='failed'
        assert repo.get('sdk-failure')['status']=='failed'
        print('Native Workflow SDK smoke passed: embedded queue, deterministic replay, transient retry and persisted authentication failure.')
    finally:
        for item in patches:item.stop()
        repo.engine.dispose()
        await world.aclose()

if __name__=='__main__':anyio.run(main)
