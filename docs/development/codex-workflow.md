# Focused development with Codex

For current classroom scope, exact state and next action, read [classroom-b1.md](classroom-b1.md). New tutor changes belong to this repository, not upstream Belay.

This workflow reduces repeated discovery while preserving the repository's
verification requirements. It adds no background agents, model calls, or
automatic releases. Usage savings have not yet been measured.

## Start with one outcome

Use the existing GitHub issue or specification when one exists. For substantial
work without a record, copy [the change template](change-template.md) into a
task-specific document. Keep the same record through design, implementation,
verification, and handoff. Don't maintain parallel plans in several chats.

A useful request is: “Implement this outcome in this checkout, follow this
record, run its verification commands, and report the final diff and remaining
limitations.” Routine implementation choices do not need a new approval round.
Keep product decisions that change scope explicit.

Before editing, confirm `git status --short --branch` and `git rev-parse HEAD`.
If a sibling component is involved, record its exact checkout and revision too.
An old checkpoint or clean test run does not establish today's state.

## Design against the existing app

For each requested component or feature, compare:

| Question | Record |
| --- | --- |
| What user problem does this solve? | One before/after example. |
| What already exists? | Source file, current behavior, and relevant tests. |
| What is the design source? | Exact chat, issue, screenshot, or spec and its accepted requirements. |
| Can we reuse or extend it? | Smallest compatible change and reason. |
| What can go wrong? | Relevant empty, loading, error, permission, and recovery states. |
| How will we know it works? | Observable acceptance examples and checks. |

UI resemblance alone doesn't establish a new feature requirement. Distinguish
visual changes from new backend behavior. Preserve existing authority boundaries
and privacy controls. For cross-component contracts, locate the actual sibling
`educloud/SYSTEM.md`; keep platform decisions in the umbrella repository.

## Read only what the task needs

| Area | Start here |
| --- | --- |
| Shared rules | `CLAUDE.md`, `CONTRIBUTING.md` |
| Tutor flow | `backend/app/agent/orchestrator.py`, `backend/tests/test_orchestrator_smoke.py` |
| HTTP / sidecar | `backend/app/main.py`, `backend/app/integrations/quad/`, `backend/tests/test_quad_sidecar.py` |
| Domain boundary | `backend/app/core/domain/`, `backend/tests/test_import_boundaries.py` |
| Reference UI | `frontend/README.md`, `frontend/widget.html`, `frontend/api-client.js`, `backend/tests/test_overlay.py` |
| Privacy / governance | `PRIVACY.md`, `backend/app/agent/governance.py`, relevant safety tests |
| Verification | `.github/workflows/ci.yml`, `backend/pyproject.toml`, `VALIDATION.md` |

These are entry points, not an exhaustive list of impacted files. Follow callers
and contracts when needed. Search the relevant section of long history documents
instead of loading their full contents into every implementation session.

## Run the existing checks

Use a prepared Python environment with the three backend requirements files from
`CONTRIBUTING.md`. CI uses Python 3.12. Don't assume a local `.venv` matches it.
From `backend/`, start with the tests for the changed behavior, for example:

```sh
python -m pytest tests/test_overlay.py -q
```

Before delivering application changes, run the existing local quality gates:

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q
```

CI also runs the suite against Postgres with `DATABASE_URL` pointing at a
dedicated test database. SQLite success does not verify Postgres. Record the
actual environment and any missing matrix leg. Do not point tests at student or
production data. Live provider evaluations are separate from hermetic tests.
Documentation-only changes need link/path and diff inspection, not the full
application suite unless they change executable instructions or contracts.

Preserve full failure output outside the conversation when useful; bring back
the failing command, relevant traceback, diagnosis, and outcome. Repair the
cause, then rerun the affected checks. Repeated failure without new evidence
calls for a revised diagnosis, not an unbounded retry loop.

## Finish once, resume from evidence

For substantial work, update the same record with the short handoff in the
template. Report implemented, verified, and unresolved states separately, with
paths to the evidence. Don't repeatedly rerun successful checks against unchanged
inputs just to produce a new summary.

Fieldwork can locate final responses, source links, and local review notes.
Open its existing review desk only when useful. Reading results doesn't require
generating explanations or launching workers; those are separate model work.
Treat summaries as leads to evidence, particularly when a result is old or the
source checkout has changed. Keep its review marks distinct from release approval.

Evaluate this workflow over the next ten accepted changes: track interruptions,
rework, review time, and usage where available. Compare similar tasks, retain
failures, and don't infer savings from fewer tool calls alone.
