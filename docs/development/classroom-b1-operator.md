# B1 synthetic classroom component walkthrough — prepared, not accepted

Checkout `/Users/gregchism/.codex/worktrees/belay-classroom-b1/belay`, branch
`codex/belay-classroom-b1`, base `92a1d3546798cf9e232a207fc0d7c42d4fb4ca6c` plus
uncommitted files inventoried/hashes in the private `belay-handoff.txt`.

This recipe is for a later, separately admitted runtime window. No command below
has been run by B1. Do not start it during the current source-only window. No real
student data, original course CSV, real provider keys, Docker, notebook execution,
model download or model/API traffic is part of this lane. “Zero network” here
means no external network/inference; a later browser walkthrough necessarily uses
two loopback listeners. The focused hermetic windows below use no listeners.

## Frozen component contract

| Field | Exact value |
| --- | --- |
| Pack | `datascience` |
| Exercise | `info511-lab3-q4-synthetic` |
| Version | `info511-lab3-q4-synthetic-v1` |
| Teaching policy | `info511-hints-v1`, `mode: hints_only` |
| Notice | `info511-private-guidance-v1` |
| Scope | `synthetic-inst` / `synthetic-class` |
| Alice | signed subject `synthetic-one`, pseudonym `edu:1` |
| Bob | signed subject `synthetic-two`, pseudonym `edu:2` |
| Source | synthetic 3x3, nine cells, three missing cells |
| Source SHA256 | `c638d29069c47efbd4589e80fcf959088809f0b0275942f13a1866fc2703ea7b` |
| Private lifetime | 3600 seconds from session creation, no activity extension |

No student identifier is minted from a name/email. These deliberately synthetic
launcher identities do not implement institutional sign-in/federation. The local
operator can issue both identities; this is a test harness, not multiuser hosting.

Operator `authorization.json` binds installed versions, per-subject membership
and `teaching_policies`. Browser fields confer no permission. Removal of a subject
or its grant is allowed during rehearsal and must deny later authorized work.
Changing the teaching binding requires a separate scope decision. Only this
exercise is affected; the generic `_skeleton` demo never qualifies it.

Private API (same contract for `/api` and `/quad/v1`):

- `GET /api/classroom/info511-lab3-q4-synthetic/info511-lab3-q4-synthetic-v1`
- `POST` to the same path. Common required fields: `request_id` (16–64 ASCII
  letters/digits/underscore/hyphen), `expected_revision` (nonnegative integer),
  `action`. Exactly the fields below; arbitrary text/extra fields rejected.
- `enable` / `resume`: `notice_version` with the exact notice above.
- `pause` / `revoke`: no additional fields.
- `checkpoint`: `schema_present` and `unit_present`, both booleans. This records
  attested presence only; it does not prove chronology, correctness or authorship.
- `declaration`: `declaration` equal to `no_ai` or `ai_assisted`.
- `guidance_opened` / `challenge` / `retry`: `alert_id`, a server-issued 32-hex ID.

Example checkpoint:

```json
{"request_id":"checkpoint_000001","expected_revision":0,"action":"checkpoint","schema_present":true,"unit_present":true}
```

Read the current revision first. A stale mutation returns 409; replaying an
identical retained request ID returns the current state without another event.
Reusing that ID with different action fields returns 409. Revoke clears optional
events/alerts/dedup records and advances revision, fencing an earlier enable.
The UI now also discards responses/errors from earlier requests after a newer
request starts, in addition to its learner/context fence. Root subsequently verified this fix: 5 authored controls plus the original independent
regression, all 6 PASS on immutable matching source. Fake DOM only; the original
failed test remains preserved.

Responses contain `monitor` (`off`, `active`, `paused`, `revoked`, `full`),
`checkpoint`, `declaration`, `events`, `alerts`, `revision`, `expires_at`, notice,
policy, retention, guidance and reminder fields. Internal request fingerprints
are not returned. Response cache policy is no-store. Intake limit 4096 bytes.

The `classroom_private_v1` table has only owner hash, revision, expiry and bounded
JSON body. Owner scope includes institution/class/pseudonym/exercise/version/policy.
No prompts, code, explanation/reflection text, affect, detector scores or token
claims are stored there. Operators with DB access are not magically excluded;
there is no instructor/research/grade/export API for this table.

| Event/action | Meaning |
| --- | --- |
| `tool_denied`, rule `hints_only`, kind `policy_guidance` | Trusted forbidden stance/mode; optional private alert, never an accusation |
| `tool_allowed`, rule `hints_only`, kind `workflow_action` | Teaching-policy eligibility, **not** successful dispatch/completion; a budget may still deny work |
| `checker_result`, `check_passed` / `check_needs_attention` / `code_error`, `learning_feedback` | Actual pack Run result, never client/model-reported correctness |
| `checker_result`, `execution_unavailable`, `service_error` | Runner/service problem, not improper use |
| `checkpoint`, `declaration`, `guidance_opened`, `challenge`, `retry` | Explicit closed-field action; optional event only while monitoring active |

There are at most 64 optional events and 128 retained request fingerprints.
Capacity stops optional monitoring visibly. Pause stops new optional records;
revoke clears them. Required checkpoint/declaration and operational auth/budget
records remain independent. Missing checkpoint is a 409 completion reminder,
missing/mismatched policy a 503 service error, forbidden mode a 403 private rule
response. No new inference call classifies a learner. Existing distress routing,
injection guard and governance remain in the flow.

## Preparation and launch (NOT RUN; later admission required)

Use a prepared compatible Python environment with backend requirements,
`python-dotenv` (existing launcher import), `httpx`/AnyIO (HTTP tests), pandas/numpy,
cryptography/PyJWT, SQLAlchemy and Uvicorn available. No installation/download is
part of this recipe. CI requires Python 3.12. The currently inspected primary
`.venv/pyvenv.cfg` says **3.14.5**, so using it is compatibility evidence only,
not the Python 3.12 gate. Freeze actual dependency versions before acceptance.

Run from the worktree `backend/`. Below `python` means the operator's reviewed
interpreter. Select a new disposable local directory outside all repositories,
backups and synced folders; never reuse an existing installation. The example
absolute path is intentionally local and must not contain other work.

```sh
python -B -m app.classroom.demo prepare --data-dir /tmp/belay-info511-b1-rehearsal
python -B -m app.classroom.demo migrate-private --data-dir /tmp/belay-info511-b1-rehearsal --accept-private-retention
python -B -m app.classroom.demo check --data-dir /tmp/belay-info511-b1-rehearsal --learner alice
python -B -m app.classroom.demo start --data-dir /tmp/belay-info511-b1-rehearsal --learner alice
```

The adapter reuses `controlled_runtime.prepare/check/start/stop`, its RSA key
loading, existing same-origin token handler, SQL ledger, encryption/deletion
ledgers, worker and normal APIs. Prepare binds **only** the frozen assignment and
two grants. Private-table migration is a separate explicit action. Neither
prepare nor check starts listeners. Start uses `127.0.0.1:8016` API and
`127.0.0.1:5186/dev-client.html` UI, with five-minute RS256 tokens. It never prints
private keys/tokens. Clear inherited deployment environment by launching from a
clean operator shell; the adapter also removes inherited auth/provider/controls
settings and supplies the explicit synthetic configuration. No `.env` is loaded.

`local_stub` is bound to a prepared hint card via the existing provider registry.
Every synthetic planner/reasoner/evaluator/classifier call still goes through
`model_call`; its 10/5 token usage is **synthetic accounting**, not measured model
usage. All four scope token caps are 200000; currency cap/prices are zero; queue
and concurrency are finite; runner-call/run/time limits are zero. Clicking Run
must be denied before runner dispatch. Do not reduce safety stages to make a live
attempt cap fit. A live-provider maximum A and 72*A evaluation allowance remain
unqualified and block actual-model evaluation.

The injection guard is enabled and uses the same stub factory; its canned
verdict is not classifier effectiveness evidence. Distress routing remains
enabled with a labeled synthetic operator-support message. The leak/governance
gate is unchanged, and assessed-call evidence from this exercise remains active.
No reference solution or assessed narrative is included in the hint card.

### Observable journey

1. Alice: open the page. Only the frozen exercise/version should be listed.
   Leave research consent, saved conversation and monitoring off. Verify Ask
   produces the prediction reminder without a stub attempt. Write the prediction
   in the notebook, record the presence checkpoint and choose `no_ai`. Do not Ask.
   Continue CW1's four-artifact non-AI route. A completeness pass is not grading.
2. Stop with Ctrl+C (join worker) or the matching `stop` command below. Close the
   old page. Start the same isolated directory with `--learner bob` and fully
   reload a separate browser profile. Alice's private state must not appear.
3. Bob: record the prediction checkpoint, read the notice, explicitly enable
   optional tracking. Open `dev-client.html?stance=oracle` on the same loopback
   origin. Submit one answer-seeking question: expect 403 `hints_only`, private
   guidance and **no provider attempt**. Refresh guidance if necessary.
4. Select “I opened this guidance”, “Challenge this alert”, then “I will retry
   with permitted hints”. Challenge records disagreement without changing policy.
   Retry selects peer/study and focuses the composer; it does not send work.
   Press Ask separately. The response must say “Prepared hint card — no model
   evaluation”. This is the permitted retry, not an approved-model evaluation.
5. Repeat one ordinary Ask with optional saved conversation enabled; inspect
   actual job/result and saved restore/delete. Also check unsaved recovery by the
   same request ID. Do not invent a receipt or rerun an unknown provider request.
   All these service interactions remain NOT RUN.
6. Pause optional tracking and perform an allowed action: no new optional event.
   Revoke: alerts/events clear; checkpoint/declaration stay. The no-monitoring
   route still permits hints after the same required checkpoint. Set assistance
   declaration truthfully (`ai_assisted` if actual AI was used; disclose this
   prepared hint-card tool separately in CW1's human-readable assistance file).
7. Record Bob's conversation/job IDs, then stop/switch to Alice. Fetching Bob's
   saved conversation/job must be denied; both learners' own private states stay
   distinct. Their API privacy tests are prepared; the browser proof is pending.
8. Revoke a synthetic subject in this directory's operator-owned authorization
   JSON. Existing tokens must not restore membership. Verify queued dispatch,
   internal retries, conversation reads and publication are fenced. Cost already
   incurred and unknown holds are never refunded by revocation.

For deterministic API manipulation during the later walkthrough, use this
origin-local browser helper; it obtains in-memory credentials and prints no token:

```javascript
const api = window.BELAY_AUTH_ORIGIN;
const headers = await window.BelayAuth.headers(api);
const path = '/api/classroom/info511-lab3-q4-synthetic/info511-lab3-q4-synthetic-v1';
const state = await (await fetch(api + path, {headers, cache:'no-store'})).json();
// Explicit POST only after selecting the desired action; preserve request_id for replay.
const body = {request_id:crypto.randomUUID().replaceAll('-',''),
  expected_revision:state.revision, action:'pause'};
await fetch(api + path, {method:'POST',headers,body:JSON.stringify(body)});
```

Inspect events/export only through legitimate own-learner APIs. Ordinary research
trace export `/api/session/{own-pseudonym}/events.jsonl` must not contain private
alerts, challenge states or the private table. Cairn's exports contain its
submitted artifacts/review, not Belay's private state. B1 does not implement or
qualify Cairn review/export. Preserve existing consent choices; never enable
research consent merely to make this walkthrough produce an export.

### Cleanup and shutdown

While this explicit adapter runs, the existing managed worker cleanup cycle also
clears expired private bodies every 30 seconds; no scheduler is installed.
Expiry denies reads immediately. Revision-only tombstones survive at most an
additional 900 seconds, then cleanup removes them. If the process stops, no
background cleanup runs: operator must run cleanup before re-admission and after
expiry/retirement. Physical deletion and no-resurrection are still unverified.
No backups are permitted for this disposable rehearsal table. Copied databases,
crash copies, filesystem snapshots and restored authority are outside acceptance;
no real-course privacy claim follows from this preparation.

```sh
python -B -m app.classroom.demo stop --data-dir /tmp/belay-info511-b1-rehearsal
python -B -m app.classroom.demo cleanup --data-dir /tmp/belay-info511-b1-rehearsal
```

Stop signals only the matching launcher and joins bounded work. Cleanup removes
expired private content, not unexpired operational liabilities or work. Revoke
optional monitoring for each learner before withdrawing grants. Retire/dispose
only the exact admitted directory after retained evidence/export review; this
recipe authorizes no deletion of unrelated data. Remove synthetic authority and
verify old tokens fail before calling retirement accepted.

## CW1: check the CSV at the actual submitted revision

CW1 retains four artifacts: notebook, CSV, explanation, assistance declaration.
Use the immutable commit revision from Cairn's authenticated committed receipt;
working files or a locally typed revision are not receipt proof. The local Git
object must already be available. B1 never fetches, clones or submits work.

From this worktree's `backend/`, after later checker admission:

```sh
python -B -m app.classroom.csv_check --repository /absolute/path/to/already-present/submission-repository --revision FULL_40_HEX_RECEIPT_COMMIT --path tidy-inflation.csv
```

The command reads a bounded Git blob at that commit and returns revision, path,
CSV/source hashes, `kind: formative_csv_cell_check`, `ok`, and actionable detail.
Exit 0 means corresponding cells matched; 1 means check failed; 2 means evidence
unavailable. No notebook execution or source-preservation/method proof, no grade
approval, and no teacher receipt are generated. Compare the emitted CSV hash
with the receipt/export hash. “ok” must never substitute for instructor review.

Serialization: UTF-8 CSV, exact ordered header country/year/annual_inflation,
four integer-digit years, blank or literal NA for missing, finite numeric cells,
absolute tolerance 1e-9, row order ignored. Text/float-year notation is rejected.
The pure Python seam remains `check_tidy(original, preserved, output)`; the CSV
adapter reuses it with the frozen source while explicitly reporting that it has
not observed notebook preservation. Real notebook/sandbox evidence is separate.
No complete reference transformation is in learner files/tutor retrieval. CW1
owns its operator-only correct/faulty notebooks and source-revision extraction.

## Two proposed focused hermetic windows (NOT authorization)

Root must bind a new grant to the handoff SHA256 inventory, copy that exact source
to immutable verification storage, record headroom and serialize windows. Any
source mismatch invalidates the grant. Preserve root's initial UI failure.

**Window 1: revised UI race controls — COMPLETED/CLOSED by root.** All 6 PASS
(5 authored plus independent regression), 0.335 seconds, 56,131,584-byte peak RSS.
Exact source hashes match `verification/b1-guidance-revocation-fix/result.json`.
Do not rerun unchanged inputs without a new concern/grant. Reproduction command
from the source-bound snapshot root:

```sh
/opt/homebrew/bin/node --test frontend/tests/classroom-guidance.test.cjs
```

Five authored standard-library/fake-DOM controls, including delayed old response
and delayed old error after revoke. Re-run root's independent stale-GET test
against this new snapshot too; do not point it at its old captured JS and label
that a fix check. No browser, network, service, dependencies or app execution.
One Node coordinator plus its test worker; root's earlier measured peak was
55,083,008 bytes, not a guarantee for this revision. Expected seconds; stop at the
root-granted deadline/memory ceiling rather than retrying indefinitely.

**Window 2: bounded backend controls — COLLECTION FAILED/CLOSED by root.**
The local Python 3.14 environment lacks required PyJWT (`jwt`); no tests passed.
Elapsed 2.764 seconds, peak polled RSS 144,392,192 bytes. Do not repeat in that
incomplete environment or modify the primary venv. Root owns checking/preparing
a separate complete environment. The frozen backend manifest SHA256 remains
`432defb894c7c36bd5c98c613b0cf4a690f7182cbbdcab01acc91b052d852c57`.
For a newly admitted window, from snapshot `backend/`, use an already
prepared interpreter; no installation. A reviewed local compatibility command is:

```sh
env -i PATH=/usr/bin:/bin:/opt/homebrew/bin PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 BELAY_ENV=test TUTOR_PACK=datascience PROVIDER=local_stub CONTROLS_MODE=development_bypass /Users/gregchism/dev/belay/backend/.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_classroom_checker.py tests/test_classroom_policy.py tests/test_classroom_demo.py -q
```

Unset DATABASE_URL lets existing conftest create a disposable temporary SQLite
DB; never inherit a live DB. Required packages are listed above. Single pytest
process, temporary SQLite/RSA fixtures and short TestClient threads; no worker
service, Docker, runner, notebook, SDK construction or actual model. An autouse
fixture rejects socket connects, subprocesses and runner calls; the CSV Git test
uses a controlled mock. The retry tests instantiate a provider with `__new__`
and replace its SDK with an in-memory double, then exercise actual inner
format/reformat retries and the real accounting/queued-load guard. All unknown
usage remains held. The earlier pure-checker peak (69,976,064 bytes) excludes
these web/DB imports; memory/time for this window are UNKNOWN, not pre-cleared.
Use a fresh root-reviewed ceiling and retain any import/fixture failure.

This window is not full Python 3.12/SQL/Postgres/repository acceptance. All broad
required gates, actual server/worker, browser/accessibility, notebook execution,
connected CW1 receipts/review/export, physical cleanup, restart/recovery and
actual-model cases remain separate and NOT RUN.


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
