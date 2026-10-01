"""Run privately on your computer; paste each value into Vercel Environment Variables."""
import secrets
print('WORKSPACE_PASSWORD='+secrets.token_urlsafe(24))
print('SESSION_SECRET='+secrets.token_urlsafe(48))
