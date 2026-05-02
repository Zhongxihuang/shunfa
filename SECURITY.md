# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please email **zhongxihuang11@gmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact

Do not open a public GitHub issue for security reports. You should receive a response within 72 hours.

## Security Notes for Self-Hosting

- **Never commit `.env`** — the `.gitignore` already excludes it, but double-check before pushing.
- **Set strong secrets**: both `JWT_SECRET_KEY` and `API_KEY_ENCRYPTION_SECRET` must be random strings of 32+ characters in production. The server will refuse to start if defaults are used.
- **BYOK**: user DeepSeek API keys are encrypted with Fernet (AES-128-CBC) before being stored in the database. The encryption key is derived from `API_KEY_ENCRYPTION_SECRET`.
- **REQUIRE_USER_API_KEY=true** is recommended for public deployments so the server never uses a shared API key.
- The Swagger UI (`/docs`) and Prometheus metrics (`/metrics`) are only available in non-production environments.
