import json
from researchops_backend.services.gemini_service import GeminiService


class DecisionAgent:
    """Optional evidence-grounded decision aid with a concrete action plan."""

    def __init__(self, llm=None):
        self.llm = llm or GeminiService()

    @staticmethod
    def _forecast_reliability(forecast):
        if not forecast or not forecast.get('available'):
            return 35.0
        if forecast.get('method') == 'ridge-log-trend-ml':
            r2 = float(forecast.get('in_sample_r2') or 0)
            return max(45.0, min(88.0, 55.0 + 30.0 * max(0.0, min(1.0, r2))))
        if forecast.get('method') == 'evidence-based-scenario':
            n = len(forecast.get('evidence') or [])
            return min(75.0, 52.0 + 4.0 * n)
        return 40.0

    @classmethod
    def _calculated_confidence(cls, quality, forecast, conflicts):
        quality = quality or {}
        readiness = float(quality.get('readiness_score') or 0)
        verification = float(quality.get('verification_rate') or 0)
        authority = float(quality.get('average_source_quality') or 0) * 100.0
        forecast_score = cls._forecast_reliability(forecast)
        conflict_penalty = min(28.0, sum({'low': 3, 'medium': 7, 'high': 12}.get(x.get('severity'), 7) for x in (conflicts or [])))
        score = 0.46 * readiness + 0.22 * verification + 0.17 * authority + 0.15 * forecast_score - conflict_penalty
        return int(round(max(0.0, min(95.0, score))))

    def advise(self, question, synthesis, risk, forecast, verified_findings, source_catalog,
               style='Balanced', quality=None, conflicts=None):
        valid_sources = {s['source_id'] for s in source_catalog}
        evidence = [
            {
                'finding_id': f.get('finding_id'),
                'claim': f.get('claim'),
                'source_ids': f.get('source_ids', []),
                'confidence': f.get('confidence'),
            }
            for f in verified_findings
        ]
        compact_forecast = {
            'method': forecast.get('method'), 'available': forecast.get('available'),
            'scenarios': forecast.get('scenarios'), 'forecast': forecast.get('forecast'),
            'warning': forecast.get('warning') or forecast.get('message'),
        }
        compact_risk = {
            'overall_score': risk.get('overall_score'), 'band': risk.get('band'),
            'risks': risk.get('risks', []),
        }
        instructions = """You are an evidence-grounded business decision-support agent. Use ONLY the supplied verified evidence, synthesis, deterministic risk analysis, forecast, and evidence-conflict audit. Do not add outside facts. This is an optional suggestion for a human decision-maker, not an instruction or guarantee.
Return ONLY JSON with this structure:
{"stance":"Proceed|Proceed with conditions|Delay|Do not proceed|Insufficient evidence","summary":str,"reasons":[{"text":str,"source_ids":[str]}],"conditions":[str],"action_plan":[{"priority":"Now|Next|Later","action":str,"why":str,"expected_effect":str,"timeframe":str,"source_ids":[str]}],"success_metrics":[str],"reconsider_if":[str],"watchouts":[str]}.
The action_plan is mandatory when evidence permits. It must answer what the user should DO next to improve the situation or reduce uncertainty. If the stance is Delay/Do not proceed, give concrete remediation steps that could make the situation stronger. If the stance is Proceed, focus on de-risking execution and measurable validation. Keep the summary under 160 words."""
        prompt = (
            f"Decision question: {question}\nDecision style: {style}\n"
            f"Verified evidence: {json.dumps(evidence)}\n"
            f"Synthesis: {json.dumps(synthesis)}\nRisk analysis: {json.dumps(compact_risk)}\n"
            f"Forecast: {json.dumps(compact_forecast)}\nEvidence conflicts: {json.dumps(conflicts or [])}"
        )
        data = self.llm.json(instructions, prompt)
        stance = data.get('stance', 'Insufficient evidence')
        allowed = {'Proceed', 'Proceed with conditions', 'Delay', 'Do not proceed', 'Insufficient evidence'}
        if stance not in allowed:
            stance = 'Insufficient evidence'

        reasons = []
        for item in data.get('reasons', []) or []:
            if not isinstance(item, dict) or not item.get('text'):
                continue
            ids = [x for x in item.get('source_ids', []) if x in valid_sources]
            reasons.append({'text': item['text'], 'source_ids': ids})

        action_plan = []
        for item in data.get('action_plan', []) or []:
            if not isinstance(item, dict) or not item.get('action'):
                continue
            ids = [x for x in item.get('source_ids', []) if x in valid_sources]
            priority = item.get('priority', 'Next')
            if priority not in {'Now', 'Next', 'Later'}:
                priority = 'Next'
            action_plan.append({
                'priority': priority,
                'action': str(item.get('action', '')),
                'why': str(item.get('why', '')),
                'expected_effect': str(item.get('expected_effect', '')),
                'timeframe': str(item.get('timeframe', '')),
                'source_ids': ids,
            })

        confidence = self._calculated_confidence(quality, forecast, conflicts)
        components = {
            'decision_readiness': round(float((quality or {}).get('readiness_score') or 0), 1),
            'verification_rate': round(float((quality or {}).get('verification_rate') or 0), 1),
            'average_source_quality': round(float((quality or {}).get('average_source_quality') or 0) * 100.0, 1),
            'forecast_reliability': round(self._forecast_reliability(forecast), 1),
            'material_conflicts': len(conflicts or []),
        }
        return {
            'enabled': True,
            'stance': stance,
            'confidence': confidence,
            'confidence_method': 'Calculated from research quality, verification, source authority, forecast reliability and conflict penalties.',
            'confidence_components': components,
            'summary': data.get('summary', ''),
            'reasons': reasons[:6],
            'conditions': [str(x) for x in (data.get('conditions') or [])][:8],
            'action_plan': action_plan[:9],
            # Backward-compatible summary used by older UI/report code.
            'next_actions': [x['action'] for x in action_plan[:8]],
            'success_metrics': [str(x) for x in (data.get('success_metrics') or [])][:8],
            'reconsider_if': [str(x) for x in (data.get('reconsider_if') or [])][:8],
            'watchouts': [str(x) for x in (data.get('watchouts') or [])][:8],
            'style': style,
            'note': 'AI decision support is advisory. Confidence is a research-evidence score, not a probability that the outcome will succeed.'
        }
