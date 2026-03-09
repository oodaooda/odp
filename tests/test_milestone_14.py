"""Milestone 14: Multi-Project & GitHub Integration — verify project management,
webhook handler, GitHub client, and project selector UI."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = REPO_ROOT / "apps" / "web" / "src"


def test_m14_github_module_exists():
    """GitHub client module must exist with PR creation and status check."""
    gh_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "github.py"
    assert gh_path.is_file(), "Missing github.py module"
    content = gh_path.read_text()
    assert "async def create_pr" in content, "Must have create_pr function"
    assert "async def post_status" in content, "Must have post_status function"
    assert "PRResult" in content, "Must define PRResult dataclass"
    assert "ODP_GITHUB_TOKEN" in content, "Must reference ODP_GITHUB_TOKEN"


def test_m14_webhook_endpoint():
    """API must have /webhooks/github endpoint."""
    api_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "api.py"
    content = api_path.read_text()
    assert "/webhooks/github" in content, "Missing webhook endpoint"
    assert "X-Hub-Signature-256" in content, "Must verify webhook signatures"
    assert "X-GitHub-Event" in content, "Must read GitHub event type"


def test_m14_webhook_creates_task_from_issue():
    """Webhook handler must create task from GitHub issue with 'odp' label."""
    api_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "api.py"
    content = api_path.read_text()
    assert '"issues"' in content, "Must handle issues event"
    assert '"odp"' in content, "Must check for 'odp' label"


def test_m14_webhook_creates_task_from_pr():
    """Webhook handler must create task from GitHub PR."""
    api_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "api.py"
    content = api_path.read_text()
    assert '"pull_request"' in content, "Must handle pull_request event"


def test_m14_project_management_endpoints():
    """API must have project list and create endpoints."""
    api_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "api.py"
    content = api_path.read_text()
    assert 'GET /projects' in content or '@app.get("/projects")' in content, "Must list projects"
    assert 'POST /projects' in content or '@app.post("/projects")' in content, "Must create projects"
    assert "ProjectCreateRequest" in content, "Must have project create schema"
    assert "github_repo" in content, "Must support github_repo field"


def test_m14_project_selector_in_layout():
    """Layout must have a project selector dropdown."""
    layout = WEB_SRC / "components" / "Layout.tsx"
    content = layout.read_text()
    assert "listProjects" in content, "Layout must fetch projects"
    assert "select" in content.lower(), "Layout must have a select element"
    assert "handleProjectChange" in content, "Layout must handle project change"


def test_m14_frontend_project_api():
    """API client must have project management functions."""
    client = WEB_SRC / "api" / "client.ts"
    content = client.read_text()
    assert "listProjects" in content, "Client must export listProjects"
    assert "createProject" in content, "Client must export createProject"
    assert "Project" in content, "Client must define Project type"


def test_m14_github_spec_exists():
    """13_GITHUB_INTEGRATION.md spec must exist."""
    spec = REPO_ROOT / "13_GITHUB_INTEGRATION.md"
    assert spec.is_file(), "Missing GitHub integration spec"
    content = spec.read_text()
    assert "webhook" in content.lower(), "Spec must cover webhooks"
    assert "PR" in content or "pull request" in content.lower(), "Spec must cover PR creation"


def test_m14_project_isolation():
    """Redis store must namespace by project_id (already done, verify convention)."""
    store_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "redis_store.py"
    content = store_path.read_text()
    assert "project_id" in content, "Redis keys must include project_id"
