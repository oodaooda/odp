# Configuration & Secrets

## 1. Configuration
- All runtime config via environment variables or config files.
- No hard-coded secrets in code or prompts.

## 2. Secrets Management
- Secrets stored in a local secrets file (dev) or secret manager (prod).
- Rotation required for API tokens and DB creds.
- Audit all secret access.

## 3. Logging
- Redact secrets in logs.
- Log access to secret retrieval (event in audit log).
