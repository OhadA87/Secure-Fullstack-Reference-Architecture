# Runbook: [Service/Issue Name]

## Overview
Brief description of the service/issue this runbook addresses.

## Prerequisites
- Access requirements
- Tools needed
- Knowledge assumed

## Symptoms
How to identify this issue:
- Alerts that fire
- User reports
- Monitoring indicators

## Investigation Steps
1. Check service health: `/health` endpoint
2. Review logs: `kubectl logs -f deployment/api`
3. Check metrics: Datadog dashboard
4. Verify dependencies: DB, Redis, external APIs

## Resolution Steps
### Immediate Actions
1. Step-by-step resolution
2. Commands to run
3. Expected outcomes

### Follow-up Actions
- Root cause analysis
- Prevention measures
- Post-incident review

## Escalation
When to escalate and to whom:
- On-call engineer: [contact]
- Engineering manager: [contact]
- Security team: [contact] (if security-related)

## Related Links
- Monitoring: [link]
- Logs: [link]
- Documentation: [link]