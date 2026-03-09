# Milestone 14: Multi-Project & GitHub Integration

## Goal
Support multiple concurrent projects and integrate with GitHub so ODP can be triggered by real-world events (PRs, issues) and push results back (create PRs, post comments).

This is the final milestone that makes ODP a complete, externally-connected platform as described in the PRD.

## Scope

### 1) Multi-project support
- [x] Project selector in sidebar (dropdown)
- [x] `POST /projects` — create new project with name + repo URL
- [x] `GET /projects` — list all projects
- [ ] Project settings page: name, repo URL, default branch, agent config
- [ ] Remove hardcoded default project ID from frontend

### 2) GitHub webhook integration
- [x] `POST /webhooks/github` — receives push/PR/issue events
- [x] Webhook signature verification (`X-Hub-Signature-256`)
- [x] Auto-create ODP task from: new issue with label, PR review request
- [ ] Store GitHub repo URL + token per project

### 3) GitHub PR creation
- [ ] After task reaches COMMIT state, auto-create GitHub PR *(module exists but not wired into orchestrator commit flow)*
- [x] Uses GitHub API via `httpx` (`github.py` module)
- [ ] PR URL stored as artifact and shown in TaskDetail

### 4) GitHub status checks
- [ ] Post commit status to GitHub on gate pass/fail *(module exists but not wired into gate logic)*
- [ ] ODP appears as a CI check on PRs
- [ ] Link back to ODP task detail page

### 5) Concurrent project isolation
- [x] Verify: separate Redis keyspaces per project (already namespaced by project_id)
- [x] Verify: separate Postgres rows per project (already filtered by project_id)
- [x] Verify: separate git worktrees per project (already isolated)
- [ ] Load test: 3+ projects running tasks simultaneously

## Non-goals
- GitLab / Bitbucket integration (GitHub only for v1)
- Automated deployment after merge
- Public API for third-party integrations

## Deliverables
- [x] Project creation + selection working in UI
- [x] GitHub webhook receives events and creates tasks
- [ ] PR auto-created on task commit *(module built; not wired into commit flow)*
- [ ] GitHub status checks posted on gate decisions *(module built; not wired into gate logic)*
- [ ] Multi-project load test passes
- [x] `pytest -q` green (60 tests)
- [x] Documentation: `13_GITHUB_INTEGRATION.md`

## Evidence required
- Walkthrough: GitHub issue → ODP task → agent generates code → PR created
- Screenshot of GitHub PR with ODP evidence in body
- Screenshot of ODP showing 2+ projects with active tasks
- Load test results
