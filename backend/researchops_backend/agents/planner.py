import json
from researchops_backend.services.gemini_service import GeminiService


class PlannerAgent:
    def __init__(self, llm=None):
        self.llm = llm or GeminiService()

    @staticmethod
    def _query_target(mode: str) -> int:
        return {'Standard': 2, 'Deep': 3, 'Exhaustive': 4}.get(mode, 3)

    def create_plan(self, question: str, max_tasks: int, geography=None, industry=None, research_mode='Deep'):
        query_target = self._query_target(research_mode)
        instructions = f"""You are the planning component of a rigorous business research system. Decompose the problem into independent, searchable tasks suitable for parallel execution. Cover market size/demand, customers, competitors, pricing/economics, regulation/constraints, technology/substitutes, opportunities, downside evidence, and risks when relevant. Do not assume facts.
For each task generate up to {query_target} materially different search queries, not paraphrases. Include a mix of broad discovery, primary/official evidence, quantitative evidence, and counter-evidence/risks where applicable.
Return ONLY JSON: {{"research_question":str,"decision_frame":str,"tasks":[{{"task_id":"T1","topic":str,"research_query":str,"search_queries":[str],"purpose":str,"priority":1-5}}]}}. Create no more than the requested number of tasks."""
        prompt = (
            f"Question: {question}\nGeography: {geography or 'not specified'}\n"
            f"Industry: {industry or 'infer only when obvious'}\nMaximum tasks: {max_tasks}\n"
            f"Research mode: {research_mode}"
        )
        data = self.llm.json(instructions, prompt)
        tasks = data.get('tasks', [])[:max_tasks]
        for i, t in enumerate(tasks, 1):
            t['task_id'] = f'T{i}'
            base = (t.get('research_query') or '').strip()
            queries = []
            for q in t.get('search_queries', []) or []:
                q = str(q).strip()
                if q and q.lower() not in {x.lower() for x in queries}:
                    queries.append(q)
            if base and base.lower() not in {x.lower() for x in queries}:
                queries.insert(0, base)
            if not queries and base:
                queries = [base]
            t['search_queries'] = queries[:query_target]
            if not t.get('research_query') and queries:
                t['research_query'] = queries[0]
        data['tasks'] = tasks
        data['research_question'] = question
        data['research_mode'] = research_mode
        return data

    def expand_queries(self, tasks, source_snapshot, round_no: int, max_per_task: int = 2):
        """Generate gap-closing queries after the first retrieval pass.

        The prompt receives only titles/domains/queries, not whole documents. This keeps
        the expansion call cheap while forcing the next round toward missing evidence,
        primary sources, contradictory evidence and newer quantitative data.
        """
        instructions = f"""You are a research-gap planner. Review the planned tasks and the source coverage collected so far. Generate up to {max_per_task} NEW search queries per task that close evidence gaps. Prioritize: primary/official sources, recent quantitative data, counter-evidence, failure cases, regulation, unit economics, and region-specific evidence. Do not repeat queries already used. Return ONLY JSON: {{"task_queries":{{"T1":[str]}}}}."""
        prompt = (
            f"Expansion round: {round_no}\n"
            f"Tasks: {json.dumps(tasks)}\n"
            f"Coverage snapshot: {json.dumps(source_snapshot)}"
        )
        data = self.llm.json(instructions, prompt)
        raw = data.get('task_queries', {}) or {}
        out = {}
        valid = {t.get('task_id') for t in tasks}
        for tid, queries in raw.items():
            if tid not in valid:
                continue
            clean = []
            for q in queries or []:
                q = str(q).strip()
                if q and q.lower() not in {x.lower() for x in clean}:
                    clean.append(q)
            if clean:
                out[tid] = clean[:max_per_task]
        return out
