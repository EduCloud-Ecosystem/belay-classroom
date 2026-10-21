# Change: INFO511 synthetic hints-only classroom activity (B1)

## Scope and starting state

Dispatch: classroom coordination chat `01a16013-d58c-7932-8d1a-d2dd2977b458`,
2026-10-21. This is separately authorized source implementation, not resumed
research, cloud execution, a release, or later-offering policy adoption.

Checkout: `/Users/gregchism/.codex/worktrees/belay-classroom-b1/belay`.
Branch: `codex/belay-classroom-b1`; base/head
`92a1d3546798cf9e232a207fc0d7c42d4fb4ca6c` (current PR14 ref verified read-only).
Primary remains `79589b366c5ac1f8a50f4d30766b466073ef2685` with its existing
untracked AGENTS.md and docs/development/. Guidance copied into this isolated
checkout; no primary files changed. No edits to sibling/course repositories.

Outcome: an explicitly authorized synthetic learner can work independently,
record a pre-help prediction, ask for bounded hints, receive ordinary checker
feedback, and optionally enable/challenge/retry private rule guidance. No
misconduct inference, authorship detection, grade effect, instructor feed or
research export. Four owner hours/week total across this and EduCloud; zero cash.

## Compare with existing components

| Requirement | Existing behavior | Decision |
| --- | --- | --- |
| Cell-preserving check | DS declarative specs and sandbox harness; generic dataframe equality | Extend with tidy_source_cells and a small pandas checker. Preserve runner seam and core DomainPack contract. |
| Trusted hints-only mode | HTTP schemas accept peer/oracle/control; R1 grants bind exercise/version | Extend operator authorization with one named pilot teaching policy; check saved/unsaved boundaries and queued execution. Other exercise behavior unchanged. |
| Private guidance | R2 saved dialogue and R3 accounting have different purposes | Add one bounded private SQL table, excluded from all existing trace/export paths; do not overload research consent or saved dialogue. |
| Learner interface | Existing reference dev client, auth helper and error mapper | Add a small optional section on the synthetic exercise. No new dashboard or sign-in. |
| Required presence | No explicit schema/unit prediction record | Store boolean presence and no_ai/ai_assisted declaration; do not store or judge explanation text. Cairn owns artifact/submission verification. |

## Frozen B1 contract

- Pack `datascience`; exercise `info511-lab3-q4-synthetic`; version
  `info511-lab3-q4-synthetic-v1`; policy `info511-hints-v1`.
- Original INFO511 Q4 adapted explicitly to a **3-country, 3-year synthetic**
  fixture with three missing cells. Original CSV is not copied; rights remain
  unresolved. Original reference/hash retained only in the private dispatch handoff.
- `teaching_policies[exercise_id]` in operator auth JSON carries
  `{exercise_version, policy_id, mode:"hints_only", retention_seconds:3600}`.
  Existing installed-version and membership grants must agree. Missing/mismatched
  pilot policy fails closed for tutoring. No global configuration/default changed.
- Only peer/study allowed. Browser oracle/control/teach yields private
  `hints_only` guidance before a model call. Checkpoint absence is a reminder,
  not wrongdoing. Each subsequent model stage and queued publication rechecks.
  Existing explicit distress routing is reused, not expanded; its support-only
  queued marker may bypass the academic checkpoint, not authorization.
- GET/POST `/api/classroom/{exercise_id}/{exercise_version}`, mirrored under
  `/quad/v1`. POST: `request_id`, `expected_revision`, `action`, and only that
  action's allowed fields. GET supplies revision and the versioned notice.
  All existing bearer/class/assignment checks apply. Intake limited to 4096 bytes.
- Actions: enable/resume with `notice_version`; pause/revoke; checkpoint with
  `schema_present` and `unit_present`; declaration with `no_ai` or `ai_assisted`;
  guidance_opened/challenge/retry with server `alert_id`.
- Challenge is a private disagreement state, not policy override or an automatic
  message to anyone. Retry selects peer/study in the preview and focuses the
  composer; a separate explicit Ask sends work. No automatic model call.
- Server-observed events: tool_denied (policy guidance), tool_allowed (workflow
  action), checker_result (learning feedback or service error). Academic mistakes
  never become policy alerts. No client-supplied checker result enters this store.
- One scope/policy session, max 64 optional events and 128 idempotency records;
  absolute creation-based expiry from explicit policy, no activity extension.
  Pause stops new optional events; revoke erases optional events/alerts. Required
  checkpoint/declaration and authorization/usage controls remain independent.
  Revisions fence delayed re-enables. Expired content is inaccessible; explicit
  cleanup clears it and retains only revision fencing for at most the JWT window.
- Only the authenticated learner has a read route. No prompts, source, text,
  identity claims, emotions or detector signals enter this table. No research,
  instructor, grade or conversation export references it.

## Checker and teaching boundary

The existing harness snapshots the trusted source before learner execution and
checks `country_inflation` remains unchanged. Output `tidy_inflation` must have
exactly country/year/annual_inflation, one row per source cell, integer four-digit
years, exact country/year key coverage and exact missingness. Numeric values use
absolute tolerance 1e-9, zero relative tolerance; no infinities/booleans/text.
Row order is ignored. A syntactic melt/pivot_table call check enforces the stated
method requirement only; it is not proof that the operation executed or of authorship.

The harness is the inherited formative in-sandbox checker, not hardened against
malicious Python tampering inside its own interpreter. Do not use it as independent
high-stakes grading evidence. Original-data 1,276-row acceptance remains unrun.

No reference solution is added to SOLUTIONS, retrieval, starters or learner files.
An exercise-specific disclosure cue rejects assessed melt/pivot_table calls in
tutor drafts through existing governance. This conservative cue can over-block;
it does not prove prevention of fragmented/paraphrased leaks or assessed-narrative
generation. The frozen actual-model/accumulated-output evaluation remains required.

## Preparation and verification commands (NOT execution authorization)

Operator must use a disposable synthetic database with no backups, explicit grants,
retention and cleanup responsibility; this slice does not start or schedule anything.
After compute admission, initialize once with `python -m app.classroom.migration initialize`;
run `python -m app.classroom.migration cleanup` at a declared interval (at most 60s)
and at retirement. Backup/restore of this private table is outside this rehearsal
contract and must not resurrect permission or deleted records. No migration was run.

From backend, after fresh serial compute admission:

```sh
python -m pytest tests/test_classroom_checker.py tests/test_classroom_policy.py -q
python -m pytest tests/test_auth_isolation.py tests/test_conversation_http.py tests/test_saved_jobs.py tests/test_jobs_worker.py -q
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q
```

Also run existing governance/data-science tests, full frontend suite and new
`node --test frontend/tests/classroom-guidance.test.cjs`; PostgreSQL concurrency,
browser keyboard/focus/200%-zoom/screen-reader checks, two-learner privacy and
non-AI path, authority revocation/duplicates/exhaustion/unknown usage and physical
expiry/deletion checks remain required. No runtime suite is waived.

## Source checkpoint — 2026-10-21, revised B1 demonstration preparation

Source preparation is finished for review in this checkout; runtime acceptance is
pending. No source change was made in the primary or another owner's checkout.
Full file/hash inventory is in the assigned private `belay-handoff.txt`.
The operator recipe is [classroom-b1-operator.md](classroom-b1-operator.md).

Additional scoped changes:

- `app.classroom.csv_check`: bounded CSV blob read at an immutable submitted Git
  revision, reusing `check_tidy`; reports hashes and explicit absence of notebook,
  method, source-preservation and grade approval. No competing Cairn protocol.
- `app.classroom.demo`: explicit adapter over existing controlled launcher,
  exact task/version/policy and signed Alice/Bob grants, separate private schema
  migration, finite synthetic ledger, prepared hint card, and serial identity
  switching. No live keys, external inference, code execution or safety bypass.
  Existing worker cleanup gains an opt-in private-table cleanup every 30 seconds;
  default disabled. Source is prepared, never launched or migrated.
- Direct provider calls and whole tutor calls now carry supplemental attempt
  guards into `model_call` so format/reformat retries and secondary guard calls
  recheck classroom authority. Existing queued operation guard and accounting
  remain authoritative. No actual-model attempt cap or Portage acceptance inferred.
- Saved queue submissions avoid an optional second private-store writer inside
  an already-owned ledger transaction; HTTP admission observes before that lock.
- UI request sequence fences discard older responses/errors after newer actions,
  preserving the learner/context fence. Added exact delayed-GET/revoke regression
  plus delayed-error variant. Root immutable-copy verification: five authored plus original independent regression, **6 PASS** (fake DOM only).
- New prepared tests exercise actual internal format/reformat retry boundaries,
  membership/teaching-policy loss, saved/unsaved route denial, request dedup,
  revocation revisions, peer isolation and research-export separation. Scoped
  fixture fails on socket connects, processes and runner invocation.

### Evidence and limits

| Check | Actual status |
| --- | --- |
| Focused Ruff lint/format, AST/JSON, JS syntax, diff whitespace | PASS on changed source; see final handoff counts/hashes |
| Root immutable-copy pure checker | 10 PASS; checker/source hashes still match; no notebook/sandbox/app execution |
| Root original fake-DOM authored controls | 3 PASS on original UI snapshot |
| Root independent stale-GET/revoke control | Original 1 FAIL preserved; revised 5 authored + independent regression = 6 PASS, matching hashes |
| Focused backend compatibility window | COLLECTION FAILED: missing PyJWT (`jwt`); no test pass; window closed |
| Full Python 3.12 gates, mypy, Postgres | NOT RUN, not waived |
| Migration/API/worker/actual browser/accessibility/sandbox | NOT RUN |
| CW1 receipt/review/export, original-data correctness/rights | NOT accepted by B1 |
| Covered live API/model/attempt cap/reconciliation | P1-owned qualification pending; not inferred from hints/stubs |

The available primary venv metadata says Python 3.14.5; a future focused run with
it is compatibility evidence, not CI's 3.12 gate. No broad suite, server, Docker,
model, cloud authentication, commit/push/merge/deploy or scheduler ran here.
Earlier source-edit path mistakes and import-order lint failures were corrected;
no failed runtime test was erased or relabeled.

Known boundaries: original CSV rights unresolved; synthetic3x3 only. The in-process
harness is formative and not hardened against adversarial Python tampering.
Assessed-call cue is conservative, not a proof against fragmented answers or
narrative generation. Optional retry records intent; it does not prove successful
learning, independent authorship or automatically resolve an alert. Full prompt
and accumulated-output evaluation remains open. Required checkpoint/declaration
presence does not require optional monitoring or research consent. Operational
records remain independently required and disclosed.

Next concrete action: root reviews the frozen hashes and separately admits the
two small serial hermetic windows in the operator recipe. Preserve root's failed
UI evidence, then inspect any new failures before broadening. P1 owns covered live
OpenAI/Modal route evidence and attempt correlation; B1's explicit stub adapter
must not be switched to a real provider. Any live integration requires a separate
versioned configuration/adapter and new source-bound verification. CW1 owns its
operator-only notebooks and legitimate four-artifact receipt/review/export path.
No real-course readiness, later offering adoption or completed MVP is claimed.


### Root backend window result

Root's immutable-copy compatibility window closed with exit 2 during collection:
`ModuleNotFoundError: No module named 'jwt'`. PyJWT is already required by the
repository; no source fix or primary-venv mutation was made. Elapsed 2.764 seconds,
peak polled RSS 144,392,192 bytes. No backend test pass or Python 3.12 acceptance.
Evidence: `execution/verification/b1-backend-initial/{grant,result}.json`,
`stdout.txt`. Frozen test-relevant manifest SHA256
`432defb894c7c36bd5c98c613b0cf4a690f7182cbbdcab01acc91b052d852c57`;
all entries still match the worktree. Only documentation/handoff changed after
this result. Root owns subsequent environment preparation and remote operations.


### Python 3.12 off-host assertion correction (not rerun)

Root's isolated offline Python 3.12 run reached the tests and failed eight
parametrized inner-retry cases. `len(calls) == 1` passed; the test incorrectly
expected one total ledger row, conflating queue admission with provider attempts.
Source inspection confirms `claim()` retains the queue row and settles its hold,
while `model_call` creates/settles a separate model row. Only the test changed:
it now asserts the initial queue reservation, retained settled queue row, exactly
one model row for the same operation/scopes, unknown held usage for format errors,
and exact settled usage for malformed-JSON responses. Production accounting is
unchanged. Original failure evidence remains at
`verification/b1-backend-initial/python312-offhost.stdout.txt`.

Updated test SHA256: `6fd84b5f17e81b791a9289caecd57d8cafe48575ad3c3ac53698ab09b38f0895`.
All other 208 entries of root's original 209-entry manifest still match.
Focused Ruff/format, AST and diff checks passed; corrected tests NOT RERUN.
Root must admit a new source-bound window; existing allowances remain closed.
