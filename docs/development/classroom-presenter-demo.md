# Change: one live browser journey for the classroom demonstration

## Scope and starting state

The user approved the launch/reset, unified live browser journey, rehearsal and
recording plan in this chat on 21 October 2026. Previously, rendered Belay used
prepared hint cards while live OpenAI acceptance used a separate scripted CLI
learner. This change makes the browser perform its own checkpoint and Ask and
render the actual released live result.

Checkout `/Users/gregchism/dev/belay-classroom`, branch
`codex/presenter-browser-demo`, starting merged revision
`62ec267e1f4fa1a7c41d2be04f5cb027384540c8`, initially clean. Cairn PR36 and Waypoint
PR56 are merged; their existing saved-file submission protocol is reused.
Upstream Belay and other chats' frozen work remain separate.

## Compare the design with what exists

| Outcome | Existing component | Extension and acceptance |
| --- | --- | --- |
| Live browser Ask | `live_demo.run_turn`, controlled job coordinator | Reuse guarded adapter, exact one-turn grant, runner and accounting; HTTP only admits and reads, main thread executes once |
| Explicit learner actions | `classroom-guidance.js`, classroom policy/router | Actual browser prediction/declaration/remediation; no auto-checkpoint or automatic tracking |
| Recover one request | `ask-jobs.js` request receipts | Inject granted ID only in explicit presenter mode; preserve uncertain-delivery recovery; known policy denials remain definitely not submitted |
| Presenter clarity | existing dev client and signed bootstrap | Public lane/expiry/synthetic input metadata; live always labeled, prepared remains separate |
| Four-file handoff | Waypoint bridge and Cairn preview/confirmation | Compose top-level pages; never treat a tutor source textarea as a saved notebook or copy private guidance into graded artifacts |

## Implementation and verification

The dedicated browser listener admits one reviewed synthetic input and exact
request ID. The browser asset manifest joins the existing backend/profile
review. Direct execution, alternate tutor prefixes and saved-generation routes
are unavailable on this listener. The API and frontend run in supervised service
threads; the main POSIX thread owns bounded provider/runner execution. Existing
default and prepared launchers retain their behavior.

A reset means a fresh synthetic installation, unique request/grant/window and
new explicit reservation inside the cumulative $20 authorization. Never clear
started/blocked markers, renew an old grant or rerun unknown work. Prepared
rehearsals spend no provider credit; live failures never silently fall back.

Required verification: hermetic boundary/policy/recovery tests, frontend controls,
Ruff/format/mypy/full SQLite and PostgreSQL CI, rendered desktop/phone
remediation → one live hint → same-job recovery, explicit four-file Cairn
submission and review/export rehearsal, recording, and owned-resource/private
content teardown. No institutional or real-student readiness claim follows.

## Handoff

Source implementation is complete against the starting revision above. At this
pre-runtime checkpoint the nine changed files are the new browser host/test and
this record, shared live launcher, dev client HTML/JS, Ask receipt module and
their two frontend test files. Root owns the runtime/operator slot; frontend
work is frozen. No new live operation has been admitted at this checkpoint.

Focused verification passed 181 backend controls, Ruff/format and full mypy
(180 source files), plus 78 shared frontend lifecycle and 44 dependency-free
dev-client controls. Fifteen local dependency-backed frontend cases were
unavailable and remain required in CI. Independent source review approved the
backend/browser/profile hashes with no remaining findings. Full SQLite and CI
database/frontend acceptance, rendered rehearsal and recording are pending.

Earlier isolated formatting failed under an inherited non-writable container
UID; the corrected run retained the failure. An initial 768 MiB type-check run
exceeded its finite window; its exact owned container was stopped/removed and
the successful 1536 MiB rerun retained the limitation. No provider call occurred
in these checks. Post-merge CI of the previous MVP separately passed with
configured skips retained. Final runtime/CI outcomes belong in the linked PR
and operator evidence; this paragraph is the pre-runtime source checkpoint.

## Five minute presenter sequence

1. Introduce Belay and the synthetic missing-values exercise. Show the schema
   and observational-unit prediction recorded in the notebook. This presenter
   window uses a fixed example; it does not run or save the notebook.
2. Record checkpoint presence and assistance declaration in the existing panel.
   Explain optional tracking, then enable it explicitly for the policy example.
3. Select the Oracle policy example and choose Ask Belay. Show the private rule
   explanation, acknowledge it, challenge it, and record an intended permitted
   retry. These actions do not publish a grade or submit another request.
4. Choose Ask Belay separately for the permitted live hint. Show its live label
   and same-request recovery after a lost response. The demo admits one request;
   a failure never silently changes to prepared output.
5. Return to the saved four-file assignment. In Cairn, preview the hashes,
   confirm submission and show the committed receipt. Show instructor review
   and matching export, identifying an automated synthetic review when used.
   Tutoring/private guidance does not become grading evidence.
6. Pause and revoke optional tracking. Show that its records disappear while
   required checkpoint/declaration presence and accounting remain. Close with
   the remaining campus/Jupyter, operations and human acceptance work.

## Explicit launch and reset

The operator first validates source and reviews the frozen backend, browser
assets, unchanged live profile and synthetic turn. `validate` reports both
source digests without constructing an SDK or calling an endpoint:

```sh
python -m app.classroom.live_demo validate
```

A new owner-only grant additionally pins `browser_source_sha256` and
`browser_turn_sha256`, the exact JSON turn file's SHA256. Keep the existing
review, runner admission, absolute window, fresh data directory and cumulative
reservation fields. The approved question and source are public synthetic
example inputs, never credentials. Start the window when the presenter is
ready; retain the prior installation and accounting instead of resetting them.

```sh
python -m app.classroom.live_demo prepare --data-dir /PRIVATE/new-session --grant /PRIVATE/new-grant.json --credentials-file /PRIVATE/provider.env --accept-private-retention
python -m app.classroom.live_demo check --data-dir /PRIVATE/new-session --grant /PRIVATE/new-grant.json --credentials-file /PRIVATE/provider.env
python -m app.classroom.live_demo browser --data-dir /PRIVATE/new-session --grant /PRIVATE/new-grant.json --credentials-file /PRIVATE/provider.env --turn /PRIVATE/synthetic-turn.json
```

The listener is loopback-only at ports 8018/5188. Root supplies outer process
supervision and an explicit bounded cloud/runner window when using the existing
demonstration host. The private provider key remains in the server process, as
required by [OpenAI's authentication guidance](https://developers.openai.com/api/reference/overview#authentication).
Ordinary client controls cannot enable this lane or renew its authority.

Stop cooperatively by writing the session's `stop.request` file, or use the
existing controlled-runtime stop tool. Verify owned listener/container absence,
then invoke `live_demo cleanup` with the same installation/grant/credential
arguments. Retain unknown work and accounting; a cleanup refusal is visible and
requires reconciliation. Remove the temporary remote credential after cleanup.

Rehearse without provider calls using the separate existing
`app.classroom.demo` prepare/migrate-private/check/start commands and a new
prepared installation. Keep its prepared-card label visible. A backup recording
must identify its synthetic inputs and whether its hint was live or prepared.
Never copy service databases, provider credentials or raw authentication logs
into the presentation package. Cairn's private synthetic submission/review
evidence remains outside the viewer-facing package.
