"""Milestone 12: End-to-End Orchestration UI — verify project-level WebSocket,
memory promotion UI, enhanced TaskDetail, and search integration."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = REPO_ROOT / "apps" / "web" / "src"


def test_m12_project_websocket_endpoint():
    """Backend must have a project-level WebSocket endpoint."""
    api_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "api.py"
    content = api_path.read_text()
    assert '/ws/projects/{project_id}"' in content, "Missing project-level WS endpoint"
    assert "ws_project" in content, "Missing ws_project handler function"


def test_m12_project_channel_in_events():
    """EventBus must broadcast to project-level channel."""
    events_path = REPO_ROOT / "services" / "orchestrator" / "odp_orchestrator" / "events.py"
    content = events_path.read_text()
    assert "project_channel" in content, "EventBus must have project_channel method"


def test_m12_project_socket_hook_uses_new_endpoint():
    """useProjectSocket must connect to /ws/projects/{id} (not sentinel task)."""
    hook_path = WEB_SRC / "hooks" / "useProjectSocket.ts"
    content = hook_path.read_text()
    assert "/ws/projects/${projectId}" in content, "Hook must use project-level WS URL"
    assert "00000000" not in content, "Hook should not use sentinel task ID anymore"


def test_m12_layout_has_ws_indicator():
    """Layout sidebar must show WebSocket connection indicator."""
    layout_path = WEB_SRC / "components" / "Layout.tsx"
    content = layout_path.read_text()
    assert "useProjectSocket" in content, "Layout must use useProjectSocket"
    assert "ws-indicator" in content, "Layout must show WS indicator"
    assert "Live" in content, "Layout must show connection status text"


def test_m12_task_detail_has_description():
    """TaskDetail must display task description."""
    td_path = WEB_SRC / "pages" / "TaskDetail.tsx"
    content = td_path.read_text()
    assert "task.description" in content, "TaskDetail must show description"


def test_m12_task_detail_has_memory_promotion():
    """TaskDetail must have pending memory promotion UI."""
    td_path = WEB_SRC / "pages" / "TaskDetail.tsx"
    content = td_path.read_text()
    assert "pendingMemory" in content, "TaskDetail must list pending agent memory"
    assert "handlePromote" in content, "TaskDetail must have promote handler"
    assert "Approve" in content, "TaskDetail must have Approve button"
    assert "Reject" in content, "TaskDetail must have Reject button"


def test_m12_task_detail_has_artifact_viewer():
    """TaskDetail must have artifact expand/collapse viewer."""
    td_path = WEB_SRC / "pages" / "TaskDetail.tsx"
    content = td_path.read_text()
    assert "expandedArtifact" in content, "TaskDetail must track expanded artifact"
    assert "View" in content, "TaskDetail must have View button for artifacts"


def test_m12_dashboard_uses_project_ws():
    """Dashboard must use project-level WebSocket for live updates."""
    dash_path = WEB_SRC / "pages" / "Dashboard.tsx"
    content = dash_path.read_text()
    assert "useProjectSocket" in content, "Dashboard must use useProjectSocket"
    assert "subscribe" in content, "Dashboard must subscribe to project events"


def test_m12_search_memory_client():
    """API client must have memory search function."""
    client_path = WEB_SRC / "api" / "client.ts"
    content = client_path.read_text()
    assert "searchMemory" in content, "Client must export searchMemory function"


def test_m12_dashboard_has_description_input():
    """Dashboard task creation must include description textarea."""
    dash_path = WEB_SRC / "pages" / "Dashboard.tsx"
    content = dash_path.read_text()
    assert "newTaskDesc" in content, "Dashboard must have description state"
    assert "textarea" in content.lower(), "Dashboard must have description textarea"
