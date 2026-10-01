import json
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from researchops_backend.core.config import get_settings
from researchops_backend.agents.planner import PlannerAgent
from researchops_backend.agents.evidence import EvidenceAgent
from researchops_backend.agents.synthesizer import SynthesisAgent
from researchops_backend.agents.decision import DecisionAgent
from researchops_backend.services.search_service import SearchService
from researchops_backend.mapreduce.factory import get_mapreduce_engine
from researchops_backend.analytics.forecast import ForecastService
from researchops_backend.analytics.risk import RiskService
from researchops_backend.storage.repository import Repository


RESEARCH_PROFILES = {
    'Standard': {
        'rounds': 1, 'initial_queries': 2, 'expansion_queries': 0,
        'results_per_query': 6, 'source_cap': 80, 'analysis_per_task': 16, 'claim_cap': 8,
    },
    'Deep': {
        'rounds': 2, 'initial_queries': 3, 'expansion_queries': 2,
        'results_per_query': 8, 'source_cap': 180, 'analysis_per_task': 24, 'claim_cap': 10,
    },
    'Exhaustive': {
        'rounds': 3, 'initial_queries': 4, 'expansion_queries': 3,
        'results_per_query': 10, 'source_cap': 320, 'analysis_per_task': 32, 'claim_cap': 12,
    },
}


class ResearchOrchestrator:
    def __init__(self, repo=None):
        self.s = get_settings()
        self.repo = repo or Repository()

    def _stage(self, rid, stage, progress):
        self.repo.update(rid, status='running', stage=stage, progress=progress)

    def _cached(self, rid, key, action):
        value = self.repo.load_checkpoint(rid, key)
        if value is not None:
            return value
        value = action()
        self.repo.save_checkpoint(rid, key, value)
        return value


    def _profile(self, mode):
        p = dict(RESEARCH_PROFILES.get(mode, RESEARCH_PROFILES['Deep']))
        p['source_cap'] = min(p['source_cap'], max(40, int(self.s.adaptive_source_hard_cap)))
        return p

    @staticmethod
    def _with_geo(query, geography):
        query = (query or '').strip()
        if geography and geography.lower() not in query.lower():
            query = f'{query} {geography}'.strip()
        return query

    @staticmethod
    def _fallback_queries(task, geography=None):
        base = (task.get('research_query') or task.get('topic') or '').strip()
        if not base:
            return []
        variants = [
            base,
            f'{base} official government regulator statistics report',
            f'{base} market data industry association quantitative evidence',
            f'{base} risks challenges failures criticism counter evidence',
            f'{base} competitors alternatives pricing economics',
            f'{base} latest {datetime.now().year} trends data',
        ]
        out = []
        for q in variants:
            q = ResearchOrchestrator._with_geo(q, geography)
            if q and q.lower() not in {x.lower() for x in out}:
                out.append(q)
        return out

    def _search_jobs(self, rid, jobs, search, profile):
        def fetch(tid, query):
            key = 'search:' + hashlib.sha256((tid + ':' + query).encode()).hexdigest()[:24]
            cached = self.repo.load_checkpoint(rid, key)
            if cached is not None:
                return tid, query, cached, None, key, True
            rows, error = search.search(query, profile['results_per_query'])
            return tid, query, rows, error, key, False
        with ThreadPoolExecutor(max_workers=self.s.research_workers) as pool:
            # Stable source ordering matters when replaying checkpointed searches.
            yield from pool.map(lambda job: fetch(*job), jobs)

    def _collect_sources(self, rid, req, planner, plan, profile):
        tasks = plan.get('tasks', [])
        search = SearchService()
        collected = {}
        used_queries = {t['task_id']: [] for t in tasks}
        errors = []
        trace = []

        # Round 1 comes from the planner plus deterministic primary/counter-evidence fallbacks.
        query_map = {}
        for t in tasks:
            planned = [q for q in (t.get('search_queries') or []) if str(q).strip()]
            fallback = self._fallback_queries(t, req.get('geography'))
            merged = []
            for q in planned + fallback:
                q = self._with_geo(str(q), req.get('geography'))
                if q and q.lower() not in {x.lower() for x in merged}:
                    merged.append(q)
            query_map[t['task_id']] = merged[:profile['initial_queries']]

        completed_searches = 0
        stop_reason = 'research-round-limit'
        for round_no in range(1, profile['rounds'] + 1):
            jobs = []
            task_by_id = {t['task_id']: t for t in tasks}
            for tid, queries in query_map.items():
                for q in queries:
                    if q.lower() in {x.lower() for x in used_queries.get(tid, [])}:
                        continue
                    used_queries.setdefault(tid, []).append(q)
                    jobs.append((tid, q))

            if not jobs:
                stop_reason = 'no-new-search-queries'
                break

            progress = min(34, 16 + round_no * 6)
            self._stage(rid, f'Adaptive web sweep · round {round_no}/{profile["rounds"]}', progress)
            before = len(collected)

            for record in self._search_jobs(rid, jobs, search, profile):
                    tid, query, rows, err, cache_key, was_cached = record
                    completed_searches += 1
                    if err:
                        errors.append({'task_id': tid, 'query': query, 'error': err})
                        continue
                    if not was_cached:
                        self.repo.save_checkpoint(rid, cache_key, rows)
                    self.repo.update(rid, metrics_json=json.dumps({
                        'search_queries_completed': completed_searches,
                        'unique_sources_discovered': len(collected), 'search_round': round_no
                    }))
                    task = task_by_id.get(tid, {})
                    for row in rows:
                        url = row.get('url')
                        if not url:
                            continue
                        if url not in collected and len(collected) >= profile['source_cap']:
                            continue
                        if url not in collected:
                            row.update({
                                'task_id': tid,
                                'task_ids': [tid],
                                'topic': task.get('topic', 'Research'),
                                'topics': [task.get('topic', 'Research')],
                                'query': query,
                                'queries': [query],
                            })
                            collected[url] = row
                        else:
                            cur = collected[url]
                            if tid not in cur.setdefault('task_ids', []):
                                cur['task_ids'].append(tid)
                            topic = task.get('topic', 'Research')
                            if topic not in cur.setdefault('topics', []):
                                cur['topics'].append(topic)
                            if query not in cur.setdefault('queries', []):
                                cur['queries'].append(query)
                            # Keep the richer excerpt / stronger search hit.
                            if len(row.get('content', '')) > len(cur.get('content', '')):
                                cur['content'] = row.get('content', '')
                            cur['search_score'] = max(float(cur.get('search_score', 0)), float(row.get('search_score', 0)))
                            cur['quality_score'] = max(float(cur.get('quality_score', 0)), float(row.get('quality_score', 0)))

            after = len(collected)
            self.repo.update(rid, metrics_json=json.dumps({'search_queries_completed': completed_searches, 'unique_sources_discovered': after, 'search_round': round_no}))
            new_count = after - before
            unique_domains = len({x.get('domain') for x in collected.values() if x.get('domain')})
            trace.append({
                'round': round_no,
                'queries_executed': len(jobs),
                'new_unique_sources': new_count,
                'total_unique_sources': after,
                'unique_domains': unique_domains,
            })

            if after >= profile['source_cap']:
                stop_reason = 'adaptive-safety-cap-reached'
                break
            if round_no >= profile['rounds']:
                stop_reason = 'research-round-limit'
                break
            # Diminishing returns: stop only after a broad first sweep and a very low-yield round.
            if round_no > 1 and new_count < max(6, int(max(1, before) * 0.06)):
                stop_reason = 'evidence-saturation'
                break

            snapshot = {}
            for t in tasks:
                tid = t['task_id']
                related = [x for x in collected.values() if tid in x.get('task_ids', [])]
                snapshot[tid] = {
                    'used_queries': used_queries.get(tid, []),
                    'domains': sorted({x.get('domain') for x in related if x.get('domain')})[:40],
                    'source_titles': [x.get('title') for x in sorted(related, key=lambda z: z.get('search_score', 0), reverse=True)[:20]],
                    'source_count': len(related),
                }
            try:
                query_map = self._cached(rid, f'expansion:{round_no}', lambda: planner.expand_queries(
                    tasks, snapshot, round_no + 1, max_per_task=profile['expansion_queries']
                ))
            except Exception as exc:
                errors.append({'stage': 'query-expansion', 'round': round_no + 1, 'error': f'{type(exc).__name__}: {exc}'})
                query_map = {}

            # Ensure the sweep can continue even when expansion-model output is sparse.
            for t in tasks:
                tid = t['task_id']
                if query_map.get(tid):
                    continue
                fallbacks = self._fallback_queries(t, req.get('geography'))
                unused = [q for q in fallbacks if q.lower() not in {x.lower() for x in used_queries.get(tid, [])}]
                if unused:
                    query_map[tid] = unused[:profile['expansion_queries']]

        if not collected:
            raise RuntimeError('Web research returned no usable sources. Check Tavily quota, credentials, and search availability. ' + (errors[0]['error'] if errors else 'Try a more specific brief.'))
        sources = list(collected.values())
        for i, source in enumerate(sources, 1):
            source['source_id'] = f'S{i}'
        return sources, {
            'mode': req.get('research_mode', 'Deep'),
            'adaptive': True,
            'rounds': trace,
            'queries_executed': sum(x['queries_executed'] for x in trace),
            'unique_sources': len(sources),
            'unique_domains': len({s.get('domain') for s in sources if s.get('domain')}),
            'stop_reason': stop_reason,
            'query_errors': errors[:40],
            'note': 'Research breadth is adaptive: ResearchOps expands queries toward evidence gaps and counter-evidence, then stops at saturation, the selected depth, or an internal safety cap to avoid runaway API use.'
        }

    @staticmethod
    def _task_sources(sources, task_id):
        return [s for s in sources if task_id in (s.get('task_ids') or [s.get('task_id')])]

    @staticmethod
    def _select_evidence_sources(sources, limit):
        if len(sources) <= limit:
            return sources
        ranked = sorted(
            sources,
            key=lambda s: 0.55 * float(s.get('quality_score', 0)) + 0.45 * float(s.get('search_score', 0)),
            reverse=True,
        )
        chosen, seen_domains, chosen_ids = [], set(), set()
        # First pass maximizes independent-domain coverage.
        for s in ranked:
            d = s.get('domain')
            if d and d in seen_domains:
                continue
            chosen.append(s)
            chosen_ids.add(s['source_id'])
            if d:
                seen_domains.add(d)
            if len(chosen) >= limit:
                return chosen
        for s in ranked:
            if s['source_id'] in chosen_ids:
                continue
            chosen.append(s)
            if len(chosen) >= limit:
                break
        return chosen

    def _coverage(self, tasks, sources, selected_by_task, verified):
        rows = []
        for t in tasks:
            tid = t['task_id']
            raw = self._task_sources(sources, tid)
            selected = selected_by_task.get(tid, [])
            vf = [x for x in verified if x.get('task_id') == tid]
            rows.append({
                'task_id': tid,
                'topic': t.get('topic'),
                'purpose': t.get('purpose'),
                'sources_found': len(raw),
                'sources_analyzed': len(selected),
                'unique_domains': len({x.get('domain') for x in raw if x.get('domain')}),
                'verified_findings': len(vf),
                'status': 'covered' if vf else ('evidence-found-no-verified-claim' if raw else 'gap'),
            })
        covered = sum(1 for x in rows if x['status'] == 'covered')
        return {
            'tasks': rows,
            'covered_tasks': covered,
            'total_tasks': len(rows),
            'coverage_percent': round(100 * covered / max(1, len(rows)), 1),
        }

    def _quality(self, claims, verified, sources, coverage=None, conflicts=None):
        verification_rate = (len(verified) / len(claims) * 100) if claims else 0.0
        unique_domains = len({s.get('domain') for s in sources if s.get('domain')})
        avg_quality = sum(float(s.get('quality_score', 0)) for s in sources) / max(1, len(sources))
        domain_score = min(100.0, unique_domains / 12.0 * 100.0)
        evidence_coverage = float((coverage or {}).get('coverage_percent') or min(100.0, len(verified) / 8.0 * 100.0))
        conflict_penalty = min(15.0, sum({'low': 2, 'medium': 5, 'high': 9}.get(x.get('severity'), 5) for x in (conflicts or [])))
        readiness = (
            0.30 * verification_rate
            + 0.25 * (avg_quality * 100.0)
            + 0.20 * domain_score
            + 0.25 * evidence_coverage
            - conflict_penalty
        )
        readiness = max(0.0, min(100.0, readiness))
        band = 'Limited' if readiness < 40 else 'Developing' if readiness < 65 else 'Strong'
        return {
            'readiness_score': round(readiness, 1),
            'band': band,
            'verification_rate': round(verification_rate, 1),
            'unique_domains': unique_domains,
            'average_source_quality': round(avg_quality, 3),
            'domain_diversity_score': round(domain_score, 1),
            'evidence_coverage_score': round(evidence_coverage, 1),
            'material_conflicts': len(conflicts or []),
            'conflict_penalty': round(conflict_penalty, 1),
            'note': 'Decision readiness is a heuristic combining verification rate, source authority, domain diversity, task coverage, and a penalty for unresolved evidence conflicts. It is not a guarantee that a decision will succeed.'
        }

    def run(self, rid, req):
        try:
            mode = req.get('research_mode', 'Deep')
            profile = self._profile(mode)
            self._stage(rid, 'Planning research tasks and search angles', 6)
            planner = PlannerAgent()
            plan = self._cached(rid, 'plan', lambda: planner.create_plan(
                req['question'], req['max_tasks'], req.get('geography'), req.get('industry'), research_mode=mode
            ))
            tasks = plan.get('tasks', [])
            if not tasks: raise RuntimeError('Research planner returned no tasks. Retry the saved job.')

            self._stage(rid, 'Starting adaptive web research', 14)
            retrieved = self._cached(rid, 'retrieval', lambda: dict(zip(
                ['sources', 'sweep'], self._collect_sources(rid, req, planner, plan, profile))))
            sources, sweep = retrieved['sources'], retrieved['sweep']

            self._stage(rid, 'MapReduce processing across retrieved evidence', 40)
            engine = get_mapreduce_engine()
            mr = self._cached(rid, 'mapreduce', lambda: engine.run(sources, rid))

            self._stage(rid, 'Selecting diverse high-value evidence', 47)
            selected_by_task = {}
            selected_ids = set()
            for t in tasks:
                ts = self._task_sources(sources, t['task_id'])
                chosen = self._select_evidence_sources(ts, profile['analysis_per_task'])
                selected_by_task[t['task_id']] = chosen
                selected_ids.update(s['source_id'] for s in chosen)

            self._stage(rid, 'Extracting decision-relevant evidence claims', 54)
            ev = EvidenceAgent()
            claims = []
            for t in tasks:
                ts = selected_by_task.get(t['task_id'], [])
                if ts:
                    claims.extend(self._cached(rid, 'claims:' + t['task_id'], lambda: ev.extract_claims(t, ts, max_claims=profile['claim_cap'])))

            self._stage(rid, 'Verifying claims against source excerpts', 66)
            verified_raw = []
            for t in tasks:
                tc = [c for c in claims if c['task_id'] == t['task_id']]
                ts = selected_by_task.get(t['task_id'], [])
                if tc and ts:
                    verified_raw.extend(self._cached(rid, 'verify:' + t['task_id'], lambda: ev.verify_claims(tc, ts)))

            by_source = {s['source_id']: s for s in sources}
            verified = []
            for c in verified_raw:
                if c.get('verification_status') != 'supported' or not c.get('source_ids'):
                    continue
                domains = {by_source[x]['domain'] for x in c['source_ids'] if x in by_source and by_source[x].get('domain')}
                qualities = [by_source[x]['quality_score'] for x in c['source_ids'] if x in by_source]
                corroborated = len(domains) >= 2
                primary = bool(qualities and max(qualities) >= 0.9)
                if not (corroborated or primary):
                    continue
                confidence = min(0.98, 0.55 + 0.12 * len(domains) + (0.18 if primary else 0) + 0.08 * (sum(qualities) / max(1, len(qualities))))
                c['confidence'] = round(confidence, 3)
                c['evidence_strength'] = 'corroborated' if corroborated else 'authoritative-primary'
                c['finding_id'] = f'F{len(verified) + 1}'
                verified.append(c)

            self._stage(rid, 'Auditing conflicting evidence and coverage', 73)
            conflicts = self._cached(rid, 'conflicts', lambda: ev.audit_conflicts(verified))
            coverage = self._coverage(tasks, sources, selected_by_task, verified)
            quality = self._quality(claims, verified, sources, coverage, conflicts)

            self._stage(rid, 'Synthesizing verified research findings', 80)
            synth = SynthesisAgent()
            synthesis = self._cached(rid, 'synthesis', lambda: synth.synthesize(req['question'], verified, sources, conflicts, coverage)) if verified else {
                'executive_summary': 'No claims met the strict verification threshold.',
                'executive_source_ids': [],
                'key_findings': [], 'opportunities': [], 'risks': [], 'decision_questions': [],
                'evidence_gaps': [x['topic'] for x in coverage.get('tasks', []) if x['status'] != 'covered'],
                'recommended_follow_up_research': ['Add trusted internal data or primary-source evidence for uncovered decision areas.'],
                'limitations': ['No claim passed excerpt verification plus the corroboration/authority threshold.']
            }

            self._stage(rid, 'Forecasting and deterministic risk analysis', 89)
            forecast = ForecastService().build(
                verified,
                [dict(x) for x in req.get('historical_data', [])],
                req.get('baseline_value'),
                years=int(req.get('forecast_years', 5)),
            )
            risk = RiskService().assess(synthesis.get('risks', []))

            decision = {'enabled': False}
            if req.get('include_decision_suggestion'):
                self._stage(rid, 'Building action-oriented AI decision support', 96)
                if verified:
                    decision = self._cached(rid, 'decision', lambda: DecisionAgent().advise(
                        req['question'], synthesis, risk, forecast, verified, sources,
                        style=req.get('decision_style', 'Balanced'), quality=quality, conflicts=conflicts
                    ))
                else:
                    decision = {
                        'enabled': True,
                        'stance': 'Insufficient evidence',
                        'confidence': 0,
                        'confidence_method': 'No verified evidence was available.',
                        'confidence_components': {},
                        'summary': 'The strict verification stage did not retain enough evidence to support a responsible recommendation.',
                        'reasons': [], 'conditions': [],
                        'action_plan': [
                            {'priority': 'Now', 'action': 'Collect primary-source evidence for the uncovered research areas.', 'why': 'The decision cannot be supported without verified evidence.', 'expected_effect': 'Improves decision readiness and reduces reliance on assumptions.', 'timeframe': 'Before making the decision', 'source_ids': []},
                            {'priority': 'Next', 'action': 'Add trusted internal metrics, customer data, pricing, or historical performance where available.', 'why': 'Internal evidence can resolve gaps that public web research cannot.', 'expected_effect': 'Makes the forecast and risk model more decision-specific.', 'timeframe': 'Next research cycle', 'source_ids': []},
                        ],
                        'next_actions': ['Collect primary-source evidence for uncovered research areas.', 'Add trusted internal business data where available.'],
                        'success_metrics': ['At least one verified finding for every critical research task.'],
                        'reconsider_if': ['New authoritative evidence materially changes the current evidence picture.'],
                        'watchouts': [],
                        'style': req.get('decision_style', 'Balanced'),
                        'note': 'AI decision support is advisory and should not replace human review.'
                    }

            report = self._markdown(
                req['question'], synthesis, verified, sources, forecast, risk, engine.name,
                decision, quality, int(req.get('forecast_years', 5)), sweep, coverage, conflicts
            )
            result = {
                'research_id': rid,
                'question': req['question'],
                'request_options': {
                    'forecast_years': int(req.get('forecast_years', 5)),
                    'include_decision_suggestion': bool(req.get('include_decision_suggestion')),
                    'decision_style': req.get('decision_style', 'Balanced'),
                    'research_mode': mode,
                },
                'plan': plan,
                'metrics': {
                    'tasks': len(tasks), 'sources_retrieved': len(sources), 'sources_analyzed': len(selected_ids),
                    'claims_extracted': len(claims), 'verified_findings': len(verified),
                    'rejected_or_uncertain': max(0, len(claims) - len(verified)),
                    'evidence_conflicts': len(conflicts), 'queries_executed': sweep.get('queries_executed', 0),
                },
                'research_sweep': sweep,
                'research_coverage': coverage,
                'evidence_conflicts': conflicts,
                'research_quality': quality,
                'mapreduce': {'engine': engine.name, 'summary': mr},
                'verified_findings': verified,
                'source_catalog': [
                    {k: s[k] for k in (
                        'source_id', 'title', 'url', 'domain', 'quality_score', 'search_score', 'authority_tier',
                        'published_date', 'retrieved_at', 'task_id', 'task_ids', 'topic', 'topics', 'queries'
                    ) if k in s}
                    for s in sources
                ],
                'synthesis': synthesis,
                'forecast': forecast,
                'risk_assessment': risk,
                'decision_suggestion': decision,
                'report_markdown': report,
                'verification_note': 'Findings passed model-assisted excerpt verification with exact quote checks and a domain/authority heuristic. Different domains are not proof of independent reporting. Confidence scores are heuristic evidence indicators, not calibrated probabilities or guarantees of truth or business success.'
            }
            self.repo.update(rid, status='completed', stage='Completed', progress=100, result_json=json.dumps(result))
        except Exception:
            # The independent worker records errors/retries and retains the last
            # saved progress. Failed work must never be displayed as 100%.
            raise

    def _cite(self, ids, sources):
        by = {s['source_id']: s for s in sources}
        return ' '.join(f"[{i}]({by[i]['url']})" for i in ids if i in by)

    def _markdown(self, q, syn, findings, sources, forecast, risk, engine, decision, quality,
                  forecast_years, sweep, coverage, conflicts):
        lines = [
            '# ResearchOps Report', '', f'**Problem statement:** {q}', '',
            f"**Research depth:** {sweep.get('mode', 'Deep')} (adaptive web sweep)",
            f"**Search queries executed:** {sweep.get('queries_executed', 0)}",
            f"**Unique sources reviewed:** {sweep.get('unique_sources', len(sources))}",
            f"**Distinct domains:** {sweep.get('unique_domains', quality.get('unique_domains',0))}",
            f"**Adaptive stop reason:** {sweep.get('stop_reason','')}",
            f'**Processing mode:** {engine}', f'**Forecast horizon:** {forecast_years} year(s)', '',
            '## Research Quality', '',
            f"**Decision readiness:** {quality.get('readiness_score',0)}/100 - {quality.get('band','Unknown')}",
            f"Verification rate: {quality.get('verification_rate',0)}% | Task coverage: {coverage.get('coverage_percent',0)}% | Material conflicts: {len(conflicts)}",
            f"Unique domains: {quality.get('unique_domains',0)} | Average source quality: {quality.get('average_source_quality',0)*100:.0f}%",
            '', quality.get('note',''), '',
            '## Executive Summary', '', syn.get('executive_summary',''),
            f"  \nSources: {self._cite(syn.get('executive_source_ids',[]),sources)}" if syn.get('executive_source_ids') else ''
        ]
        if decision.get('enabled'):
            lines += ['', '## AI Decision Suggestion', '', f"**{decision.get('stance','')}** - Confidence {decision.get('confidence',0)}%", '', decision.get('summary','')]
            for x in decision.get('reasons', []):
                lines += [f"- {x.get('text','')}  ", f"  Sources: {self._cite(x.get('source_ids',[]),sources)}"]
            if decision.get('conditions'):
                lines += ['', '### Conditions before acting'] + [f'- {x}' for x in decision['conditions']]
            if decision.get('action_plan'):
                lines += ['', '### Action plan']
                for x in decision['action_plan']:
                    lines += [
                        f"- **{x.get('priority','Next')} · {x.get('action','')}**",
                        f"  Why: {x.get('why','')}",
                        f"  Expected effect: {x.get('expected_effect','')} | Timeframe: {x.get('timeframe','')}",
                        f"  Sources: {self._cite(x.get('source_ids',[]),sources)}" if x.get('source_ids') else ''
                    ]
            if decision.get('success_metrics'):
                lines += ['', '### Success metrics'] + [f'- {x}' for x in decision['success_metrics']]
            if decision.get('reconsider_if'):
                lines += ['', '### Reconsider the decision if'] + [f'- {x}' for x in decision['reconsider_if']]
            if decision.get('watchouts'):
                lines += ['', '### Watchouts'] + [f'- {x}' for x in decision['watchouts']]
            lines += ['', f"_{decision.get('note','')}_"]

        lines += ['', '## Verified Findings', '']
        for f in findings:
            lines += [f"- {f['claim']}  ", f"  Sources: {self._cite(f['source_ids'],sources)}"]

        if conflicts:
            lines += ['', '## Evidence Conflicts', '']
            for x in conflicts:
                lines += [f"- **{x.get('severity','medium').title()} · {x.get('topic','Conflict')}** - {x.get('description','')}", f"  Resolution needed: {x.get('resolution_needed','')}"]

        lines += ['', '## Coverage & Evidence Gaps', '']
        for x in coverage.get('tasks', []):
            lines.append(f"- **{x.get('task_id')} · {x.get('topic')}** - {x.get('status')} | {x.get('sources_found')} sources | {x.get('verified_findings')} verified findings")
        for x in syn.get('evidence_gaps', []):
            lines.append(f'- Gap: {x}')
        if syn.get('recommended_follow_up_research'):
            lines += ['', '### Recommended follow-up research'] + [f'- {x}' for x in syn['recommended_follow_up_research']]

        lines += ['', '## Business Opportunities', '']
        for x in syn.get('opportunities', []):
            lines += [f"- **{x.get('text','')}** - {x.get('rationale','')}  ", f"  Sources: {self._cite(x.get('source_ids',[]),sources)}"]
        lines += ['', '## Risks', '']
        for x in risk.get('risks', []):
            lines += [
                f"- **{x.get('text','')}** (Likelihood {x['likelihood']}/5, Impact {x['impact']}/5, Score {x['score']}/25)  ",
                f"  Mitigation: {x.get('mitigation','')}  ",
                f"  Sources: {self._cite(x.get('source_ids',[]),sources)}"
            ]
        lines += ['', '### Aggregate risk score', f"**{risk.get('overall_score') if risk.get('overall_score') is not None else 'Not assessed'} - {risk.get('band','Unknown')}**", '', '## Forecast', '', f"Method: **{forecast.get('method')}**", '', forecast.get('warning') or forecast.get('message','')]
        if forecast.get('method') == 'evidence-based-scenario':
            lines += ['', '| Scenario | Annual rate | Final projected value |', '|---|---:|---:|']
            for name, obj in forecast.get('scenarios', {}).items():
                series = obj.get('series', [])
                final = series[-1]['value'] if series else 0
                lines.append(f"| {name.title()} | {obj.get('annual_rate',0)*100:.2f}% | {final:.2f} |")
        elif forecast.get('method') == 'ridge-log-trend-ml':
            lines += ['', '| Year | Predicted | P10 | P90 |', '|---:|---:|---:|---:|']
            for row in forecast.get('forecast', []):
                lines.append(f"| {row['year']} | {row['predicted']:.2f} | {row['p10']:.2f} | {row['p90']:.2f} |")
        if forecast.get('evidence'):
            all_ids = sorted({sid for e in forecast['evidence'] for sid in e.get('source_ids', [])})
            lines += [f"  Sources: {self._cite(all_ids,sources)}"]
        lines += ['', '## Decision Questions', '']
        for x in syn.get('decision_questions', []):
            lines.append(f'- {x}')
        lines += ['', '## Limitations', '']
        for x in syn.get('limitations', []):
            lines.append(f'- {x}')
        lines += ['', '## Source Register', '']
        for s in sources:
            lines.append(f"- **{s['source_id']}** - [{s['title']}]({s['url']}) - {s['domain']} - {s.get('authority_tier','general-web')}")
        return '\n'.join(x for x in lines if x is not None)
