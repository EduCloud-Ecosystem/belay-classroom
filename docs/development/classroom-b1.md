# Change: synthetic classroom demonstration

## Resume here

- Repository: `EduCloud-Ecosystem/belay-classroom` (private), local `/Users/gregchism/dev/belay-classroom`. Upstream Belay and the original B1 worktree remain unchanged.
- Baseline: Belay `92a1d3546798cf9e232a207fc0d7c42d4fb4ca6c`, the open PR14 candidate. Initial import retains its history and the exact B1 source snapshot. This is not upstream acceptance.
- Coordinator: chat `01a16013-d58c-7932-8d1a-d2dd2977b458`. B1 owns tutor source here; CW1 owns Cairn/Waypoint integration; P1 owns bounded live provider qualification. One writer per checkout and one admitted verification workload at a time.
- Goal: two synthetic learners complete INFO511 Lab3 Q4 through independent work or optional hints, deterministic feedback, four-file submission, explicit review and export. Keep optional monitoring private and remediation-focused.
- Budget: Greg authorized **$20 total** for demonstration testing. First direct OpenAI request reserved $0.01; invoice cost remains unreconciled. No institutional resources or real student data.

## Current contract

Pack `datascience`; exercise `info511-lab3-q4-synthetic`; version `info511-lab3-q4-synthetic-v1`; policy `info511-hints-v1`. Fixture: three fictional countries, three years, nine cells, three missing values. Do not redistribute the original course dataset.

Reuse existing authorization, queued execution, provider accounting, deterministic governance and submission protocols. Only peer/study hints are allowed by trusted policy. A required prediction checkpoint and assistance declaration are independent of optional monitoring or research consent. Optional private guidance records trusted rule decisions, actual checker results and explicit remediation actions. No detector guesses, automatic penalties, grade effects or instructor/research feed.

The private API/table and exact operator recipe are documented in [classroom-b1-operator.md](classroom-b1-operator.md). That recipe's prepared hint-card adapter remains separate from any live-provider adapter. Preserve distress/injection/governance controls and recheck authority before every provider attempt.

Cairn owns immutable preview/confirm/receipt and instructor review. Waypoint owns saved work and the existing file-transfer bridge. Belay Classroom must not invent receipts, infer submission from saving, or turn formative feedback into grades.

## Verified evidence and open gates

| Evidence | Bound |
| --- | --- |
| Pure CSV checker | 10 controls passed on initial pinned checker; no notebook or sandbox claim. |
| Private UI | Original stale-response failure retained; fixed source passed six fake-DOM controls. Rendered interaction remains due. |
| Backend Python3.12 | 46 passed, eight test assertions failed because queue admission was counted as another model attempt. Test-only correction prepared; rerun due. Original failure retained. |
| CW1 package v2 | 13 stdlib controls passed on isolated existing droplet. Initial copied-file permission failure retained. No connected receipt claim. |
| OpenAI transport | One HTTP200 request, 23 reported tokens, no retries. Direct transport only; integrated tutoring/safety and invoice reconciliation are pending. |
| Existing compute | Cairn testing droplet reachable, 4GB/2CPU; isolated tests leave existing Cairn/Postgres untouched. No new droplet. |

Full lint/format/types, regression suites, Postgres matrix, real API/worker and rendered UI, notebook/kernel execution, actual submission/review/export, privacy lifecycle and qualified accumulated-output evaluation remain open. Initial import is not a release.

## Next concrete outcome

1. Run the focused CI-repair checks below, then the required quality gates and both database matrix legs. Retain the initial CI failures and the unchanged earlier evidence.
2. Execute trusted instructor examples, retain the six-row missingness failure and nine-row repair, then qualify actual notebook execution separately.
3. Build a versioned live-provider adapter with finite input/output/attempt/currency bounds and trusted subject/request correlation. Never replace the prepared stub silently.
4. Demonstrate the existing synthetic submission/review/export journey and inspect the learner interface. A scripted synthetic reviewer is labeled as such; it is not human acceptance.

## CI-repair checkpoint (2026-10-21)

- Checkout `/Users/gregchism/dev/belay-classroom`, branch `codex/live-classroom-demonstration`, base `f53b8f19e0e445d9a0caedc734c048c383664134`; changes are uncommitted.
- Initial CI run `39683572861` failed five tests on both SQLite and Postgres. All three controlled-runtime provider scenarios stopped at the obsolete three-exercise catalog count, before their adapter/accounting assertions. The launcher test also expected the old catalog; the sidecar inventory omitted the intentional private classroom GET/POST route. Full original logs remain in the coordinator's execution/verification directory.
- Reused the existing exact catalog and route inventories, adding only the synthetic exercise and private route. Extended the existing private-route closed-field controls to reject grade/score inputs. No authorization, governance, provider, accounting or grade-write behavior changed.
- The mypy failure was the untyped nested Git helper in `app/classroom/csv_check.py`; its arguments and bytes return now declare the existing subprocess contract.
- Dirty tracked paths: `backend/app/classroom/csv_check.py`, `backend/tests/controlled_runtime_scenario.py`, `backend/tests/test_local_dev_cors.py`, `backend/tests/test_quad_sidecar.py`, `backend/tests/test_classroom_policy.py`, and this record. The six pre-existing untracked live-provider/profile/test/document files are preserved without edits.
- Verification at this source-only checkpoint: AST parsing and whitespace inspection only. Runtime, Ruff and mypy remain pending with the coordinator; no pytest, service, build, network or model execution was admitted here.
- Next command from `backend/`: `python -m pytest tests/test_controlled_runtime.py::test_real_registered_adapter_saved_unsaved_run_recovery_auth_and_accounting tests/test_local_dev_cors.py tests/test_quad_sidecar.py tests/test_classroom_policy.py tests/test_classroom_checker.py -q`. Then run the existing full quality gates and SQLite/Postgres CI matrix; do not treat this source correction as a passing run.

## Working efficiently

Read this record, affected source/callers/tests and the focused workflow. Reuse existing source maps and exact evidence rather than reconstructing old chats. Send each owner only its changed contract, dependencies and one next deliverable. Do not repeat successful unchanged checks or launch model explanations for deterministic questions. Preserve mandatory quality gates and keep failures visible.

Update this record after a meaningful change with checkout/revision, dirty paths, decision, verification and next action. Historical preparation is preserved in [the initial source record](history/classroom-b1-source-preparation-2026-10-21.md); read it only to resolve a specific uncertainty.
