import time
from datetime import datetime, timezone
from tavily import TavilyClient
from researchops_backend.core.config import get_settings
from researchops_backend.utils.text import domain_of, source_quality


class SearchService:
    def __init__(self):
        s = get_settings()
        if not s.tavily_api_key:
            raise RuntimeError('TAVILY_API_KEY is missing. Add it in Vercel Project Settings > Environment Variables (or local .env).')
        self.client = TavilyClient(api_key=s.tavily_api_key)
        self.max_chars = s.max_source_chars
        self.timeout = s.api_timeout_seconds

    @staticmethod
    def _authority_tier(score: float) -> str:
        if score >= 0.90:
            return 'primary-authority'
        if score >= 0.80:
            return 'high-authority'
        if score >= 0.65:
            return 'established'
        return 'general-web'

    def search(self, query: str, max_results: int = 8):
        # Tavily is queried in advanced mode. A failed individual query should not
        # collapse a large research run, so retry once and then return an empty set.
        max_results = max(2, min(int(max_results), 20))
        payload = None
        last_error = None
        for attempt in range(1 if get_settings().execution_mode=='vercel-workflow' else 2):
            try:
                payload = self.client.search(
                    query=query,
                    search_depth='advanced',
                    max_results=max_results,
                    include_answer=False,
                    timeout=self.timeout,
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt == 0 and get_settings().execution_mode!='vercel-workflow':
                    time.sleep(0.8)
        if payload is None:
            from researchops_backend.security import safe_error
            return [], safe_error(last_error) if last_error else 'Search failed'

        out = []
        for r in payload.get('results', []):
            url = r.get('url', '')
            quality = source_quality(url, r.get('title', ''))
            out.append({
                'title': r.get('title') or domain_of(url) or 'Untitled source',
                'url': url,
                'domain': domain_of(url),
                'content': (r.get('content') or '')[:self.max_chars],
                'search_score': float(r.get('score') or 0),
                'quality_score': quality,
                'authority_tier': self._authority_tier(quality),
                'published_date': r.get('published_date') or r.get('date'),
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
            })
        return out, None
