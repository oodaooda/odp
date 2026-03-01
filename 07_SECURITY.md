# Security Document (SEC)

## 1. Purpose
Define the security posture, boundaries, and enforcement mechanisms for ODP.

## 2. Threat Model (High-level)
- Prompt injection and agent manipulation
- Secret leakage via logs or artifacts
- Unauthorized merges or gate bypass
- Supply chain issues in dependencies

## 3. Security Controls
- Orchestrator-only memory writes and merges
- Immutable audit log of state transitions and gates
- Artifact scanning before promotion
- Secrets scanning on all diffs and logs
- Agent workspace isolation per task
 - Dependencies must come from trusted sources
 - Security updates tracked and applied on a regular cadence

## 4. Access and Auth
- Least-privilege for agent runtime
- Token-based API access
- Admin-only gate overrides (logged)

## 5. Validation
- Security gates must pass prior to merge
- All security findings produce artifacts
- Failures must be observable and reproducible

## 6. Dependency Hygiene
- Prefer official package registries and pinned versions.
- Require dependency scan in CI for every PR.
- Maintain SBOM and alert on known CVEs.
