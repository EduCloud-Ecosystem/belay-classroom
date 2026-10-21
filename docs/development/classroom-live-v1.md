# One-turn live profile v1 — source ready, runtime acceptance pending

Checkout `/Users/gregchism/dev/belay-classroom`, branch
`codex/live-classroom-demonstration`, base
`0415bd902f66804514d26f773f42cc7cbd1906f0`. This source is uncommitted. Upstream
Belay, the old B1 worktree, Portage, Cairn and Waypoint are unchanged. Root is the
sole runtime/remote operator. This document grants no spend or infrastructure.

## Reuse and observable outcome

The before/after is the prepared hint-card demonstration versus one explicitly
admitted synthetic Bob turn through a live provider. The prepared lane and all
default routes are unchanged. The live command reuses the existing signed
identity, HTTP authorization and private prediction/declaration route, encrypted
unsaved job, main-thread worker, complete tutor/safety loop, model_call and
runner_call ledger, and publication checks. It starts no listener and admits no
second job. It is a scripted synthetic learner, not a human or browser acceptance
claim. Optional private monitoring remains off unless separately enabled; the
required checkpoint and assistance declaration do not enable it.

The source contract is P1's
`execution/portage-one-turn-live-contract.json` and
`execution/portage-runner-seam-handoff.txt` in the coordinator's pilot evidence
directory. Both are source-only handoffs. P1 must review the final profile/source
before root creates a new exact grant. The earlier direct OpenAI smoke is not
integration/safety acceptance and must not be repeated just to test transport.

## Fixed profile and failure behavior

`app/classroom/live-profile-v1.json` pins OpenAI `/chat/completions`, model
`gpt-6-luna`, tier `default`, one Bob request/version/policy and one absolute
window of at most 900 seconds. Serialized messages are checked at every actual
attempt, including regeneration: at most 16384 UTF-8 bytes, using the exact same
JSON serialization as model_call, plus its 1024-unit framing allowance. Never
truncate safety prompts to fit. Output caps include reasoning: classifier 100,
planner/self_eval 400, reasoner 800. The reasoner keeps medium/high effort; other
roles explicitly request none. Reformat retains format, effort and caps.

The provisional 19-attempt ceiling includes all stages/retries; classifier, planner,
reasoner and self_eval ceilings are 1/2/8/8. The aggregate conservative reservation
is 341252 token units: sum over stages of attempts × (16384 + 1024 + output cap). Integer prices are
**1 micro-USD per input/output token**, rounded-up reservation prices, not vendor
invoice rates. Provisional allocation is **$0.35 within the $20 total**, retaining
the separate **$0.01 direct-smoke hold**. Root must account for all other holds.
The existing nonrenewing currency ledger remains authoritative; no second
accounting framework or refund logic is added.

A narrow optional reservation guard runs under the existing coordinator lock,
in the reservation transaction, for cumulative attempt/run admission. The
existing accounting path exposes only its attempt ID while performing external
work. Unknown/overrun/inflight or foreign attempts prevent further work. The
one-shot `run-started.json` marker is durable before HTTP mutations and never
removed by restart/cleanup. Failure cannot cause automatic continuation, replay,
a new learner, a fresh budget period or a renewed deadline. A blocked marker
survives provider/parse/contract failures and prevents another dispatch.

SDK and HTTP transport retries are zero. Explicit HTTP 400/422 errors retain
unknown usage and stop: an HTTP status is not evidence of zero usage. A valid,
measured non-classifier response may receive one bounded JSON reformat attempt.
Invalid/missing classifier fields, non-object classifier JSON, missing/malformed
usage, response model/tier/request-ID mismatch, excess usage, expired/revoked
root or membership authority, unavailable runner/verifier, or output failure
withhold release. The strict classifier uses the original classifier prompt;
it never manufactures an unflagged result. Governance, distress, worked-example,
retrieval and leak checks remain in the original loop.

The dedicated worker must execute on the main POSIX thread. Per-request signal
supervision imposes a 15-second wall deadline; a full-job absolute signal timer
fences execution/publication. SDK inactivity timeout is also 15 seconds. Root
must supply outer process supervision and confirm teardown after interruption.
The key is parsed as data from only `OPENAI_API_KEY` in an owner-only ordinary
file, with no shell sourcing. The launcher scrubs inherited configuration;
HTTP proxies, redirects, SDK debug logging and automatic retries are disabled.

## Isolated safety runner

The explicitly selected internal core.runner backend preserves outer
runner_call accounting and RunnerResult. It stages only the reviewed harness,
bootstrap, exact synthetic spec/checker/data and this invocation's source; the
profile permits no artifacts. Unknown names, path traversal, reserved collisions,
more than five input files or 256 KiB total, altered trusted inputs and wrong
limits fail closed. Inputs/bootstrap mount read-only; there is no repository,
home, environment, credential or Docker-socket mount in generated-code containers.

Root's cached image ID is
`sha256:7bd11b08999a9d227539029473f3dfb057e82245675611df7cf203f0984e2a58`.
The container runs `python -I /runner/_child.py /input/__program__.py` as
UID/GID 65534, network none, read-only root, all capabilities dropped,
no-new-privileges, normal seccomp, private PID/IPC, 512 MiB memory/no extra swap,
1 CPU, 32 PIDs, 64 MiB private /tmp, 10 CPU seconds, 20 wall seconds, and
64 KiB per stdout/stderr stream. Eight executions reserve at most 168000 wall-ms.
No pull, build, installation, substitution or host interpreter fallback occurs.

Before starting, the daemon's actual confinement/mount/image settings are
inspected. Each owned container has operation/attempt labels and a durable name
record before creation. Timeout/overflow triggers stop, followed by inspection
and removal of that exact owned container. Stop/removal uncertainty retains
staging and runner liability/slot, blocking further admission. Missing,
duplicate, malformed or truncated grade records, dependency errors, OOM and
nonzero process exits raise a control failure rather than becoming a safe
non-solution. Ordinary failed formative checks remain failed checks.

Container inspection cannot supply measured peak CPU/memory. The evidence
explicitly labels those measurements unavailable; root must provide host-side
monitoring if required. Image Python/pandas/numpy qualification belongs to root's
separate admission evidence. The in-process student/harness stdout verdict is
not tamper-proof against an adversarial program; this bounded synthetic demo is
not adversarial grading acceptance.

## Commands and operator inputs

Run in the backend directory of root's exact reviewed snapshot, with Python
3.12 and all three requirements files. This path also explicitly depends on
httpx (declared in requirements.txt), pytest/TestClient, the baked provider SDK
versions, POSIX signals and local `/usr/bin/docker` on the admitted existing
host. Generated code uses the separate minimal cached image, never the API-key
process/image environment. No institutional resource or real student input.

One source-only validation command:

```sh
python -m app.classroom.live_demo validate
```

It imports no application runtime/SDK, executes no model/runner/DB and prints
source/profile SHA256, finite policy and installed-distribution metadata. Run
again after formatting or any source/test/dependency change. A source hash is
not a grant. Adding `--grant /PRIVATE/live-grant.json` additionally checks the
exact owner-only grant, source/profile hashes, P1 review file/hash, root reserve
and runner admission flags/references. The supplied template deliberately fails.

Root fills every template field and provides a new dedicated absolute data path,
unique deployment and request IDs, nonrenewing absolute timestamps and distinct
$0.35 reservation ID. A template/example is never execution authorization.
Never use an existing hint-card installation or existing ledger for this command.
Prepare only after final review/grant and explicit synthetic private-retention
acceptance; prepare makes no provider call:

```sh
python -m app.classroom.live_demo prepare --data-dir /PRIVATE/live-one-turn --grant /PRIVATE/live-grant.json --credentials-file /PRIVATE/provider.env --accept-private-retention
python -m app.classroom.live_demo check --data-dir /PRIVATE/live-one-turn --grant /PRIVATE/live-grant.json --credentials-file /PRIVATE/provider.env
```

The bounded UTF-8 turn file has exactly these fields. The operator's `true`
values explicitly attest the scripted synthetic learner has recorded both
prediction items; they are not inferred from monitoring, saving or model output.
The source must be the synthetic learner's current work. No client result is
invented or treated as a checker result.

```json
{
  "message": "How can I check whether missing source cells survived my reshape?",
  "source": "# Synthetic learner's current work; no model-generated solution.\n",
  "schema_present": true,
  "unit_present": true,
  "declaration": "ai_assisted"
}
```

One actual execution command, **only after root admits the exact source and
reserves the operation**:

```sh
timeout --signal=TERM --kill-after=5s 920s python -m app.classroom.live_demo run --data-dir /PRIVATE/live-one-turn --grant /PRIVATE/live-grant.json --credentials-file /PRIVATE/provider.env --turn /PRIVATE/synthetic-turn.json --response-output /PRIVATE/live-one-turn/synthetic-released-result.json
```

The source's POSIX timers are additional protection; the outer command requires
GNU timeout on the admitted Linux host. A timeout is not a refund or permission
to rerun. Root inspects recorded owned container names and confirms stop/removal
before closing the CPU resource admission. Do not remove unknown evidence,
reinitialize the ledger, clear blocked/started markers or replace the grant to
make a failed turn run again.

Shared stdout/evidence stays content-free. The optional `--response-output`
creates only the released student-facing result as an owner-only synthetic
operator artifact at the exact named data-directory path, with an expiry label.
It is not a shared trace, notebook, submission, grade or research export. Root
must remove it during teardown; the expiry label does not physically erase a
file. Without this flag the result remains only in existing encrypted operational
recovery, whose 300-second TTL is unchanged. Container/attempt evidence records
IDs, hashes, bounded counts, measured wall time, usage and actual teardown state;
no prompt, source, response, credential or raw error text enters shared logs.

Dedicated cleanup verifies both database paths, refuses queued/running/cancel-requested
or unknown jobs, revokes installation subjects and purges all private sessions and
encrypted execution content, including fresh rows. It removes the named result
artifact while retaining jobs, bindings, accounting and started/blocked/attempt
markers. This is ordinary deletion, with no secure-erasure or backup-removal claim:

```sh
python -m app.classroom.live_demo cleanup --data-dir /PRIVATE/live-one-turn --grant /PRIVATE/live-grant.json --credentials-file /PRIVATE/provider.env
```

If external grant revocation prevents launcher maintenance, root can use the
existing dedicated cleanup tools against the installed directory; revocation is
never reversed to regain inference. No long-lived backup of synthetic execution
content is authorized. Root separately reconciles provider billing and all holds.

## Verification and current checkpoint

Source-only work performed here: exact checkout inspection, underlying P1
contract/source review, AST parsing, JSON parsing and whitespace inspection.
No pytest, Ruff, mypy, service, build, container, model or network execution was
admitted to the source writer. The coordinator reported the prior offline run as
74 passed and one expected prompt-cap contract failure, with no API call. Its
retained measurement artifact is
`execution/verification/belay-live-offline-v2/actual-loop-measurement-1.json`: 19
frames (1/2/8/8), full retrieval/context/governance preserved, maximum 14643 message
bytes. The original 6144-byte failure remains evidence. This unreleased v1 source
now uses P1's provisional 16384-byte/19-attempt/$0.35 formula; final P1 hash review
and root execution grant are still pending. The full-loop test retains exact role
counts, measured 14643-byte maximum and 341252-unit reservation arithmetic; a
separate deliberately 6144-byte test profile still proves fail-closed rejection.
The newly changed source/tests have not been run. Root must format/review this
diff, recompute source/profile hashes and rerun the affected checks without
weakening gates.

Focused offline command from backend:

```sh
python -m pytest tests/test_classroom_live.py tests/test_controls_execution.py tests/test_runner_sandbox.py tests/test_controls_worker.py tests/test_jobs_worker.py tests/test_injection_guard.py tests/test_classroom_policy.py tests/test_classroom_demo.py -q
```

The new tests mock SDK construction, transport and Docker, deny external sockets,
processes and host runner use, and cover actual retry fields/counts, oversized
regenerated bodies, unknown usage, format/auth errors, invalid classifiers,
model/tier/output mismatch, root/membership revocation, expiry before/after
response, persistent count/one-shot admission, runner ID/accounting, malformed
verdicts, selected-backend non-fallback, and owned stop/teardown failure states.
These controls do not establish live transport, Docker confinement or browser
acceptance. Required full Ruff/format/mypy, SQLite and Postgres suites, actual
image confinement/teardown and rendered learner interaction remain due.

Next concrete action: root formats and reviews this snapshot, runs offline gates,
retains any failures, obtains final P1 profile/source review and runner/headroom
admission, then decides whether to create the one-turn grant. No commit/push,
merge, deployment, live inference or acceptance is claimed by this checkpoint.
