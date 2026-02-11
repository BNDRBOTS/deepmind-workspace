# Secrets Management — DeepMind Workspace

## Overview

DeepMind Workspace supports enterprise secrets management via a pluggable provider system.
Secrets are never stored in code or config files — they are resolved at runtime from the configured provider.

## Quick Start

```bash
# 1. Generate cryptographically secure keys
python scripts/generate_secrets.py --env 2>> .env

# 2. Set your API keys in .env
#    (or configure Vault/AWS — see below)

# 3. Start the app — secret validator runs automatically
python -m deepmind.cli
```

## Providers

### Environment (Default)

Reads secrets from environment variables and `config/app.yaml` `${VAR}` interpolation.
Zero configuration required. Suitable for local development and single-server deployments.

```yaml
# config/app.yaml
secrets:
  provider: environment
```

### HashiCorp Vault

Production-grade secrets management with audit logging, dynamic secrets, and rotation.

```yaml
secrets:
  provider: vault
  vault_url: "https://vault.example.com:8200"
  vault_mount: "secret"
  vault_path: "deepmind"
```

```bash
# Required
pip install hvac
export VAULT_TOKEN=your-vault-token

# Store secrets
vault kv put secret/deepmind \\
  APP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))") \\
  DEEPSEEK_API_KEY=sk-... \\
  OPENAI_API_KEY=sk-...
```

### AWS Secrets Manager

Managed secrets with automatic rotation, IAM-based access control, and CloudTrail auditing.

```yaml
secrets:
  provider: aws
  aws_region: "us-east-1"
  aws_secret_name: "deepmind/secrets"
```

```bash
# Required
pip install boto3
# Configure AWS credentials via standard methods (env vars, IAM role, etc.)

# Store secrets
aws secretsmanager create-secret \\
  --name deepmind/secrets \\
  --secret-string '{"APP_SECRET_KEY":"...","DEEPSEEK_API_KEY":"sk-..."}'
```

### Local Encrypted File

AES-256 encrypted file on disk. Uses PBKDF2 key derivation from `APP_SECRET_KEY`.
Suitable for single-server production deployments without Vault/AWS access.

```yaml
secrets:
  provider: local_encrypted
  local_encrypted_path: "data/.secrets.enc"
```

```bash
# Required
pip install cryptography
# APP_SECRET_KEY must be set in env before using this provider
```

## Startup Validation

The app validates all critical secrets at boot:

| Check | Requirement | Fatal in Production |
|-------|-------------|-------------------|
| `APP_SECRET_KEY` set | Not empty, not placeholder | Yes |
| `APP_SECRET_KEY` length | >= 32 characters | Yes |
| `APP_SECRET_KEY` entropy | >= 3.5 bits/char (Shannon) | Yes |
| `JWT_SECRET_KEY` valid | If set, same rules as above | No (falls back) |
| API keys present | Per enabled service | No (warning) |

If validation fails in production, the app **refuses to start** with a clear error message.

## Integration

All services retrieve secrets through `get_secrets_manager()`:

```python
from deepmind.services.secrets_manager import get_secrets_manager

sm = get_secrets_manager()
api_key = sm.get("DEEPSEEK_API_KEY")
```

Services that have been migrated:
- `openai_client.py` — `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- `auth_service.py` — `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, `APP_SECRET_KEY`
- All other services read from `get_config()` which resolves via YAML `${VAR}` interpolation

## Generating Keys

```bash
# Generate all keys (output to stderr)
python scripts/generate_secrets.py

# Append to .env file
python scripts/generate_secrets.py --env 2>> .env

# JSON output
python scripts/generate_secrets.py --json

# Single key
python scripts/generate_secrets.py --key jwt
```
