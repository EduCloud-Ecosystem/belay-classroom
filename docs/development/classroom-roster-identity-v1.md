# Classroom roster identity consumer v1

Tracks Belay-classroom #4, Cairn #37, Waypoint #58 and EduCloud #56.

## Outcome

Belay-classroom can consume an explicitly typed existing Cairn roster ID from its
trusted operator authorization file and pass that label unchanged to Portage.
Before this change, every authorized learner required a provider/numeric label
such as `edu:2`, which the Portage adapter correctly refuses. This consumer neither
creates a learner identity nor hashes a name, token, username or legacy label.

The optional namespace is `cairn_roster_v1`; its roster ID must contain exactly
32 lowercase hexadecimal characters. A required `grant_generation` has the same
format and identifies the authority's grant instance. A renewal must supply a new,
never-reused generation. Existing legacy grants keep their format and execution
reference unchanged. They cannot opt into generation fencing accidentally.

This is a proposed consumer contract. The trusted Waypoint/Cairn producer and
its source-of-truth export/freshness behavior remain unqualified. The presence of
a valid-looking roster label or generation does not prove enrollment or issuer
binding. No new authority service or background synchronization is introduced.

## Source and ownership

Implementation worktree:
`/Users/gregchism/dev/.educloud-worktrees/belay-classroom-roster-identity-v1`,
branch `codex/classroom-roster-identity-v1`, base
`b4b2c3c58539b8b7258cd61bfd9c911ffcddab25`. This is stacked on classroom PR #5.
The parent handed implementation coordination to this chat. PR5 was rechecked as
open/draft at that exact head; no other open classroom PR was present. Existing
primary checkouts, provider worktree and original Belay remain unchanged.

Cairn source `9d7dca579d86fca1c2df00bd6711765e013d0974` calls `id.New()` in
`internal/api/server.go:handleAddRoster`; `internal/id/id.go` generates 16 random
bytes and hex encodes them. `RosterEntry.ID` belongs to its classroom and is
separate from its verified Git-host account ID. This is source implementation
evidence, not an accepted institutional identity bridge.

Waypoint/Keycloak owns principal authentication; Cairn owns roster, coursework
and assignment versions. Belay verifies the signed principal and consumes trusted
authorization; Portage independently checks its ledger and membership authority.
Only the existing Belay authorization model/reference logic and tests change.
The existing PII, Quad, submission and grading contracts remain unchanged.

## Proposed operator binding

The operator must bind a verified principal to the existing Cairn roster row and
class. Never derive the roster label from the login subject, or let browser input
choose it. Configure the example below only in synthetic tests:

```json
{
  "institution_id": "synthetic-inst",
  "class_id": "synthetic-class",
  "learner_id": "47a8ed4608e14957bf74ac18f93655c1",
  "learner_id_kind": "cairn_roster_v1",
  "grant_generation": "a45abc18d8ca4ae6a7b32def7048d2ac",
  "assignments": {"echo-1": "v1"}
}
```

These are fictional fixture values, not an actual enrollment or authorization.
Omitting `learner_id_kind` retains the existing `host_numeric_v1` contract.
The new namespace applies to classroom REST identity fields; Quad's legacy
`pseudo_id` contract remains unchanged and rejects these new labels.

The grant reference binds issuer, audience, authenticated subject, institution,
class, roster ID and grant generation. Current authorization is reread before
execution. Changing the generation invalidates old dispatch references and old
unsaved-job access/publication, while preserving job state and accounting records.
Legacy references retain their exact previous calculation.

## Remaining authority limits

The consumer cannot detect an operator rollback to an identical old authorization
snapshot. The preceding offline control demonstrated that restoring identical
authorization revives its reference. This patch rejects old references when the
authority advances the generation; it does not claim independent monotonic source
history. Durable generation issuance, freshness/deadlines, revocation propagation,
rollback prevention and issuer-to-roster binding remain requirements for the
trusted producer before a real classroom pilot.

The generation is not a token, not a user-selected version, and not evidence that
the authority is current. Saved conversation retention policy is separate from
unsaved job ownership. Restoring old local files is not an approved regrant flow.
A new grant does not erase reservations, consumed usage or unknown liabilities.

Also pending: a bounded Waypoint notebook presenter profile, authoritative
per-attempt Portage receipts/accounting, approved model qualification, full
synthetic browser journey and independent operator review. Historical presenter
grants remain frozen. No private learner data or live model/provider operations
were used or authorized by this change.

## Verification and reproduction

The scope record was committed before adding generation handling. The old offline
packet (six red controls before the initial fix, denied socket checks, full-suite
timeout and regrant liability) is preserved under
`output/roster-identity-v1/offline-preparation-20261108.zip`. Later passing results
do not overwrite those failures.

Current commands/results and source hashes are recorded in
`deployment/portage/roster-identity-verification.json`. A fresh CPython 3.12.13
virtual environment was installed from the existing 56-package version/hash lock.
No old environment was used for the restored-access acceptance run.

From a clean checkout of this branch:

```sh
uv venv --python 3.12.13 .venv
uv pip sync --python .venv/bin/python --require-hashes deployment/portage/requirements.lock
PORTAGE_CHECKOUT=/absolute/path/to/portage .venv/bin/python -m pytest backend/tests/test_auth_isolation.py backend/tests/test_execution_grants.py backend/tests/test_execution_data.py backend/tests/test_portage_integration.py -q
cd backend
../.venv/bin/python -m ruff check .
../.venv/bin/python -m ruff format --check .
../.venv/bin/python -m mypy
PORTAGE_CHECKOUT=/absolute/path/to/portage ../.venv/bin/python -m pytest -q
```

Portage must be clean at `79742746b10ace18e498111dd5a8f3227edd995c`.
Expected focused result: 229 passed, no failures or skips. Controls exercise the
actual classroom HTTP boundaries, signed identity, required namespace/generation,
forged principal and wrong-class refusal, stale/revoked/renewed grants, private
job ownership, the actual SDK/gateway/ledger and synthetic upstream, including
subject preservation and gateway/provider request counts and authority paths.
PostgreSQL and hosted CI remain distinct evidence. No browser UI changed.

The next product integration is an accepted trusted authority/export contract and
its Waypoint/Cairn producer, including monotonic generation and freshness. This
consumer is reviewable independently; it does not complete SSO or classroom
launch readiness.

Final local full-suite result: 1,112 passed, 20 skipped, zero errors/failures
(327.966 seconds). Skips cover unavailable PostgreSQL, PowerShell, verifier
sibling checkout and opt-in live-model evaluation. Lint, format and mypy pass.
The raw logs and JUnit files remain local, with hashes in the verification record.
Hosted CI and PostgreSQL acceptance are recorded separately by the coordinator.
