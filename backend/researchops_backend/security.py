import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import time
from fastapi import HTTPException, Request
from researchops_backend.core.config import get_settings

def safe_error(exc):
    s=get_settings()
    message=f'{type(exc).__name__}: {exc}'
    for secret in [s.gemini_api_key,s.tavily_api_key,s.workspace_password,s.session_secret]:
        if secret:message=message.replace(secret,'[redacted]')
    message=re.sub(r'AIza[\w-]+|tvly-[\w-]+|postgres(?:ql)?[^\s]*://[^\s]+','[redacted]',message)
    return message[:1500]

def issue_session(password):
    s=get_settings()
    if not s.workspace_password or not s.session_secret:raise HTTPException(503,'Workspace authentication is not configured.')
    if not hmac.compare_digest(password.encode(),s.workspace_password.encode()):raise HTTPException(401,'Incorrect workspace password.')
    body=base64.urlsafe_b64encode(json.dumps({'exp':int(time.time())+86400,'nonce':secrets.token_hex(12)}).encode()).decode().rstrip('=')
    signature=hmac.new(s.session_secret.encode(),body.encode(),hashlib.sha256).hexdigest()
    return body+'.'+signature

def require_access(request: Request):
    s=get_settings()
    if s.environment=='local' and not s.workspace_password:return
    token=request.headers.get('Authorization','').removeprefix('Bearer ')
    try:
        body,sig=token.split('.')
        expected=hmac.new(s.session_secret.encode(),body.encode(),hashlib.sha256).hexdigest()
        payload=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        if not s.session_secret or not hmac.compare_digest(sig,expected) or payload['exp']<time.time():raise ValueError()
    except (ValueError,KeyError,TypeError,json.JSONDecodeError,UnicodeDecodeError,binascii.Error):raise HTTPException(401,'Sign in to your ResearchOps workspace.')
