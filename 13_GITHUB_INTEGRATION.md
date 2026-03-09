# GitHub Integration Specification

## 1. Purpose
Define how ODP connects to GitHub to receive events (webhooks), create pull requests from completed tasks, and post status checks on gate decisions.

---

## 2. Architecture

```
GitHub ──webhook──▶ ODP API ──▶ Orchestrator ──▶ Agents
                                     │
                                     ▼
                               ODP API ──PR/status──▶ GitHub
```

- Inbound: GitHub sends webhook events to `POST /webhooks/github`
- Outbound: ODP creates PRs and posts commit statuses via GitHub API

---

## 3. Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ODP_GITHUB_TOKEN` | For GitHub features | — | GitHub personal access token or app token |
| `ODP_GITHUB_WEBHOOK_SECRET` | For webhooks | — | Webhook signature verification secret |
| `ODP_GITHUB_AUTO_PR` | No | `0` | Auto-create PR on task COMMIT (`1` to enable) |
| `ODP_GITHUB_STATUS_CHECKS` | No | `0` | Post commit statuses on gate decisions |

---

## 4. Webhook Events

### Supported events
| Event | Action | ODP Behavior |
|-------|--------|-------------|
| `issues` | `opened` (with label `odp`) | Create new task from issue title + body |
| `pull_request` | `opened` / `synchronize` | Create task to review/validate PR changes |
| `workflow_dispatch` | — | Manual task trigger with custom inputs |

### Verification
- All webhooks verified via `X-Hub-Signature-256` using HMAC-SHA256
- Invalid signatures return 403
- Events without matching handlers return 200 (acknowledged, ignored)

---

## 5. PR Creation

When a task reaches COMMIT state and `ODP_GITHUB_AUTO_PR=1`:

1. Push task branch (`odp/task-{id}`) to remote
2. Create PR via GitHub API:
   - Title: task title
   - Body: gate evidence summary, agent results, artifact links
   - Base: `main` (or configured default branch)
   - Head: `odp/task-{id}`
3. Store PR URL as artifact on the task
4. Display PR link in TaskDetail UI

---

## 6. Status Checks

When `ODP_GITHUB_STATUS_CHECKS=1`, ODP posts commit statuses:

| Gate Phase | GitHub Status | Context |
|------------|--------------|---------|
| phase_2_engineer | success/failure | `odp/engineer` |
| phase_3_qa | success/failure | `odp/qa` |
| phase_4_security | success/failure | `odp/security` |

Target URL points back to the ODP task detail page.

---

## 7. Multi-Project

Each project stores:
- `github_repo`: `owner/repo` format
- `github_token`: per-project token (or falls back to global `ODP_GITHUB_TOKEN`)
- `default_branch`: branch to merge into (default: `main`)

These are stored in a new `projects` table or as project metadata.

---

## 8. Security

- GitHub tokens stored in environment variables or encrypted in Postgres
- Webhook secrets verified on every request
- PR bodies never include raw secrets or API keys
- Rate limiting: respect GitHub API rate limits (5000 req/hr for authenticated)
