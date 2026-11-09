# Finite Cairn enrollment authority consumer

Tracks Belay-classroom #4, Cairn #37, Waypoint #58 and EduCloud #56. Isolated branch
`codex/classroom-enrollment-authority-v1`, based on roster-consumer PR6 at
`0be46ae9a3154e9f9e17917cc8a6d6d3aafe8433`. The new Cairn exporter is pinned in
`deployment/enrollment/sources.json`. Original Belay and existing worktrees remain
untouched. Scope and branch ownership are in the umbrella's
`classroom-enrollment-authority-v1-scope.json`.

## Behavior and responsibility

Previously a current-looking authorization file could be restored after revocation.
The new operator-mediated path requires a finite authority envelope and an
independent durable watermark. Cairn emits existing opaque roster labels only
after checking a reviewed issuer/subject mapping against its current active roster,
verified Git-host identity, class and pinned assignment. Waypoint/Keycloak remains
the sign-in authority. Belay independently verifies the signed credential against
its configured issuer/audience/key and matches the subject to the exported grant.

Cairn does not automatically prove the cross-system link: the operator must verify
that the IdP subject and Cairn account identify the same learner. No username/email
matching, identity hash derivation or browser-selected roster mapping is introduced.
Belay's legacy operator files remain available only when the new mode is disabled.
The new mode fails closed if its envelope or durable state is removed; do not turn
it off as a recovery workaround. Original Quad payload rules remain unchanged.

The private snapshot adds `authority` with exactly:
`schema_version: 1`, `authority_id` (32 lowercase hex), `issuer`, `audience`,
`revision` (positive integer <= 2^53-1), `issued_at` and `expires_at` (Unix seconds).
Lifetime is at most 300 seconds; future and expired snapshots refuse. The existing
`subjects` and `exercise_versions` payloads retain their roster-consumer semantics.
Every new-mode member must use `cairn_roster_v1` with its authority-supplied generation.

A private SQLite watermark, initialized once for the authority ID, records only
highest revision, canonical-document digest and last observation time. Missing,
corrupt, non-private or symlink state refuses. Older revisions, changed content at
the same revision, wrong issuer/audience/authority and clock rollback refuse.
Newer snapshots update the watermark transactionally across processes. Initialization
never overwrites existing history. These checks execute for both HTTP authorization
and worker grant rechecks, before provider attempts or private job access.

Unchanged refreshes preserve a grant generation. Observed withdrawals, binding
changes and expiry gaps cause Cairn to rotate it. An old unsaved job cannot resume
under a new generation; prior accounting, pending results and liabilities persist.
An empty current snapshot withdraws grants and advances rollback protection.

## Operator setup

Install from the existing version/hash lock in a fresh CPython 3.12.13 environment.
Review the Cairn producer runbook and mapping, then initialize outside learner write
access, using the producer's actual authority ID:

```sh
cd backend
../.venv/bin/python -m app.authority_state /private/operator/authority-watermark.sqlite AUTHORITY_ID
```

Set `AUTH_AUTHORITY_STATE_FILE` to that existing private file, alongside the usual
`AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_PUBLIC_KEY_FILE`, and
`AUTH_AUTHORIZATION_FILE` (the atomically installed Cairn export). Never put tokens,
private keys, account IDs or real learner records in fixtures or Git. Configure the
Portage application's institution/class scope to match; Portage membership and
budgets remain separately operator-managed. This export does not allocate spending
or create a Portage account. The transport fixture explicitly registers its synthetic
member and uses a synthetic current-membership responder, not a live Cairn service.

Refresh at a bounded interval shorter than the validity window; export withdrawals
explicitly. An already exported snapshot can remain valid until its original expiry.
Remove/reactivate events between exports are not observed. Privileged rollback of
both issuance journal and consumer watermark is outside this protection. Preserve
history during backup/recovery; loss of it requires reviewed authority migration,
not resetting revision zero. A valid export is not independent evidence that the
operator selected a current database or verified the institutional mapping.

## Reproduction and acceptance

From a clean consumer checkout and exact clean dependency checkouts:

```sh
uv venv --python 3.12.13 .venv
uv pip sync --python .venv/bin/python --require-hashes deployment/portage/requirements.lock
.venv/bin/python deployment/enrollment/evaluate.py \
  --cairn /absolute/path/to/pinned-cairn \
  --portage /absolute/path/to/pinned-portage \
  --output /new/private/synthetic-evidence-directory
```

The evaluator refuses wrong or dirty dependency pins and reused output directories.
It creates native Cairn SQLite fixtures and exports active, refresh, revoked,
renewed and changed-assignment snapshots. Actual signed HTTP authorization and worker
checks consume those files. The SDK calls the actual pinned Portage gateway/ledger,
with a synthetic upstream only. Expected result: 22 checks, zero skips/errors/failures.
A skipped component fixture cannot pass the evaluator. Raw command logs, JUnit and
source identities are retained. Fixture validity is deliberately finite: regenerate
through the evaluator; do not patch deadlines in saved evidence.

Required ordinary checks remain lint, format, mypy and the full backend suite.
The ordinary suite skips native-component checks when their fixtures are absent;
the dedicated CI workflow executes them with exact dependency pins. PostgreSQL,
CI, local SQLite and actual-model acceptance remain separate evidence.

The initial transport control refused because its gateway was bound to a different
synthetic institution/class. Only fixture configuration changed; scope checks were
preserved. The failed run remains in `output/enrollment-v1/native-1`. Final results
and source/output hashes are in the adjacent verification record.

## Remaining integration

This completes a bounded operator enrollment-export path, not institutional SSO or
a full classroom journey. Next connect the Waypoint notebook presenter to this
reviewed roster binding and credential lifecycle, then test explicit Cairn saved-file
submission, receipt/reopen, result verification and Outfitter cleanup independently.
No learner records, live model/provider calls, cloud activation, merge or deployment
were used or authorized by this change.
