# Security Policy

## Reporting Security Vulnerabilities

**DO NOT** create public GitHub issues for security vulnerabilities.

Instead, email: security@[company].com

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested mitigation (if any)

## Security Standards

### Authentication & Authorization
- JWT access + refresh tokens
- RBAC for all admin endpoints
- Session management via Redis
- Rate limiting on auth endpoints

### Data Protection
- No secrets in code/logs
- PII redaction in structured logs
- Secrets via AWS SSM/Secret Manager
- TLS 1.3 for all external communications

### Infrastructure Security
- Private subnets for data plane
- WAF with OWASP managed rules
- VPC with least-privilege security groups
- No public database access

### Development Security
- Pre-commit secret scanning (trufflehog)
- Dependency scanning (Dependabot)
- Container scanning (hadolint)
- Infrastructure scanning (Checkov)

### Security Testing
- **OWASP ZAP:** Automated on staging
- **Nuclei:** Monthly vulnerability scans
- **Scout Suite:** Monthly cloud posture
- **Penetration Testing:** Annual third-party

## Incident Response

1. **Detection:** Alerts via Datadog
2. **Response:** Follow ops/runbooks/security_incident.md
3. **Recovery:** Document in ops/incident_scenarios/
4. **Post-Incident:** PIR within 48h for Sev-2+

## Security Monitoring

### Metrics Tracked
- `auth_failures_total`
- `rbac_denials_total`
- `rate_limit_hits_total`
- WAF block counts
- Suspicious API patterns

### SLOs
- Auth failure rate < 0.5%
- RBAC denial rate < 0.1%
- Security alert MTTR < 30m

## Compliance

- **Data Residency:** US/EU regions only
- **Retention:** User data purged after account deletion
- **Audit Logging:** All admin actions logged
- **Backup Security:** Encrypted at rest + in transit