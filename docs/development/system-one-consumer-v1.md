# System One shadow consumer compatibility

Authorized 2026-11-12 by the request to execute the System One direction toward
a classroom pilot. Base: `656d6ec1e4be5f9ef7267f5a2bb5145a90238dfe`;
branch `codex/system-one-classroom-consumer-v1` in the separate same-named
worktree. Existing enrollment worktree and original Belay remain untouched.

Extend the existing actual-Portage test fixture and integration workflow only.
Pin the new Portage source, explicitly identify synthetic model fixtures, and
add an opt-in shadow fixture plus controls for actual Belay SDK calls, JSON
repair attempts, unknown usage and refusal. Reuse signed enrollment controls.
No tutor, prompts, pedagogical rules, grades, browser UI or runtime defaults
change. This is an integration test update, not acceptance of a decision model.

Acceptance: existing Portage/enrollment controls pass at the new exact clean
source pin. Shadow metadata must correspond to actual admitted SDK requests,
including repair attempts; advice does not select the requested alias or settle
unknown usage. Pre-admission refusal invokes neither shadow nor inference.
Run the selected tests in a fresh hash-locked Python 3.12 environment, plus
Ruff/format/mypy checks. No external model, learner data, cloud, merge or deploy.

The engineering owner is this coordination workstream; Greg retains classroom
and pilot acceptance. Record all verification outcomes and remaining model,
institutional identity and delivery gates in the umbrella handoff.

## Reproduce

Pinned Portage source: `709f5aba85dd2e56f87e9f5c32a2ac7438268ee5`.
Cairn exporter stays `0cf3158fdf5bbbecc52d3cc9cd88ef33bdfb63fc`.
Historical verification JSON files still describe their original pins and are
preserved. The current dependency JSON and both integration workflows use the
new Portage source.

```sh
uv venv --python 3.12.13 .venv
uv pip sync --python .venv/bin/python --require-hashes deployment/portage/requirements.lock
.venv/bin/python deployment/enrollment/evaluate.py \
  --cairn /path/to/clean/pinned/cairn \
  --portage /path/to/clean/pinned/portage \
  --output output/system-one-native
CAIRN_ENROLLMENT_FIXTURES="$PWD/output/system-one-native/fixtures" \
PORTAGE_CHECKOUT=/path/to/clean/pinned/portage \
.venv/bin/python -m pytest -q backend/tests/test_portage_integration.py \
  backend/tests/test_system_one_portage.py backend/tests/test_enrollment_portage.py
```

The native evaluator refuses non-clean or wrong-revision dependencies and
requires all 22 controls without skips. The SDK/shadow command should pass 28
tests. It uses actual Belay providers/SDK and Portage HTTP/ledger code with a
fabricated engine. It does not contact any model or use learner records.
Ordinary requests keep shadow disabled; the six new controls opt in to rules
shadow. A `code_large` recommendation cannot change the actual `code_small`
request, and the explicit two-request repair yields two decision events.

Evidence is under ignored `output/system-one-v1/`. An initial run had 27 passes
and one skip because native exporter fixtures were not yet supplied; the native
evaluator generated those fixtures and the final selected run passed 28/28.
An initial lint failure concerned import order and pytest fixture shadowing;
the final lint/format checks pass. Full backend and type-check outcomes are
recorded in the umbrella validation JSON after execution. There are no UI or
tutor source changes, so prior browser evidence is retained, not recertified.

Do not reuse the native export fixtures in a long broad-suite run: the exporter
intentionally issues 120-second snapshots. One broad run reused them past expiry
and retained two 503 failures (1,138 passes, 20 skips). This was verification
sequencing, not a reason to extend deadlines or freeze the runtime clock. Use
the normal broad suite without `CAIRN_ENROLLMENT_FIXTURES`, then run the bounded
native evaluator to generate and immediately exercise fresh snapshots. Its
no-skip gate remains separate and mandatory.
