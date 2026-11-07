# Classroom Portage connection

Opt-in application adapter for [classroom issue #4](https://github.com/EduCloud-Ecosystem/belay-classroom/issues/4).
No live endpoint, credential, enrollment, authority service or resource is installed by this change.

Reuse: the ordinary OpenAI-compatible provider, existing controlled operation/ledger,
and Portage's application-credential gateway. The default provider is unchanged.

## Configuration

Operator-owned configuration, never browser parameters:

```text
PROVIDER=portage
CONTROLS_MODE=enforced
PORTAGE_DEPLOYMENT=<existing Belay deployment label>
PORTAGE_INSTITUTION=<existing institution label>
PORTAGE_CLASSROOM=<existing class label>
OPENAI_BASE_URL=https://<approved Portage gateway>/v1
OPENAI_API_KEY=<existing Portage application credential for this course>
LLM_BILLING_MODE=<explicit metered or unmetered policy>
```

Fast/strong select `code_small`/`code_large`. Only literal-loopback HTTP is allowed
for synthetic rehearsal; remote endpoints require HTTPS. Environment proxies,
redirects and SDK retries are disabled. Every attempt uses the current trusted
operation's opaque learner label in `X-Portage-Subject`; Portage authenticates
the application credential and checks current membership. The configured three
scope labels must match. No fallback to a direct provider occurs.

Portage currently requires learner labels matching `[A-Za-z0-9_-]{8,128}`.
Legacy classroom labels such as `edu:2` refuse before contact. An accepted
Waypoint/Cairn identity binding is still required; do not hash, strip punctuation,
or invent a new pseudonym to bypass this boundary.

Belay's existing local safety, queue, budget and unknown holds remain. Portage
owns its inference token admission; this is **not** an authoritative monetary
receipt cutover. A gateway refusal has zero upstream calls in the fixtures, but
Belay retains its conservative unknown hold without an authenticated no-dispatch
receipt. An HTTP 400/422 from Portage is a terminal gateway refusal rather than
an engine JSON-format fallback signal. Direct OpenAI compatibility fallback is
unchanged. The pinned gateway strips `response_format` and temperature; native
format negotiation is not qualified by this slice. Belay still verifies JSON
and accounts for its explicit repair request.

## Reproduce without a model

Use a clean Portage checkout at `79742746b10ace18e498111dd5a8f3227edd995c`.
The tests reject a different commit or tracked source edits. Python 3.12.13 was
used locally (macOS arm64); Linux CI is separate evidence.

```sh
uv venv --python 3.12.13 .venv
uv pip sync --python .venv/bin/python --require-hashes deployment/portage/requirements.lock
PORTAGE_CHECKOUT=/absolute/clean/portage .venv/bin/python -m pytest -q backend/tests/test_portage_integration.py
```

Without `PORTAGE_CHECKOUT`, component-dependent cases skip; this is not a full
integration pass. The dedicated CI job supplies the exact dependency checkout.
The upstream/authority responses are synthetic, loopback only, and shut down
at fixture teardown. There are no model calls, learner records or cloud jobs.

## Acceptance and boundaries

Tests exercise the real provider, installed OpenAI SDK, HTTP gateway and both
ledgers. They count requests reaching the gateway separately from upstream
requests, including refusals, explicit repair, missing usage and upstream failure.
Configuration, absent/cross-class context and unbound legacy labels refuse.
Controlled startup accepts the provider; the doctor explicitly reports scoped
reachability **NOT PROBED**, rather than issuing an unscoped application request.

This selects the ordinary controlled provider path. The historical one-turn
OpenAI presenter profile remains frozen and is not redirected by this adapter.
A new bounded presenter profile and browser acceptance are separate work.

Next: accepted canonical identity binding, scoped per-attempt receipt/status and
accounting reconciliation, selected actual-model qualification, and full browser
journey. None is established by this synthetic connection. Cairn retains grading;
Waypoint admission is separate from Outfitter worker readiness. Native Jetstream2
expiry/cleanup and real classroom/human/accessibility acceptance remain open.
