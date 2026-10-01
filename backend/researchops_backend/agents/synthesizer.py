import json
from researchops_backend.services.gemini_service import GeminiService


class SynthesisAgent:
    def __init__(self, llm=None):
        self.llm = llm or GeminiService()

    def synthesize(self, question, findings, source_catalog, conflicts=None, coverage=None):
        source_meta = {s['source_id']: {'title': s['title'], 'url': s['url']} for s in source_catalog}
        payload = [
            {
                'finding_id': f['finding_id'], 'claim': f['claim'], 'source_ids': f['source_ids'],
                'topic': f['topic'], 'confidence': f['confidence']
            }
            for f in findings
        ]
        instructions = """You are a business research synthesis agent. Use ONLY the supplied verified findings, evidence conflicts, and coverage data. Do not introduce new facts or numbers. Every factual output item must cite finding IDs and source IDs that support it. Distinguish evidence from interpretation. Produce decision support, not an automatic decision. Return ONLY JSON with: executive_summary (max 180 words), executive_source_ids [str], key_findings [{text,finding_ids,source_ids}], opportunities [{text,rationale,finding_ids,source_ids}], risks [{text,likelihood:1-5,impact:1-5,mitigation,finding_ids,source_ids}], decision_questions [str], evidence_gaps [str], recommended_follow_up_research [str], limitations [str]. Keep 3-8 items per main section when evidence allows."""
        data = self.llm.json(
            instructions,
            f"Question: {question}\nVerified findings: {json.dumps(payload)}\n"
            f"Evidence conflicts: {json.dumps(conflicts or [])}\nCoverage: {json.dumps(coverage or {})}\n"
            f"Source catalog: {json.dumps(source_meta)}"
        )
        valid_findings = {f['finding_id'] for f in findings}
        finding_sources = {f['finding_id']: set(f['source_ids']) for f in findings}
        valid_sources = {sid for f in findings for sid in f['source_ids']}

        def clean(items):
            out = []
            for x in items or []:
                if not isinstance(x, dict):
                    continue
                x['finding_ids'] = [i for i in x.get('finding_ids', []) if i in valid_findings]
                allowed_sources = {sid for fid in x['finding_ids'] for sid in finding_sources[fid]}
                x['source_ids'] = [i for i in x.get('source_ids', []) if i in allowed_sources]
                if x.get('text') and x['finding_ids'] and x['source_ids']:
                    out.append(x)
            return out

        for k in ('key_findings', 'opportunities', 'risks'):
            data[k] = clean(data.get(k, []))
        data['executive_source_ids'] = [i for i in data.get('executive_source_ids', []) if i in valid_sources]
        if data.get('executive_summary') and not data['executive_source_ids']:
            data['executive_source_ids'] = sorted({sid for x in data['key_findings'] for sid in x.get('source_ids', [])})
        for k in ('decision_questions', 'evidence_gaps', 'recommended_follow_up_research', 'limitations'):
            data.setdefault(k, [])
        return data
