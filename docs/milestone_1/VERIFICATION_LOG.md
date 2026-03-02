# Verification Log

## Task
- Task ID: milestone_1
- Spec refs:
  - docs/MILESTONE_1.md
  - docs/PROCESS.md

## Tests Run
- Command:
  - `/home/deimos/miniforge3/bin/mamba run -n odp pytest -q`

## Results
```
....                                                                     [100%]
=============================== warnings summary ===============================
tests/test_milestone_1.py::test_task_lifecycle_to_commit
tests/test_milestone_1.py::test_gate_enforcement_spec_drift_rolls_back
tests/test_milestone_1.py::test_crash_recovery_resume_endpoint
tests/test_milestone_1.py::test_websocket_replay_and_live_events
  /home/deimos/Documents/openClaw/genesis/odp/services/orchestrator/odp_orchestrator/api.py:44: DeprecationWarning:
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    @app.on_event("startup")

tests/test_milestone_1.py::test_task_lifecycle_to_commit
tests/test_milestone_1.py::test_gate_enforcement_spec_drift_rolls_back
tests/test_milestone_1.py::test_crash_recovery_resume_endpoint
tests/test_milestone_1.py::test_websocket_replay_and_live_events
  /home/deimos/miniforge3/envs/odp/lib/python3.11/site-packages/fastapi/applications.py:4599: DeprecationWarning:
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    return self.router.on_event(event_type)

tests/test_milestone_1.py::test_websocket_replay_and_live_events
  /home/deimos/Documents/openClaw/genesis/odp/services/orchestrator/odp_orchestrator/api.py:174: DeprecationWarning: Call to deprecated close. (Use aclose() instead) -- Deprecated since version 5.0.1.
    await pubsub.close()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
4 passed, 9 warnings in 0.73s
```

## Artifacts
- docs/milestone_1/SCOPE_OF_WORK.md
- docs/milestone_1/ROADMAP.md

## Notes
- Tests are dockerless (fakeredis + sqlite fallback) for environments without a Docker daemon.
- Production/dev still defaults to Redis + Postgres (pgvector attempted).
