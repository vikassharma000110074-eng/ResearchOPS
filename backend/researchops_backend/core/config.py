from functools import lru_cache
from pathlib import Path
import os
import tempfile
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / '.env', override=False)
load_dotenv(ROOT / 'backend' / '.env', override=False)

class Settings:
    def __init__(self):
        self.app_name = 'ResearchOps'
        self.environment = os.getenv('APP_ENV', 'production' if os.getenv('VERCEL') else 'local').lower()
        self.gemini_api_key = os.getenv('GEMINI_API_KEY', '')
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
        self.gemini_fallback_models = [m.strip() for m in os.getenv('GEMINI_FALLBACK_MODELS', '').split(',') if m.strip()]
        self.gemini_max_retries = int(os.getenv('GEMINI_MAX_RETRIES', '0'))
        self.tavily_api_key = os.getenv('TAVILY_API_KEY', '')
        self.research_workers = max(1, min(12, int(os.getenv('RESEARCH_WORKERS', '4'))))
        self.hadoop_mode = os.getenv('HADOOP_MODE', 'local').lower()
        self.hadoop_binary = os.getenv('HADOOP_BINARY', 'hadoop')
        self.hadoop_streaming_jar = os.getenv('HADOOP_STREAMING_JAR', '')
        self.data_dir = Path(os.getenv('DATA_DIR', str(Path(tempfile.gettempdir())/'researchops') if os.getenv('VERCEL') else str(ROOT / 'data')))
        self.db_path = self.data_dir / 'researchops.db'
        self.database_url = os.getenv('DATABASE_URL', '') or os.getenv('POSTGRES_URL','') or f'sqlite:///{self.db_path}'
        if os.getenv('DEMO_MODE','').lower()=='true':self.database_url=f'sqlite:///{self.db_path}'
        if self.database_url.startswith('postgres://'):
            self.database_url = self.database_url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif self.database_url.startswith('postgresql://'):
            self.database_url = self.database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
        self.max_source_chars = max(1000, min(12000, int(os.getenv('MAX_SOURCE_CHARS', '6500'))))
        self.adaptive_source_hard_cap = max(40, min(1000, int(os.getenv('ADAPTIVE_SOURCE_HARD_CAP', '60'))))
        self.cors_origins = [x.strip().rstrip('/') for x in os.getenv('CORS_ORIGINS', '').split(',') if x.strip()]
        self.public_access = os.getenv('PUBLIC_ACCESS', 'false').lower() == 'true'
        self.workspace_password = os.getenv('WORKSPACE_PASSWORD', '')
        self.session_secret = os.getenv('SESSION_SECRET', '')
        self.execution_mode = os.getenv('EXECUTION_MODE', 'vercel-workflow' if os.getenv('VERCEL') else 'local-worker').lower()
        self.job_max_attempts = max(1, min(5, int(os.getenv('JOB_MAX_ATTEMPTS', '3'))))
        self.lease_seconds = max(30, int(os.getenv('JOB_LEASE_SECONDS', '180')))
        self.api_timeout_seconds = max(10, min(75, int(os.getenv('PROVIDER_TIMEOUT_SECONDS', '60'))))
        self.max_active_jobs = max(1, min(50, int(os.getenv('MAX_ACTIVE_JOBS', '2'))))
        self.max_saved_jobs = max(10,int(os.getenv('MAX_SAVED_JOBS','100')))
        self.storage_budget_mb = max(10,int(os.getenv('STORAGE_BUDGET_MB','350')))
        self.max_monthly_runs = max(1,int(os.getenv('MAX_MONTHLY_RUNS','30')))
        self.demo_mode = os.getenv('DEMO_MODE', '').lower() == 'true'

    def validate_runtime(self):
        missing = []
        if not self.demo_mode:
            if not self.gemini_api_key: missing.append('GEMINI_API_KEY')
            if not self.tavily_api_key: missing.append('TAVILY_API_KEY')
        if self.environment == 'production':
            if not self.database_url.startswith('postgresql+psycopg://'): missing.append('DATABASE_URL (PostgreSQL)')
            if not self.public_access and len(self.workspace_password) < 16: missing.append('WORKSPACE_PASSWORD (16+ characters)')
            if not self.public_access and len(self.session_secret) < 32: missing.append('SESSION_SECRET (32+ random characters)')
            if self.demo_mode: missing.append('DEMO_MODE must be false in production')
            if self.execution_mode != 'vercel-workflow': missing.append('EXECUTION_MODE=vercel-workflow')
            if '*' in self.cors_origins: missing.append('CORS_ORIGINS must contain explicit frontend origins')
        if self.execution_mode not in {'local-worker', 'vercel-workflow'}: missing.append('EXECUTION_MODE must be local-worker or vercel-workflow')
        return missing

@lru_cache
def get_settings():
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
