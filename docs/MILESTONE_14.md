# Milestone 14: Multi-Project & GitHub Integration

## Goal
Support multiple concurrent projects and integrate with GitHub so ODP can be triggered by real-world events (PRs, issues) and push results back (create PRs, post comments).

This is the final milestone that makes ODP a complete, externally-connected platform as described in the PRD.

## Scope

### 1) Multi-project support
- [ ] Project selector in sidebar (dropdown or list)
- [ ] `POST /projects` — create new project with name + repo URL
- [ ] `GET /projects` — list all projects
- [ ] Project settings page: name, repo URL, default branch, agent config
- [ ] Remove hardcoded default project ID from frontend

### 2) GitHub webhook integration
- [ ] `POST /webhooks/github` — receives push/PR/issue events
- [ ] Webhook signature verification (`X-Hub-Signature-256`)
- [ ] Auto-create ODP task from: new issue with label, PR review request, or manual dispatch
- [ ] Store GitHub repo URL + token per project

### 3) GitHub PR creation
- [ ] After task reaches COMMIT state, auto-create GitHub PR with:
  - Title from task description
  - Body with gate evidence summary + artifact links
  - Branch: `odp/task-{id}`
- [ ] Uses GitHub API (via `httpx` or `PyGithub`)
- [ ] PR URL stored as artifact and shown in TaskDetail

### 4) GitHub status checks
- [ ] Post commit status to GitHub on gate pass/fail
- [ ] ODP appears as a CI check on PRs
- [ ] Link back to ODP task detail page

### 5) Concurrent project isolation
- [ ] Verify: separate Redis keyspaces per project (already namespaced by project_id)
- [ ] Verify: separate Postgres rows per project (already filtered by project_id)
- [ ] Verify: separate git worktrees per project (already isolated)
- [ ] Load test: 3+ projects running tasks simultaneously

## Non-goals
- GitLab / Bitbucket integration (GitHub only for v1)
- Automated deployment after merge
- Public API for third-party integrations

## Deliverables
- [ ] Project creation + selection working in UI
- [ ] GitHub webhook receives events and creates tasks
- [ ] PR auto-created on task commit
- [ ] GitHub status checks posted on gate decisions
- [ ] Multi-project load test passes
- [ ] `pytest -q` + `npm test` green
- [ ] Documentation: `docs/GITHUB_INTEGRATION.md`

## Evidence required
- Walkthrough: GitHub issue → ODP task → agent generates code → PR created
- Screenshot of GitHub PR with ODP evidence in body
- Screenshot of ODP showing 2+ projects with active tasks
- Load test results
