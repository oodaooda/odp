# Factory Acceptance Test (FAT)
## Orchestrated Dev Platform (ODP)

**Version:** 1.0
**Date:** 2026-03-12
**Tester:** ___________________
**Environment:** Local / LAN (`http://10.0.0.25:8080`)

---

## Overview

This document walks you through end-to-end acceptance testing of ODP using a **real coding task** on a real GitHub repository. By the end you will have:

1. Verified the full agent pipeline runs (engineer → QA → security → gate)
2. Confirmed Anthropic (orchestrator chat) and OpenAI (agents) are both live
3. Reviewed real LLM-generated code and a real GitHub PR
4. Confirmed the UI, WebSocket, token counters, and chat all work correctly

**Total estimated time:** 30–45 minutes

---

## Prerequisites Checklist

Before starting, confirm the following are ready:

- [ ] ODP server is running: `python -m services.orchestrator.odp_orchestrator`
- [ ] Redis + Postgres are running: `docker-compose -f infra/docker-compose.yml up -d`
- [ ] Browser is open at `http://10.0.0.25:8080` and you are logged in
- [ ] `.env` contains valid keys:
  - `ODP_ORCH_LLM_PROVIDER=anthropic` + `ODP_ORCH_LLM_API_KEY`
  - `ODP_AGENT_LLM_PROVIDER=openai` + `ODP_AGENT_LLM_API_KEY`
  - `ODP_GITHUB_TOKEN` (a GitHub personal access token with `repo` scope)
- [ ] You have a GitHub account and can create a new public or private repository

---

## Step 1 — Create the Test Repository on GitHub

This is the codebase ODP will work on.

1. Go to [github.com/new](https://github.com/new)
2. Name it `odp-fat-test` (or any name you prefer)
3. Set it to **Public** or **Private** (either works)
4. Check **"Add a README file"** so the repo has an initial commit
5. Click **Create repository**
6. Copy the full repo name, e.g. `your-username/odp-fat-test`

**Result:** Repository exists with at least one commit on `main`.
- [ ] PASS &nbsp;&nbsp; - [ ] FAIL

---

## Step 2 — Create a Project in ODP

1. In the ODP browser UI, look for **"New Project"** or navigate to the **Settings** page
2. Fill in:
   - **Name:** `FAT Test Project`
   - **GitHub Repo:** `your-username/odp-fat-test` (the repo you just created)
   - **Default Branch:** `main`
3. Click **Save** / **Create**
4. You should be redirected to the project dashboard

> If you don't see a "New Project" button yet, you can create one via curl:
> ```bash
> TOKEN=$(grep "^ODP_API_TOKEN" .env | cut -d= -f2)
> curl -s -H "Authorization: Bearer $TOKEN" \
>      -H "Content-Type: application/json" \
>      -X POST http://localhost:8080/projects \
>      -d '{"name":"FAT Test Project","github_repo":"your-username/odp-fat-test","default_branch":"main"}'
> ```
> Copy the `project_id` from the response and navigate to `http://10.0.0.25:8080/projects/<project_id>`.

**Expected:** Project dashboard loads, showing empty task list.
- [ ] PASS &nbsp;&nbsp; - [ ] FAIL

---

## Step 3 — Verify Chat (Anthropic)

1. Click **Chat** in the left sidebar
2. Type the following message and press Enter:

   > `What is ODP and what can you help me with today?`

3. Wait for the response (usually 3–8 seconds)

**Expected:** The orchestrator responds with a coherent description of ODP and offers to help with task management, planning, and agent coordination. The response is NOT the fallback "I received your message" text.

- [ ] PASS &nbsp;&nbsp; - [ ] FAIL
- **Actual response (first 2 lines):** _______________________________________________

4. Follow up with:

   > `I'm about to create a coding task for you. The repo is your-username/odp-fat-test. What should I keep in mind?`

**Expected:** A relevant, contextual reply (not generic).
- [ ] PASS &nbsp;&nbsp; - [ ] FAIL

---

## Step 4 — Submit the Real Coding Task

This is the core of the FAT. You will give ODP a real implementation task.

1. Navigate to the project **Dashboard**
2. Click **New Task**
3. Enter the following:

**Title:**
```
Add a password strength checker utility
```

**Description:**
```
Create a Python module called `password_checker.py` in the project root with the following:

1. A function `check_password_strength(password: str) -> dict` that returns:
   - `score` (int 0-4): 0=very weak, 4=very strong
   - `feedback` (list[str]): list of improvement suggestions
   - `is_acceptable` (bool): True if score >= 2

   Scoring rules:
   - +1 if length >= 8
   - +1 if contains uppercase AND lowercase letters
   - +1 if contains at least one digit
   - +1 if contains at least one special character (!@#$%^&*...)

2. A test file `test_password_checker.py` with at least 5 unit tests covering:
   - Empty password (score 0)
   - Short password (score < 2)
   - Medium password (score 2-3)
   - Strong password (score 4)
   - Edge cases (spaces, unicode)

Use only the Python standard library. No external dependencies.
```

4. Click **Create Task**

**Expected:** Task appears in the dashboard with state `INIT`, then quickly transitions to `DISPATCH`.
- [ ] PASS &nbsp;&nbsp; - [ ] FAIL
- **Task ID (copy from URL):** _______________________________________________

---

## Step 5 — Monitor Agent Execution in Real Time

1. Click on the task to open the **Task Detail** page
2. Watch the **State** badge at the top — it should cycle through:
   - `DISPATCH` → `COLLECT` → `VALIDATE` → `COMMIT` (or `ROLLBACK`)
3. As each agent finishes, their result cards appear below

**While waiting (takes 2–5 minutes), verify the following:**

### 5a — WebSocket Indicator
Look for the **● live** green dot in the top-right area of the task page.
- [ ] WebSocket connected indicator is visible and green

### 5b — Token Counter Updates Live
Watch the **Token Usage** table on the task page. It should update in real time as each agent completes (without needing to refresh the page).
- [ ] Engineer token row populates after engineer agent finishes
- [ ] QA token row populates after QA agent finishes
- [ ] Security token row populates after security agent finishes
- [ ] Total row updates correctly

### 5c — Agent Result Cards
As each agent completes, a result card should appear:
- [ ] **Engineer** card appears with `ok: true` and a summary of the code written
- [ ] **QA** card appears with test results
- [ ] **Security** card appears with a security review

---

## Step 6 — Review Gate Decisions

After all agents complete, the system runs gate checks. Scroll to the **Gate Decisions** section.

**Expected gate phases:**
- `phase_1_lifecycle` — task structure OK
- `phase_2_engineer` — code was written
- `phase_3_qa` — tests pass
- `phase_4_security` — no critical vulnerabilities
- `phase_5_ws` — workspace clean

For each phase:
- [ ] `phase_1_lifecycle` — Passed: ___
- [ ] `phase_2_engineer` — Passed: ___
- [ ] `phase_3_qa` — Passed: ___
- [ ] `phase_4_security` — Passed: ___
- [ ] `phase_5_ws` — Passed: ___

**Final task state:**
- [ ] `COMMIT` (all gates passed — code committed to a branch, PR opened on GitHub)
- [ ] `ROLLBACK` (a gate failed — note which phase: ___________________________)

---

## Step 7 — Review the Output on GitHub

If the task reached `COMMIT`:

1. Open your GitHub repo `your-username/odp-fat-test`
2. Click **Pull Requests**
3. You should see a PR titled something like `[ODP] Add password strength checker utility`

**Review the PR:**
- [ ] PR exists on GitHub
- [ ] `password_checker.py` is present in the diff with the scoring logic implemented
- [ ] `test_password_checker.py` is present with at least 5 test cases
- [ ] PR description summarizes what was done

**Read the code.** Ask yourself:
- [ ] Does `check_password_strength()` implement all 4 scoring rules?
- [ ] Are the tests meaningful (not just `assert True`)?
- [ ] Is the code readable and documented?

**Notes on code quality:** _______________________________________________

---

## Step 8 — Chat Follow-Up (Post-Task Review)

1. Go back to **Chat**
2. Type:

   > `The password checker task just finished. Can you summarize what the engineer agent did and whether the gates all passed?`

**Expected:** The orchestrator gives a coherent summary referencing the task. It may not have direct access to task details but should respond helpfully.
- [ ] PASS &nbsp;&nbsp; - [ ] FAIL

---

## Step 9 — Artifacts & Logs

1. On the Task Detail page, scroll to the **Artifacts** section (if visible)
2. On the **Agent Memory** page (left sidebar), check for any pending memory entries from this task

- [ ] Agent logs are visible in the result cards
- [ ] No unhandled error messages in the UI

---

## Step 10 — Negative Tests

These quick checks verify the system handles bad input gracefully.

### 10a — Auth
1. Open a private/incognito browser window (no token)
2. Navigate to `http://10.0.0.25:8080`
3. **Expected:** Login page appears, not the dashboard
- [ ] PASS &nbsp;&nbsp; - [ ] FAIL

### 10b — Invalid Task
1. In the chat, type:

   > `Create a task that will definitely fail: write a program that solves the halting problem in 10 lines of Python`

   Then go to Dashboard → New Task and create it with that as the title.
2. **Expected:** Task is created, agents attempt it, at least one gate fails, task reaches `ROLLBACK` state

- [ ] Task created: [ ] PASS &nbsp;&nbsp; - [ ] FAIL
- [ ] Task reached ROLLBACK or COMMIT: [ ] PASS &nbsp;&nbsp; - [ ] FAIL

### 10c — Clear Chat
1. Go to **Chat**
2. Click the **Clear Chat** button (top-right)
3. **Expected:** All messages disappear immediately
- [ ] PASS &nbsp;&nbsp; - [ ] FAIL

---

## Summary

| Section | Component | Result |
|---------|-----------|--------|
| Step 3 | Anthropic chat (orchestrator) | [ ] Pass / [ ] Fail |
| Step 4 | Task creation | [ ] Pass / [ ] Fail |
| Step 5a | WebSocket live indicator | [ ] Pass / [ ] Fail |
| Step 5b | Live token counter | [ ] Pass / [ ] Fail |
| Step 5c | Agent result cards | [ ] Pass / [ ] Fail |
| Step 6 | Gate decisions | [ ] Pass / [ ] Fail |
| Step 7 | GitHub PR created | [ ] Pass / [ ] Fail |
| Step 7 | Code quality review | [ ] Pass / [ ] Fail |
| Step 8 | Chat post-task | [ ] Pass / [ ] Fail |
| Step 10a | Auth enforcement | [ ] Pass / [ ] Fail |
| Step 10b | Failed task rollback | [ ] Pass / [ ] Fail |
| Step 10c | Clear chat | [ ] Pass / [ ] Fail |

**Overall result:** [ ] PASS (all critical tests pass) &nbsp;&nbsp; [ ] FAIL (one or more critical tests failed)

**Tester signature:** ___________________ &nbsp;&nbsp; **Date:** ___________________

---

## Defects Found

| # | Step | Description | Severity |
|---|------|-------------|----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

---

## Notes

_Use this space for observations, unexpected behaviour, or suggestions:_

_______________________________________________
_______________________________________________
_______________________________________________
